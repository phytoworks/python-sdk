"""Python side of the Zarr v3 storage adapter.

Logical field names (``depth``, ``temperature``, ``F0``) are the public
contract; only this module turns one into an array path inside a store, joins
store members to local paths, and PUTs a local store under an issued prefix.

The layout table mirrors the Hub's Zarr field-array layout; the DEPTH array name
comes from the packaged scalar policy, which is generated from that layout.

Heavy optional dependencies stay inside the functions that need them.
"""

from __future__ import annotations

import json
import math
import os
import re
import secrets
import shutil
import threading
import time
from collections.abc import Callable, Iterable, Iterator, Mapping
from contextlib import AbstractContextManager, contextmanager, nullcontext
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import TYPE_CHECKING, Any, NoReturn, cast
from urllib.parse import urlsplit

from ._scalar_policy import depth_policy
from ._transport import require_secure_storage_url
from .errors import TransportError, ValidationError

if TYPE_CHECKING:
    import zarr
    from zarr.core.metadata.v3 import ArrayV3Metadata

ROOT_METADATA = "zarr.json"

_CF_FIELD_NAME = re.compile(r"[A-Za-z0-9_]+")
# Canonical CF layout first; ``raw/{label}`` is the legacy alias of the same field.
_CF_ARRAY_PREFIXES = ("cf/raw/", "raw/")
_THERMAL_FIELD = ("temperature", "raw/data")


def _single_field(modality: str) -> tuple[str, str] | None:
    if modality == "THERMAL":
        return _THERMAL_FIELD
    if modality == "DEPTH":
        policy = depth_policy()
        return policy.field_name, policy.zarr_array_name
    return None


def array_path_for_field(modality: str, field_name: str) -> str | None:
    """The array path (no leading slash) a producer writes for ``field_name``, or ``None``."""

    if modality == "FLUORESCENCE":
        return f"{_CF_ARRAY_PREFIXES[0]}{field_name}" if _CF_FIELD_NAME.fullmatch(field_name) else None
    single = _single_field(modality)
    return single[1] if single is not None and single[0] == field_name else None


def field_for_array_path(modality: str, array_path: str) -> str | None:
    """The logical field an existing array path holds; every written layout of a field resolves to it."""

    path = array_path[1:] if array_path.startswith("/") else array_path
    if modality == "FLUORESCENCE":
        for prefix in _CF_ARRAY_PREFIXES:
            if path.startswith(prefix):
                field_name = path[len(prefix) :]
                return field_name if _CF_FIELD_NAME.fullmatch(field_name) else None
        return None
    single = _single_field(modality)
    return single[0] if single is not None and single[1] == path else None


# Reader decode budget, mirroring the limits the Hub applies to user stores.
DECODE_MAX_AXIS = 16_384
DECODE_MAX_SAMPLES = 64 * 1024 * 1024
DECODE_MAX_BYTES = DECODE_MAX_SAMPLES * 4
DECODE_MAX_CHUNKS = DECODE_MAX_SAMPLES // DECODE_MAX_AXIS
USER_STORE_MAX_METADATA_DOCUMENTS = 32
USER_STORE_MAX_MEMBERS = USER_STORE_MAX_METADATA_DOCUMENTS + DECODE_MAX_CHUNKS
METADATA_READ_CAP_BYTES = 64 * 1024


def _invalid_json_constant(_value: str) -> NoReturn:
    raise ValidationError("Zarr metadata document has a non-JSON numeric value")


def read_metadata_document(path: Path) -> dict[str, object]:
    """Read at most 64 KiB plus one byte, even if a local file grows after stat."""

    try:
        if path.is_symlink() or not path.is_file():
            raise ValidationError("Zarr metadata document is missing or unsafe")
        with path.open("rb") as stream:
            body = stream.read(METADATA_READ_CAP_BYTES + 1)
        if len(body) > METADATA_READ_CAP_BYTES:
            raise ValidationError("Zarr metadata document exceeds the read cap")
        document = json.loads(body.decode("utf-8"), parse_constant=_invalid_json_constant)
    except (OSError, ValueError, RecursionError):
        raise ValidationError("Zarr metadata document is invalid") from None
    if not isinstance(document, dict):
        raise ValidationError("Zarr metadata document must be an object")
    return cast(dict[str, object], document)


def validate_group_metadata(document: dict[str, object], *, ignore_consolidated: bool = False) -> None:
    """Validate the complete group document before a decoder can consult it."""

    from zarr.core.group import GroupMetadata

    if ignore_consolidated:
        document = {key: value for key, value in document.items() if key != "consolidated_metadata"}
    try:
        GroupMetadata.from_dict(document)
    except (ValueError, TypeError, KeyError, AssertionError, RecursionError):
        raise ValidationError("Zarr group metadata is invalid") from None


_DTYPE_BYTES: dict[str, int] = {
    "bool": 1,
    "int8": 1,
    "uint8": 1,
    "int16": 2,
    "uint16": 2,
    "float16": 2,
    "int32": 4,
    "uint32": 4,
    "float32": 4,
    "int64": 8,
    "uint64": 8,
    "float64": 8,
}


def dtype_bytes(data_type: object) -> int | None:
    """Bytes per sample of a Zarr v3 core numeric dtype; ``None`` for anything else."""

    return _DTYPE_BYTES.get(data_type) if isinstance(data_type, str) else None


def _is_extent(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _measure(shape: object, data_type: object, chunk_shape: object) -> str | tuple[int, int, int]:
    if not isinstance(shape, (list, tuple)) or not shape or not all(_is_extent(n) for n in shape):
        return "shape"
    if (
        not isinstance(chunk_shape, (list, tuple))
        or len(chunk_shape) != len(shape)
        or not all(_is_extent(n) for n in chunk_shape)
    ):
        return "chunk-grid"
    width = dtype_bytes(data_type)
    if width is None:
        return "dtype"
    if any(n > DECODE_MAX_AXIS for n in (*shape, *chunk_shape)):
        return "axis"
    samples = chunks = 1
    for extent, chunk in zip(shape, chunk_shape, strict=True):
        on_axis = -(-extent // chunk)
        samples *= on_axis * chunk
        if samples > DECODE_MAX_SAMPLES:
            return "samples"
        chunks *= on_axis
        if chunks > DECODE_MAX_CHUNKS:
            return "chunks"
    return "bytes" if samples * width > DECODE_MAX_BYTES else (samples, samples * width, chunks)


def decode_budget_violation(shape: object, data_type: object, chunk_shape: object) -> str | None:
    """Why decoding this array whole would exceed the reader budget, or ``None`` when it fits."""

    cost = _measure(shape, data_type, chunk_shape)
    return cost if isinstance(cost, str) else None


def store_decode_budget_violation(arrays: Iterable[tuple[object, object, object]]) -> str | None:
    """Why decoding these ``(shape, data_type, chunk_shape)`` arrays together would exceed the budget."""

    samples = size = chunks = 0
    for shape, data_type, chunk_shape in arrays:
        cost = _measure(shape, data_type, chunk_shape)
        if isinstance(cost, str):
            return cost
        samples, size, chunks = samples + cost[0], size + cost[1], chunks + cost[2]
        if samples > DECODE_MAX_SAMPLES:
            return "samples"
        if size > DECODE_MAX_BYTES:
            return "bytes"
        if chunks > DECODE_MAX_CHUNKS:
            return "chunks"
    return None


@dataclass(frozen=True, slots=True)
class DownloadMember:
    """One fully validated member in a Hub's Zarr size snapshot."""

    url: str
    relative: str
    expected_bytes: int


DownloadAdmission = Callable[[Path, tuple[DownloadMember, ...]], None]
_DOWNLOAD_CHUNK_PATH = re.compile(r"c/(?:0|[1-9][0-9]{0,4})/(?:0|[1-9][0-9]{0,4})")


def admit_download_members(members: tuple[DownloadMember, ...], array_paths: tuple[str, ...]) -> None:
    """Admit a 2D reader profile's grammar and disk budget before any storage GET."""

    metadata_paths = {ROOT_METADATA}
    for array_path in array_paths:
        parts = array_path.split("/")
        metadata_paths.update("/".join((*parts[:depth], ROOT_METADATA)) for depth in range(1, len(parts) + 1))
    if len(members) > len(metadata_paths) + DECODE_MAX_CHUNKS:
        raise ValidationError("Zarr listing exceeds the reader member limit")
    if (
        sum(member.expected_bytes for member in members)
        > DECODE_MAX_BYTES + len(metadata_paths) * METADATA_READ_CAP_BYTES
    ):
        raise ValidationError("Zarr listing exceeds the reader byte budget")
    if not metadata_paths.issubset(member.relative for member in members):
        raise ValidationError("Zarr listing is missing required profile metadata")
    for member in members:
        if member.relative in metadata_paths:
            continue
        if not any(
            member.relative.startswith(array_path + "/")
            and _DOWNLOAD_CHUNK_PATH.fullmatch(member.relative[len(array_path) + 1 :]) is not None
            for array_path in array_paths
        ):
            raise ValidationError("Zarr listing contains an unsupported profile member")


def admitted_download_members(
    staged: Path, members: tuple[DownloadMember, ...], admit: DownloadAdmission | None
) -> Iterator[DownloadMember]:
    """Fetch every metadata document and admit it before yielding the first chunk."""

    if admit is None:
        yield from members
        return
    yield from (
        member for member in members if member.relative.endswith("/zarr.json") or member.relative == ROOT_METADATA
    )
    admit(staged, members)
    yield from (
        member for member in members if not member.relative.endswith("/zarr.json") and member.relative != ROOT_METADATA
    )


def _is_canonical_member_path(relative: str) -> bool:
    if not relative or "\\" in relative or relative.startswith("/"):
        return False
    if any(part in {"", ".", ".."} for part in relative.split("/")):
        return False
    windows_path = PureWindowsPath(relative)
    return PurePosixPath(relative).as_posix() == relative and not windows_path.drive and not windows_path.is_absolute()


def _validate_manifest_overview(
    files: Mapping[str, str], member_sizes: Mapping[str, int], total_files: int, total_bytes: int
) -> None:
    if total_files < 0:
        raise ValidationError("Hub returned an invalid Zarr member count")
    if total_bytes < 0:
        raise ValidationError("Hub returned an invalid Zarr total size")
    if total_files > USER_STORE_MAX_MEMBERS or len(files) != total_files:
        raise ValidationError("Hub returned an inconsistent Zarr member count")
    if set(files) != set(member_sizes):
        raise ValidationError("Hub returned inconsistent Zarr member sizes")


def download_manifest(
    files: Mapping[str, str],
    member_sizes: Mapping[str, int] | None,
    total_files: int,
    total_bytes: int | None,
) -> tuple[DownloadMember, ...]:
    """Validate the complete member map and size snapshot before the first GET."""

    if member_sizes is None or total_bytes is None:
        raise ValidationError("Hub omitted required Zarr size metadata")
    _validate_manifest_overview(files, member_sizes, total_files, total_bytes)

    members: list[DownloadMember] = []
    targets: set[str] = set()
    listed_total = 0
    for relative, url in files.items():
        if not _is_canonical_member_path(relative):
            raise ValidationError("Hub returned a non-canonical Zarr member path")
        if not url:
            raise ValidationError("Hub returned an invalid Zarr member URL")
        require_secure_storage_url(url)
        size = member_sizes[relative]
        if size < 0:
            raise ValidationError("Hub returned an invalid Zarr member size")
        if PurePosixPath(relative).name.casefold() == ROOT_METADATA.casefold() and size > METADATA_READ_CAP_BYTES:
            raise ValidationError("listed Zarr metadata member exceeds its read cap")
        target_key = relative.casefold()
        if target_key in targets:
            raise ValidationError("Hub returned duplicate Zarr download targets")
        targets.add(target_key)
        listed_total += size
        members.append(DownloadMember(url, relative, size))

    if listed_total != total_bytes:
        raise ValidationError("Hub returned an inconsistent Zarr total size")
    return tuple(members)


def validate_download_root(root: Path) -> None:
    """Refuse to replace an existing non-directory or symlink destination."""

    if root.is_symlink() or (root.exists() and not root.is_dir()):
        raise ValidationError("Zarr download destination must be a real directory")


@contextmanager
def staged_store(root: Path) -> Iterator[Path]:
    """Create a sibling store with normal umask-based directory permissions."""

    root.parent.mkdir(parents=True, exist_ok=True)
    while True:
        staged = root.with_name(f".{root.name}.stage-{secrets.token_hex(8)}")
        try:
            staged.mkdir(mode=0o777)
        except FileExistsError:
            continue
        break
    try:
        yield staged
    finally:
        shutil.rmtree(staged, ignore_errors=True)


@contextmanager
def staged_download_store(
    root: Path,
    files: Mapping[str, str],
    member_sizes: Mapping[str, int] | None,
    total_files: int,
    total_bytes: int | None,
    download_ready: bool | None,
    completed_bytes: int | None,
    *,
    array_paths: tuple[str, ...] | None = None,
) -> Iterator[tuple[Path, tuple[DownloadMember, ...]]]:
    """Validate a complete listing and publish its fully downloaded staged store."""

    members = download_manifest(files, member_sizes, total_files, total_bytes)
    if download_ready is not True:
        raise ValidationError("Hub Zarr asset is not ready for download")
    if completed_bytes is not None and completed_bytes != total_bytes:
        raise ValidationError("Hub Zarr completion size does not match its member snapshot")
    if array_paths is not None:
        admit_download_members(members, array_paths)
    validate_download_root(root)
    with staged_store(root) as staged:
        yield staged, members
        publish_staged_store(staged, root)


def publish_staged_store(staged: Path, root: Path) -> None:
    """Publish a complete staged store and restore the old root on rename failure."""

    validate_download_root(root)
    backup: Path | None = None
    if root.exists() or root.is_symlink():
        backup = root.with_name(f".{root.name}.backup-{secrets.token_hex(8)}")
        root.rename(backup)
    try:
        staged.rename(root)
    except OSError:
        if backup is not None:
            backup.rename(root)
        raise
    if backup is not None:
        try:
            if backup.is_dir() and not backup.is_symlink():
                shutil.rmtree(backup, ignore_errors=True)
            else:
                backup.unlink()
        except OSError:
            pass


def member_key(prefix: str, relative: str) -> str:
    """Object key of a local store member under an issued upload prefix."""

    return prefix + relative


def member_content_type(name: str) -> str:
    return "application/json" if name == ROOT_METADATA else "application/octet-stream"


def local_members(root: Path) -> Iterable[Path]:
    """Every file of a local store, in a stable order."""

    return sorted(path for path in root.rglob("*") if path.is_file())


def _field(payload: Mapping[str, object], key: str, modality: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value:
        raise ValidationError(f"Hub returned an invalid {modality} upload reservation")
    return value


def public_endpoint(endpoint: str, thumbnail_url: str, bucket: str) -> str:
    """Use the Hub's public MinIO presign origin when its storage origin is internal."""

    signed = urlsplit(thumbnail_url)
    internal = urlsplit(endpoint)
    if signed.scheme in ("http", "https") and signed.netloc and signed.path.startswith(f"/{bucket}/"):
        if internal.hostname == "minio" or internal.hostname == "localhost":
            return f"{signed.scheme}://{signed.netloc}"
    return endpoint


# Connect and read INACTIVITY timeouts for one storage PUT (botocore would otherwise wait 60 s each). A read timeout
# restarts whenever bytes arrive, so a transfer that keeps making progress can outlive it; this is not a limit on the
# duration of a PUT.
STORAGE_TIMEOUT_SECONDS = 30

# What an isolated session uses instead of botocore's own default where that default would itself read ambient state
# (the home directory's AWS files), where the SDK sets the policy (one attempt is configured through ``Config``), or
# where monitoring must be off.
_SESSION_VAR_DEFAULTS: dict[str, object] = {
    "config_file": os.devnull,
    "credentials_file": os.devnull,
    "retry_mode": "standard",
    "csm_enabled": False,
}


def _isolated_session_vars() -> dict[str, tuple[None, None, object, object]]:
    """Every botocore session variable with its environment and config-file providers removed.

    ``Session(session_vars=...)`` only *overrides* the variables it names, so a partial map leaves the rest reading
    the environment (``AWS_CSM_*`` client-side monitoring would send the grant's access key and session token to the
    caller's monitoring host; compression and account-endpoint settings change client construction). The map is built
    from botocore's own table, ``Session.SESSION_VARIABLES`` (the copy of ``botocore.configprovider``'s default
    variables that each session starts from, present in every botocore release), so a variable a later release adds
    is isolated without a change here. Each entry is the documented ``(config_file_key, env_vars, default,
    converter)`` tuple with the first two removed: only the default and the converter remain.
    https://docs.aws.amazon.com/botocore/latest/reference/core/session.html
    """

    from botocore.session import Session  # type: ignore[import-untyped]

    isolated = {
        name: (None, None, _SESSION_VAR_DEFAULTS.get(name, spec[2]), spec[3])
        for name, spec in Session.SESSION_VARIABLES.items()
    }
    for name, default in _SESSION_VAR_DEFAULTS.items():
        isolated.setdefault(name, (None, None, default, None))
    return isolated


def storage_client(*, region: str, endpoint: str, access_key: str, secret_key: str, token: str | None) -> Any:
    """The S3 client for one issued grant, built only from the grant and this SDK's own policy.

    The Hub's grant is the whole configuration: its region, endpoint and keys. Nothing is read from the caller's
    AWS setup, so a stale ``AWS_PROFILE``, a broken ``~/.aws/config``, ``s3.use_accelerate_endpoint``, an
    ``AWS_ENDPOINT_URL``, a CA bundle, a retry mode or a checksum setting can neither fail an upload after its
    reservation nor redirect it. Process environment variables are never modified.

    Isolation is the botocore-documented combination of (1) a private ``botocore.session.Session`` whose
    ``session_vars`` drop every environment and file provider in botocore's own variable table (https://docs.aws.amazon.com/botocore/latest/reference/core/session.html),
    (2) explicit ``botocore.config.Config`` values, which take precedence over environment and file values
    (https://docs.aws.amazon.com/botocore/latest/reference/config.html and
    https://docs.aws.amazon.com/boto3/latest/guide/configuration.html), and (3) an explicit ``endpoint_url`` and
    ``verify=True``, which the endpoint-URL environment variables and ``AWS_CA_BUNDLE`` do not override. Policy kept:
    path-style addressing, one attempt (the retry loop in :func:`upload_store` is the SDK's), SigV4, the default CA
    bundle that ships with botocore, and :data:`STORAGE_TIMEOUT_SECONDS` connect and read inactivity timeouts. Proxy variables
    (``HTTPS_PROXY``) are not AWS configuration and still apply.
    """

    import boto3  # type: ignore[import-untyped]
    from botocore.config import Config  # type: ignore[import-untyped]
    from botocore.session import Session

    options: dict[str, Any] = {
        "signature_version": "s3v4",
        "retries": {"total_max_attempts": 1, "mode": "standard"},
        "s3": {
            "addressing_style": "path",
            "use_accelerate_endpoint": False,
            "use_dualstack_endpoint": False,
            "use_arn_region": False,
            "us_east_1_regional_endpoint": "legacy",
            "s3_disable_multiregion_access_points": True,
        },
        "use_fips_endpoint": False,
        "use_dualstack_endpoint": False,
        "connect_timeout": STORAGE_TIMEOUT_SECONDS,
        "read_timeout": STORAGE_TIMEOUT_SECONDS,
    }
    # Options newer botocore releases add; an older release neither has them nor reads the matching setting.
    for name, value in (
        ("request_checksum_calculation", "when_supported"),
        ("response_checksum_validation", "when_supported"),
        ("ignore_configured_endpoint_urls", True),
    ):
        if name in Config.OPTION_DEFAULTS:
            options[name] = value
    isolated = Session(session_vars=_isolated_session_vars())
    return boto3.session.Session(botocore_session=isolated).client(
        "s3",
        region_name=region,
        endpoint_url=endpoint,
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        aws_session_token=token,
        config=Config(**options),
        verify=True,
    )


def upload_store(  # noqa: C901 - one issued grant, bounded retry
    root: Path,
    reservation: Mapping[str, object],
    modality: str = "DEPTH",
    *,
    admit: Callable[[], AbstractContextManager[None]] = nullcontext,
    cancel: threading.Event | None = None,
) -> None:
    """PUT every local member under the issued prefix; retries keep that grant.

    ``cancel`` is checked before every attempt, so once it is set no further PUT starts and the call raises
    :class:`TransportError`. A PUT already on the wire is not interrupted: it ends when it completes, fails, or
    stalls for :data:`STORAGE_TIMEOUT_SECONDS` (a connect or read inactivity timeout, so a transfer that keeps
    making progress can run longer), and no later PUT starts.

    ``modality`` (DEPTH, THERMAL or MULTISPECTRAL, the SDK's Zarr uploads) only names the
    upload in reservation and transfer errors. ``admit`` wraps each PUT attempt
    (the device persona admits each one like a Hub request); its refusal is
    raised as is, never retried. An attempt is exactly one HTTP send: boto3's
    own retries are off and a second send it starts inside one attempt (a
    region redirect, its bucket-region lookup) is refused, so every send this
    loop makes passes through ``admit``.
    """

    credentials = reservation.get("credentials")
    if not isinstance(credentials, Mapping):
        raise ValidationError(f"Hub returned an invalid {modality} upload reservation")
    grant = cast(Mapping[str, object], credentials)
    region = _field(grant, "region", modality)
    bucket = _field(grant, "bucketName", modality)
    endpoint = _field(grant, "endpoint", modality)
    access_key = _field(grant, "accessKeyId", modality)
    secret_key = _field(grant, "secretAccessKey", modality)
    prefix = _field(reservation, "key", modality).rstrip("/") + "/"
    token = grant.get("sessionToken")
    if token is not None and not isinstance(token, str):
        raise ValidationError(f"Hub returned an invalid {modality} upload reservation")
    ttl = reservation.get("expiresIn")
    if not isinstance(ttl, int) or isinstance(ttl, bool) or ttl <= 0:
        raise ValidationError(f"Hub returned an invalid {modality} upload reservation")
    deadline = time.monotonic() + ttl
    expiration = grant.get("expiration")
    if isinstance(expiration, str):
        try:
            remaining = datetime.fromisoformat(expiration.replace("Z", "+00:00")).timestamp() - time.time()
        except ValueError:
            raise ValidationError(f"Hub returned an invalid {modality} upload reservation") from None
        deadline = min(deadline, time.monotonic() + remaining)
    thumbnail_url = reservation.get("thumbnailUploadUrl")
    if isinstance(thumbnail_url, str):
        endpoint = public_endpoint(endpoint, thumbnail_url, bucket)
    endpoint = require_secure_storage_url(endpoint)
    client = storage_client(region=region, endpoint=endpoint, access_key=access_key, secret_key=secret_key, token=token)
    sent = False

    def one_send(**_: object) -> None:
        nonlocal sent
        if sent:
            raise TransportError(f"{modality} storage asked for a second request inside one attempt; it is not sent")
        sent = True

    client.meta.events.register("before-send.s3", one_send)
    for member in local_members(root):
        key = member_key(prefix, member.relative_to(root).as_posix())
        for attempt in range(2):
            if cancel is not None and cancel.is_set():
                raise TransportError(f"{modality} upload cancelled")
            if time.monotonic() >= deadline:
                raise TransportError(f"{modality} upload credentials expired; start a new upload")
            with admit():
                sent = False
                try:
                    with member.open("rb") as stream:
                        client.put_object(
                            Bucket=bucket,
                            Key=key,
                            Body=stream,
                            ContentType=member_content_type(member.name),
                        )
                    break
                except Exception:
                    if attempt == 1:
                        raise TransportError(f"{modality} Zarr member upload failed") from None
            if cancel is None:
                time.sleep(0.1)
            elif cancel.wait(0.1):
                raise TransportError(f"{modality} upload cancelled")


CHUNK_INDEX = re.compile(r"0|[1-9][0-9]*")


def bounded_codecs(codecs: object, width: int) -> bool:
    """Exactly one ``bytes`` codec, naming its byte order unless the dtype is a single byte."""

    if not isinstance(codecs, list) or len(codecs) != 1 or not isinstance(codecs[0], dict):
        return False
    configuration = codecs[0].get("configuration", {})
    if codecs[0].get("name") != "bytes" or not isinstance(configuration, dict):
        return False
    endian = configuration.get("endian")
    return endian in ("little", "big") or (endian is None and width == 1)


def bounded_array_metadata(root: Path, array_name: str) -> dict[str, object]:
    """Validate physical metadata without opening an array or fetching chunks."""

    parts = Path(array_name).parts
    documents = [root.joinpath(*parts[:depth], "zarr.json") for depth in range(len(parts) + 1)]
    document: dict[str, object] = {}
    for path in documents:
        if path.parent.is_symlink():
            raise ValueError("a metadata directory is symlinked")
        document = read_metadata_document(path)
        if path != documents[-1] and (document.get("zarr_format") != 3 or document.get("node_type") != "group"):
            raise ValueError("not a Zarr v3 group")
        if path != documents[-1]:
            validate_group_metadata(document, ignore_consolidated=True)
    if document.get("zarr_format") != 3 or document.get("node_type") != "array":
        raise ValueError("not a Zarr v3 array")
    shape, data_type = document.get("shape"), document.get("data_type")
    grid, encoding = document.get("chunk_grid") or {}, document.get("chunk_key_encoding") or {}
    chunk_shape = (grid.get("configuration") or {}).get("chunk_shape") if isinstance(grid, dict) else None
    if (
        not isinstance(grid, dict)
        or grid.get("name") != "regular"
        or not isinstance(encoding, dict)
        or encoding.get("name") != "default"
        or (encoding.get("configuration") or {}).get("separator", "/") != "/"
        or document.get("storage_transformers") not in (None, [])
    ):
        raise ValueError("unsupported chunk layout")
    violation = decode_budget_violation(shape, data_type, chunk_shape)
    if violation is not None:
        raise ValueError(f"outside the reader decode budget ({violation})")
    shape, chunk_shape = cast(list[int], shape), cast(list[int], chunk_shape)
    width = cast(int, dtype_bytes(data_type))
    if not bounded_codecs(document.get("codecs"), width):
        raise ValueError("codecs other than a lone bytes codec")
    from zarr.core.common import JSON
    from zarr.core.metadata.v3 import ArrayV3Metadata

    ArrayV3Metadata.from_dict(cast(dict[str, JSON], document))
    return document


def validate_array_chunk(parts: tuple[str, ...], size: int, document: dict[str, object]) -> None:
    shape = cast(list[int], document["shape"])
    grid = cast(dict[str, object], document["chunk_grid"])
    chunk_shape = cast(list[int], cast(dict[str, object], grid["configuration"])["chunk_shape"])
    chunk_bytes = math.prod(chunk_shape) * cast(int, dtype_bytes(document["data_type"]))
    grid_extent = [-(-extent // chunk) for extent, chunk in zip(shape, chunk_shape, strict=True)]
    if (
        len(parts) != len(shape) + 1
        or parts[0] != "c"
        or not all(CHUNK_INDEX.fullmatch(index) for index in parts[1:])
        or any(int(index) >= extent for index, extent in zip(parts[1:], grid_extent, strict=True))
        or size != chunk_bytes
    ):
        raise ValueError("a stored member is not an in-grid chunk of its decoded size")


def inspect_array_members(array_root: Path, document: dict[str, object]) -> None:
    directories = [array_root]
    members = 0
    shape = cast(list[int], document["shape"])
    grid = cast(dict[str, object], document["chunk_grid"])
    chunk_shape = cast(list[int], cast(dict[str, object], grid["configuration"])["chunk_shape"])
    grid_extent = [-(-extent // chunk) for extent, chunk in zip(shape, chunk_shape, strict=True)]
    while directories:
        with os.scandir(directories.pop()) as entries:
            for entry in entries:
                member = Path(entry.path)
                parts = member.relative_to(array_root).parts
                if entry.is_symlink():
                    raise ValueError("a stored member is symlinked")
                if entry.is_dir(follow_symlinks=False):
                    if (
                        parts[0] != "c"
                        or len(parts) > len(shape)
                        or any(
                            CHUNK_INDEX.fullmatch(index) is None or int(index) >= extent
                            for index, extent in zip(parts[1:], grid_extent, strict=False)
                        )
                    ):
                        raise ValueError("an unsupported chunk directory")
                    directories.append(member)
                    continue
                members += 1
                if members > USER_STORE_MAX_MEMBERS or not entry.is_file(follow_symlinks=False):
                    raise ValueError("a stored member is unsupported or exceeds the member limit")
                if parts != ("zarr.json",):
                    validate_array_chunk(parts, entry.stat(follow_symlinks=False).st_size, document)


def open_bounded_array(root: Path, array_name: str) -> zarr.Array[ArrayV3Metadata]:
    """Open only admitted physical metadata and chunks.

    Consolidated copies are ignored, metadata reads are capped, the codec chain
    is one bytes codec, and members are in-grid chunks of their decoded size.
    Metadata parse failures raise SDK ``ValidationError``; other unsafe store
    structures raise ``ValueError`` before any pixel buffers are allocated.
    """

    import zarr

    document = bounded_array_metadata(root, array_name)
    inspect_array_members(root / array_name, document)
    shape = cast(list[int], document["shape"])
    grid = cast(dict[str, object], document["chunk_grid"])
    chunk_shape = cast(list[int], cast(dict[str, object], grid["configuration"])["chunk_shape"])

    array = cast(
        "zarr.Array[ArrayV3Metadata]",
        zarr.open_group(str(root), mode="r", zarr_format=3, use_consolidated=False)[array_name],
    )
    if list(array.shape) != shape or list(array.chunks) != chunk_shape or array.dtype.name != document["data_type"]:
        raise ValueError("opened array disagrees with its checked metadata")
    return array
