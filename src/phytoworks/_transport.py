"""Small sync/async HTTP transport shared by every facade resource."""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import os
import re
import secrets
import time
from collections.abc import AsyncIterator, Awaitable, Callable, Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from importlib import metadata
from pathlib import Path
from typing import BinaryIO, TypeVar, cast, overload
from urllib.parse import urlsplit

import httpx
from httpx._types import QueryParamTypes

from .config import (
    ALLOW_INSECURE_HUB_ENV,
    _allow_insecure_http,
    _is_secure_origin,
)
from .errors import TransportError, ValidationError, error_from_http

T = TypeVar("T")
_IDEMPOTENT_METHODS = frozenset({"DELETE", "GET", "HEAD", "OPTIONS", "PUT"})
_DOWNLOAD_CHUNK = 1 << 16
# ponytail: retain at most 65,536 error bytes; HTTPX may read one extra network chunk.
# Use a lower-level bounded read API only if a strict network byte cap is required.
_DOWNLOAD_ERROR_CAP = 64 * 1024

ProgressCallback = Callable[[int, int | None], None]
"""``on_progress(bytes_done, total_bytes_or_None)`` invoked after every written chunk."""


@dataclass(frozen=True, slots=True)
class Pagination:
    page: int | None = None
    limit: int | None = None
    total: int | None = None
    total_pages: int | None = None
    offset: int | None = None
    next_cursor: str | None = None
    has_next: bool | None = None

    @classmethod
    def from_payload(cls, payload: object) -> Pagination:
        if not isinstance(payload, Mapping):
            return cls()
        return cls(
            page=_as_int(payload.get("page")),
            limit=_as_int(payload.get("limit")),
            total=_as_int(payload.get("total")),
            total_pages=_as_int(payload.get("totalPages", payload.get("total_pages"))),
            offset=_as_int(payload.get("offset")),
            next_cursor=_as_str(payload.get("nextCursor", payload.get("next_cursor"))),
            has_next=_as_bool(payload.get("hasNext", payload.get("has_next"))),
        )


@dataclass(slots=True)
class Page[T](Iterable[T]):
    """A page that is iterable and can lazily load a next page."""

    items: list[T]
    pagination: Pagination = Pagination()
    meta: Mapping[str, object] | None = None
    _next: Callable[[], Page[T] | None] | None = None
    _anext: Callable[[], Awaitable[Page[T] | None]] | None = None
    _total_limit: int | None = None

    def __iter__(self) -> Iterator[T]:
        current: Page[T] | None = self
        remaining = self._total_limit
        while current is not None:
            for item in current.items:
                if remaining is not None:
                    if remaining <= 0:
                        return
                    remaining -= 1
                yield item
            if remaining == 0:
                return
            current = current._next() if current._next is not None else None

    async def __aiter__(self) -> AsyncIterator[T]:
        current: Page[T] | None = self
        remaining = self._total_limit
        while current is not None:
            for item in current.items:
                if remaining is not None:
                    if remaining <= 0:
                        return
                    remaining -= 1
                yield item
            if remaining == 0:
                return
            current = await current._anext() if current._anext is not None else None

    def __len__(self) -> int:
        return len(self.items)

    @overload
    def __getitem__(self, index: int) -> T: ...

    @overload
    def __getitem__(self, index: slice) -> list[T]: ...

    def __getitem__(self, index: int | slice) -> T | list[T]:
        return self.items[index]


def _as_int(value: object) -> int | None:
    return int(value) if isinstance(value, (int, float, str)) and str(value).strip() else None


def _as_str(value: object) -> str | None:
    return value if isinstance(value, str) else None


def _as_bool(value: object) -> bool | None:
    return value if isinstance(value, bool) else None


_logger = logging.getLogger(__name__)


class _RedactSignedQuery(logging.Filter):
    """Drop the query of a signed storage URL from httpx log arguments; the request itself keeps it."""

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.args, tuple):
            record.args = tuple(
                arg.copy_with(query=None)
                if isinstance(arg, httpx.URL) and any(key.lower() == "x-amz-signature" for key in arg.params)
                else arg
                for arg in record.args
            )
        return True


# httpx logs every request URL, query included, at INFO. A filter on its named logger is process-wide,
# but it rewrites only presigned (SigV4) URL arguments; other query diagnostics stay as they are.
logging.getLogger("httpx").addFilter(_RedactSignedQuery())


def _rate_limited(delay: float) -> float:
    """Announce a 429 wait (the CLI prints it on stderr) so a retry never looks like a hang."""

    _logger.warning("the Hub rate-limited this request (HTTP 429); retrying in %ss", f"{delay:g}")
    return delay


def _parse_retry_after(value: str | None) -> float | None:
    if value is None:
        return None
    try:
        return max(0.0, float(value))
    except ValueError:
        return None


def _is_retryable_method(method: str) -> bool:
    return method.upper() in _IDEMPOTENT_METHODS


def _unwrap_payload(payload: object, *, meta: Mapping[str, object] | None = None) -> object:
    if not isinstance(payload, Mapping):
        return payload
    if payload.get("success") is True and "data" in payload:
        data = payload["data"]
        pagination = payload.get("pagination")
        if isinstance(data, list) and pagination is not None:
            return Page(
                items=list(data),
                pagination=Pagination.from_payload(pagination),
                meta=cast(Mapping[str, object] | None, payload.get("meta", meta)),
            )
        return data
    if "data" in payload and set(payload).issubset({"data", "meta", "pagination", "success"}):
        data = payload["data"]
        if isinstance(data, list) and "pagination" in payload:
            return Page(
                items=list(data),
                pagination=Pagination.from_payload(payload.get("pagination")),
                meta=cast(Mapping[str, object] | None, payload.get("meta", meta)),
            )
        return data
    return payload


def _check_download_cap(written: int, max_bytes: int | None) -> None:
    if max_bytes is not None and written > max_bytes:
        raise ValidationError(f"downloaded object exceeds its {max_bytes}-byte read cap")


def _check_download_deadline(deadline: float | None) -> None:
    # ponytail: check between body chunks; header/framing trickle can overshoot by up to the
    # HTTP parser's incomplete-event limit times the idle timeout (~+8.7 s measured).
    # Use a cancellable transport if a tighter expiry bound becomes necessary.
    if deadline is not None and time.monotonic() >= deadline:
        raise TransportError("presigned download exceeded its deadline")


def _download_error_message(body: bytes | bytearray) -> str:
    # Only a bounded code or these fixed legacy diagnostics can leave storage.
    code = re.search(rb"<Code>\s*([A-Za-z][A-Za-z0-9]{0,127})\s*</Code>", body)
    if code is not None:
        return f"presigned download failed ({code[1].decode('ascii')})"
    if body.strip() == b"SignatureDoesNotMatch":
        return "presigned download failed (SignatureDoesNotMatch)"
    if body.strip() == b"storage unavailable" or re.search(rb'"message"\s*:\s*"storage unavailable"', body):
        return "presigned download failed (storage unavailable)"
    return "presigned download failed"


def _read_download_error(response: httpx.Response, deadline: float | None) -> str:
    if response.is_stream_consumed:
        return _download_error_message(response.content[:_DOWNLOAD_ERROR_CAP])
    body = bytearray()
    for chunk in response.iter_raw():
        _check_download_deadline(deadline)
        body.extend(chunk[: _DOWNLOAD_ERROR_CAP - len(body)])
        if len(body) == _DOWNLOAD_ERROR_CAP:
            break
    _check_download_deadline(deadline)
    return _download_error_message(body)


async def _aread_download_error(response: httpx.Response, deadline: float | None) -> str:
    if response.is_stream_consumed:
        return _download_error_message(response.content[:_DOWNLOAD_ERROR_CAP])
    body = bytearray()
    async for chunk in response.aiter_raw():
        _check_download_deadline(deadline)
        body.extend(chunk[: _DOWNLOAD_ERROR_CAP - len(body)])
        if len(body) == _DOWNLOAD_ERROR_CAP:
            break
    _check_download_deadline(deadline)
    return _download_error_message(body)


def require_secure_storage_url(url: str) -> str:
    """Reject unsafe storage URLs; the explicit development switch allows remote HTTP outside production."""

    try:
        parsed = urlsplit(url)
        _ = parsed.port
    except ValueError as exc:
        raise ValidationError("storage URL has an invalid authority") from exc
    if parsed.username is not None or parsed.password is not None:
        raise ValidationError("storage URL must not contain userinfo")
    if not parsed.hostname:
        raise ValidationError("storage URL must include a host")
    if _is_secure_origin(parsed.scheme, parsed.hostname):
        return url
    if _allow_insecure_http(
        url,
        resource="use a production storage URL",
        warning_resource="presigned storage URL",
        error_type=ValidationError,
    ):
        return url
    if parsed.scheme == "http":
        raise ValidationError(
            f"storage URL must use HTTPS or loopback HTTP (or set {ALLOW_INSECURE_HUB_ENV}=1 / "
            "--allow-insecure-hub for a development host)"
        )
    raise ValidationError("storage URL must use HTTPS or loopback HTTP")


def _refuse_content_encoding(response: httpx.Response) -> None:
    # httpx would inflate the whole body before any cap sees it; objects are stored unencoded.
    encoding = response.headers.get("Content-Encoding", "identity").strip().lower()
    if encoding != "identity":
        raise ValidationError(f"downloaded object carries Content-Encoding {encoding!r}; only identity is read")


def _installed_version() -> str:
    try:
        return metadata.version("phytoworks")
    except metadata.PackageNotFoundError:
        return "0+unknown"


def _default_user_agent() -> str:
    return f"phytoworks/{_installed_version()}"


class Transport:
    """Synchronous HTTPX transport with bounded retry and envelope handling."""

    def __init__(
        self,
        base_url: str,
        *,
        client: httpx.Client | None = None,
        timeout: float | httpx.Timeout = 30.0,
        max_retries: int = 2,
        retry_backoff: float = 0.25,
        user_agent: str | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.max_retries = max(0, max_retries)
        self.retry_backoff = max(0.0, retry_backoff)
        self.user_agent = user_agent if user_agent is not None else _default_user_agent()
        self._client = client or httpx.Client(timeout=timeout)
        self._owns_client = client is None

    def __repr__(self) -> str:
        return f"Transport(base_url={self.base_url!r}, timeout={self.timeout!r}, max_retries={self.max_retries!r})"

    def request_raw(
        self,
        method: str,
        path: str,
        *,
        headers: Mapping[str, str] | None = None,
        params: Mapping[str, object] | Sequence[tuple[str, object]] | None = None,
        json_body: object | None = None,
    ) -> httpx.Response:
        request_headers = {"User-Agent": self.user_agent, **(headers or {})}
        url = f"{self.base_url}/{path.lstrip('/')}"
        for attempt in range(self.max_retries + 1):
            try:
                response = self._client.request(
                    method,
                    url,
                    headers=request_headers,
                    params=cast(QueryParamTypes | None, params),
                    json=json_body,
                    timeout=self.timeout,
                    follow_redirects=False,
                )
            except httpx.HTTPError as exc:
                if not _is_retryable_method(method) or attempt >= self.max_retries:
                    raise TransportError(str(exc)) from exc
                self._sleep(attempt)
                continue
            if response.status_code == 429:
                retry_after = _parse_retry_after(response.headers.get("Retry-After"))
                if _is_retryable_method(method) and attempt < self.max_retries:
                    time.sleep(
                        _rate_limited(retry_after if retry_after is not None else self.retry_backoff * (2**attempt))
                    )
                    continue
            if _is_retryable_method(method) and response.status_code >= 500 and attempt < self.max_retries:
                self._sleep(attempt)
                continue
            return response
        raise AssertionError("unreachable")

    def request(
        self,
        method: str,
        path: str,
        *,
        headers: Mapping[str, str] | None = None,
        params: Mapping[str, object] | Sequence[tuple[str, object]] | None = None,
        json_body: object | None = None,
    ) -> object:
        response = self.request_raw(method, path, headers=headers, params=params, json_body=json_body)
        payload = _response_payload(response)
        if response.status_code >= 400:
            retry_after = _parse_retry_after(response.headers.get("Retry-After"))
            raise error_from_http(
                response.status_code, payload, retry_after=retry_after, request_id=response.headers.get("X-Request-Id")
            )
        return _unwrap_payload(payload)

    def download_request(
        self,
        method: str,
        path: str,
        target: Path,
        *,
        headers: Mapping[str, str] | None = None,
        params: Mapping[str, object] | Sequence[tuple[str, object]] | None = None,
        json_body: object | None = None,
        on_progress: ProgressCallback | None = None,
        expected_content_type: str | None = None,
    ) -> int:
        """Stream an authenticated API response to ``target`` atomically."""

        request_headers = {"User-Agent": self.user_agent, **(headers or {})}
        url = f"{self.base_url}/{path.lstrip('/')}"
        target.parent.mkdir(parents=True, exist_ok=True)
        for attempt in range(self.max_retries + 1):
            try:
                with self._client.stream(
                    method,
                    url,
                    headers=request_headers,
                    params=cast(QueryParamTypes | None, params),
                    json=json_body,
                    timeout=self.timeout,
                    follow_redirects=False,
                ) as response:
                    retry_delay = _stream_retry_delay(
                        response,
                        method=method,
                        attempt=attempt,
                        max_retries=self.max_retries,
                        backoff=self.retry_backoff,
                    )
                    if retry_delay is not None:
                        time.sleep(retry_delay)
                        continue
                    if response.status_code >= 400:
                        payload = _payload_from_bytes(response.read())
                        raise error_from_http(
                            response.status_code,
                            payload,
                            retry_after=_parse_retry_after(response.headers.get("Retry-After")),
                            request_id=response.headers.get("X-Request-Id"),
                        )
                    _validate_content_type(response, expected_content_type)
                    with atomic_binary_writer(target) as handle:
                        return _write_stream_response(response, handle, on_progress=on_progress)
            except httpx.HTTPError as exc:
                if not _is_retryable_method(method) or attempt >= self.max_retries:
                    raise TransportError(str(exc)) from exc
                self._sleep(attempt)
        raise AssertionError("unreachable")

    def download(
        self,
        url: str,
        target: Path,
        *,
        on_progress: ProgressCallback | None = None,
        expected_content_type: str | None = None,
        max_bytes: int | None = None,
        deadline: float | None = None,
    ) -> int:
        """Stream a presigned object URL into ``target`` and return the byte count.

        The URL carries its own signature, so no SDK header is sent. Bytes go to
        a sibling temp file and are renamed on success. ``max_bytes`` bounds the
        object size. HTTPX retains its configured per-read idle timeout. An absolute
        ``deadline`` is checked between streamed body chunks; header/chunk-framing
        trickle can overshoot by up to the HTTP parser's incomplete-event limit times the
        idle timeout (about +8.7 s in the gate measurement).
        Error diagnostic samples are capped at 64 KiB; HTTPX may consume one
        extra network chunk. Only a safe diagnostic is exposed, never the body.
        """

        require_secure_storage_url(url)
        _check_download_deadline(deadline)
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            with self._client.stream("GET", url, timeout=self.timeout, follow_redirects=False) as response:
                _check_download_deadline(deadline)
                _refuse_content_encoding(response)
                if not 200 <= response.status_code < 300:
                    if response.status_code < 400:
                        raise TransportError("presigned download failed", status_code=response.status_code)
                    _validate_error_content_type(response, expected_content_type)
                    raise error_from_http(response.status_code, _read_download_error(response, deadline))
                _validate_content_type(response, expected_content_type)
                total = _content_length(response)
                written = 0
                with atomic_binary_writer(target) as handle:
                    for chunk in response.iter_raw():
                        _check_download_deadline(deadline)
                        written += len(chunk)
                        _check_download_cap(written, max_bytes)
                        handle.write(chunk)
                        if on_progress is not None:
                            on_progress(written, total)
                    _check_download_deadline(deadline)
        except httpx.TimeoutException:
            failure = "presigned download timed out"
        except httpx.HTTPError:
            failure = "presigned download failed"
        else:
            return written
        raise TransportError(failure) from None

    def upload(self, url: str, source: Path, *, content_type: str) -> None:
        """Stream an SDK-staged file (a private temporary path) through :meth:`upload_opened`."""

        require_secure_storage_url(url)
        try:
            with source.open("rb") as handle:
                self.upload_opened(url, handle, size=os.fstat(handle.fileno()).st_size, content_type=content_type)
        except OSError:
            raise TransportError("presigned upload failed") from None

    def upload_opened(self, url: str, source: BinaryIO, *, size: int, content_type: str) -> None:
        """Stream an already open object of ``size`` bytes to its presigned URL without operator credentials."""

        require_secure_storage_url(url)
        try:
            response = self._client.put(
                url,
                content=iter(lambda: source.read(_DOWNLOAD_CHUNK), b""),
                headers={"Content-Type": content_type, "Content-Length": str(size)},
                timeout=self.timeout,
                follow_redirects=False,
            )
        except (httpx.HTTPError, OSError):
            raise TransportError("presigned upload failed") from None
        if not 200 <= response.status_code < 300:
            raise TransportError("presigned upload failed", status_code=response.status_code)

    def _sleep(self, attempt: int) -> None:
        if self.retry_backoff:
            time.sleep(self.retry_backoff * (2**attempt))

    def close(self) -> None:
        if self._owns_client:
            self._client.close()


class AsyncTransport:
    """Async twin of :class:`Transport` with the same wire contract."""

    def __init__(
        self,
        base_url: str,
        *,
        client: httpx.AsyncClient | None = None,
        timeout: float = 30.0,
        max_retries: int = 2,
        retry_backoff: float = 0.25,
        user_agent: str | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.max_retries = max(0, max_retries)
        self.retry_backoff = max(0.0, retry_backoff)
        self.user_agent = user_agent if user_agent is not None else _default_user_agent()
        self._client = client or httpx.AsyncClient(timeout=timeout)
        self._owns_client = client is None

    def __repr__(self) -> str:
        return f"AsyncTransport(base_url={self.base_url!r}, timeout={self.timeout!r}, max_retries={self.max_retries!r})"

    async def request_raw(
        self,
        method: str,
        path: str,
        *,
        headers: Mapping[str, str] | None = None,
        params: Mapping[str, object] | Sequence[tuple[str, object]] | None = None,
        json_body: object | None = None,
    ) -> httpx.Response:
        request_headers = {"User-Agent": self.user_agent, **(headers or {})}
        url = f"{self.base_url}/{path.lstrip('/')}"
        for attempt in range(self.max_retries + 1):
            try:
                response = await self._client.request(
                    method,
                    url,
                    headers=request_headers,
                    params=cast(QueryParamTypes | None, params),
                    json=json_body,
                    timeout=self.timeout,
                    follow_redirects=False,
                )
            except httpx.HTTPError as exc:
                if not _is_retryable_method(method) or attempt >= self.max_retries:
                    raise TransportError(str(exc)) from exc
                await self._sleep(attempt)
                continue
            if response.status_code == 429:
                retry_after = _parse_retry_after(response.headers.get("Retry-After"))
                if _is_retryable_method(method) and attempt < self.max_retries:
                    await _async_sleep(
                        _rate_limited(retry_after if retry_after is not None else self.retry_backoff * (2**attempt))
                    )
                    continue
            if _is_retryable_method(method) and response.status_code >= 500 and attempt < self.max_retries:
                await self._sleep(attempt)
                continue
            return response
        raise AssertionError("unreachable")

    async def request(
        self,
        method: str,
        path: str,
        *,
        headers: Mapping[str, str] | None = None,
        params: Mapping[str, object] | Sequence[tuple[str, object]] | None = None,
        json_body: object | None = None,
    ) -> object:
        response = await self.request_raw(method, path, headers=headers, params=params, json_body=json_body)
        payload = _response_payload(response)
        if response.status_code >= 400:
            retry_after = _parse_retry_after(response.headers.get("Retry-After"))
            raise error_from_http(
                response.status_code, payload, retry_after=retry_after, request_id=response.headers.get("X-Request-Id")
            )
        return _unwrap_payload(payload)

    async def download_request(
        self,
        method: str,
        path: str,
        target: Path,
        *,
        headers: Mapping[str, str] | None = None,
        params: Mapping[str, object] | Sequence[tuple[str, object]] | None = None,
        json_body: object | None = None,
        on_progress: ProgressCallback | None = None,
        expected_content_type: str | None = None,
    ) -> int:
        """Async twin of :meth:`Transport.download_request`."""

        request_headers = {"User-Agent": self.user_agent, **(headers or {})}
        url = f"{self.base_url}/{path.lstrip('/')}"
        target.parent.mkdir(parents=True, exist_ok=True)
        for attempt in range(self.max_retries + 1):
            try:
                async with self._client.stream(
                    method,
                    url,
                    headers=request_headers,
                    params=cast(QueryParamTypes | None, params),
                    json=json_body,
                    timeout=self.timeout,
                    follow_redirects=False,
                ) as response:
                    retry_delay = _stream_retry_delay(
                        response,
                        method=method,
                        attempt=attempt,
                        max_retries=self.max_retries,
                        backoff=self.retry_backoff,
                    )
                    if retry_delay is not None:
                        await _async_sleep(retry_delay)
                        continue
                    if response.status_code >= 400:
                        body = await response.aread()
                        payload = _payload_from_bytes(body)
                        raise error_from_http(
                            response.status_code,
                            payload,
                            retry_after=_parse_retry_after(response.headers.get("Retry-After")),
                            request_id=response.headers.get("X-Request-Id"),
                        )
                    _validate_content_type(response, expected_content_type)
                    with atomic_binary_writer(target) as handle:
                        return await _awrite_stream_response(response, handle, on_progress=on_progress)
            except httpx.HTTPError as exc:
                if not _is_retryable_method(method) or attempt >= self.max_retries:
                    raise TransportError(str(exc)) from exc
                await self._sleep(attempt)
        raise AssertionError("unreachable")

    async def download(
        self,
        url: str,
        target: Path,
        *,
        on_progress: ProgressCallback | None = None,
        expected_content_type: str | None = None,
        max_bytes: int | None = None,
        deadline: float | None = None,
    ) -> int:
        """Async twin of :meth:`Transport.download`."""

        require_secure_storage_url(url)
        _check_download_deadline(deadline)
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            async with self._client.stream("GET", url, timeout=self.timeout, follow_redirects=False) as response:
                _check_download_deadline(deadline)
                _refuse_content_encoding(response)
                if not 200 <= response.status_code < 300:
                    if response.status_code < 400:
                        raise TransportError("presigned download failed", status_code=response.status_code)
                    _validate_error_content_type(response, expected_content_type)
                    raise error_from_http(response.status_code, await _aread_download_error(response, deadline))
                _validate_content_type(response, expected_content_type)
                total = _content_length(response)
                written = 0
                with atomic_binary_writer(target) as handle:
                    async for chunk in response.aiter_raw():
                        _check_download_deadline(deadline)
                        written += len(chunk)
                        _check_download_cap(written, max_bytes)
                        handle.write(chunk)
                        if on_progress is not None:
                            on_progress(written, total)
                    _check_download_deadline(deadline)
        except httpx.TimeoutException:
            failure = "presigned download timed out"
        except httpx.HTTPError:
            failure = "presigned download failed"
        else:
            return written
        raise TransportError(failure) from None

    async def upload(self, url: str, source: Path, *, content_type: str) -> None:
        """Async twin of :meth:`Transport.upload`."""

        require_secure_storage_url(url)
        try:
            with source.open("rb") as handle:
                await self.upload_opened(url, handle, size=os.fstat(handle.fileno()).st_size, content_type=content_type)
        except OSError:
            raise TransportError("presigned upload failed") from None

    async def upload_opened(self, url: str, source: BinaryIO, *, size: int, content_type: str) -> None:
        """Async twin of :meth:`Transport.upload_opened`."""

        require_secure_storage_url(url)

        async def chunks() -> AsyncIterator[bytes]:
            while chunk := await asyncio.to_thread(source.read, _DOWNLOAD_CHUNK):
                yield chunk

        try:
            response = await self._client.put(
                url,
                content=chunks(),
                headers={"Content-Type": content_type, "Content-Length": str(size)},
                timeout=self.timeout,
                follow_redirects=False,
            )
        except (httpx.HTTPError, OSError):
            raise TransportError("presigned upload failed") from None
        if not 200 <= response.status_code < 300:
            raise TransportError("presigned upload failed", status_code=response.status_code)

    async def _sleep(self, attempt: int) -> None:
        await _async_sleep(self.retry_backoff * (2**attempt))

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()


async def _async_sleep(delay: float) -> None:
    if delay <= 0:
        return
    import asyncio

    await asyncio.sleep(delay)


def _stream_retry_delay(
    response: httpx.Response,
    *,
    method: str,
    attempt: int,
    max_retries: int,
    backoff: float,
) -> float | None:
    if attempt >= max_retries or not _is_retryable_method(method):
        return None
    if response.status_code == 429:
        retry_after = _parse_retry_after(response.headers.get("Retry-After"))
        return _rate_limited(retry_after if retry_after is not None else backoff * (2.0**attempt))
    if response.status_code >= 500:
        return backoff * (2.0**attempt)
    return None


@contextlib.contextmanager
def atomic_binary_writer(target: Path) -> Iterator[BinaryIO]:
    """Write ``target`` through a fresh random sibling and publish it with one rename.

    The sibling is created exclusively and never through a symlink, so a link
    planted at a predictable name (another local user in a shared directory)
    cannot redirect the bytes.  Mode ``0o666`` keeps the umask in charge, as a
    plain ``open("wb")`` did; a failure removes only this call's sibling.
    """

    staged = target.with_name(f".{target.name}.{secrets.token_hex(8)}.part")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0)
    descriptor = os.open(staged, flags, 0o666)
    try:
        handle = os.fdopen(descriptor, "wb")
        descriptor = -1  # the stream owns it now
        with handle:
            yield handle
        os.replace(staged, target)
    except BaseException:
        if descriptor >= 0:
            os.close(descriptor)
        staged.unlink(missing_ok=True)
        raise


def _write_stream_response(
    response: httpx.Response,
    handle: BinaryIO,
    *,
    on_progress: ProgressCallback | None,
) -> int:
    total = _content_length(response)
    written = 0
    for chunk in response.iter_bytes(_DOWNLOAD_CHUNK):
        handle.write(chunk)
        written += len(chunk)
        if on_progress is not None:
            on_progress(written, total)
    return written


async def _awrite_stream_response(
    response: httpx.Response,
    handle: BinaryIO,
    *,
    on_progress: ProgressCallback | None,
) -> int:
    total = _content_length(response)
    written = 0
    async for chunk in response.aiter_bytes(_DOWNLOAD_CHUNK):
        handle.write(chunk)
        written += len(chunk)
        if on_progress is not None:
            on_progress(written, total)
    return written


def _content_length(response: httpx.Response) -> int | None:
    value = response.headers.get("Content-Length")
    try:
        return int(value) if value is not None else None
    except ValueError:
        return None


def _validate_content_type(response: httpx.Response, expected: str | None) -> None:
    if expected is None:
        return
    expected_type = expected.split(";", 1)[0].strip().lower()
    actual_header = response.headers.get("Content-Type", "")
    actual_type = actual_header.split(";", 1)[0].strip().lower()
    if expected_type == "application/octet-stream":
        # Zarr members are opaque storage objects; reject error documents without
        # coupling downloads to backend-specific binary MIME labels.
        if actual_type in {"text/html", "application/xhtml+xml", "application/xml", "text/xml"} or actual_type.endswith(
            "+xml"
        ):
            actual = actual_type or "<missing>"
            raise TransportError(f"unexpected response content type {actual!r}; expected binary content")
        return
    if actual_type != expected_type:
        actual = actual_type or "<missing>"
        raise TransportError(f"unexpected response content type {actual!r}; expected {expected_type!r}")


def _validate_error_content_type(response: httpx.Response, expected: str | None) -> None:
    content_type = response.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
    if content_type in {"application/xml", "text/xml"}:
        _validate_content_type(response, expected)


def _response_payload(response: httpx.Response) -> object:
    if response.status_code == 204 or not response.content:
        return None
    try:
        return response.json()
    except (json.JSONDecodeError, UnicodeDecodeError):
        return response.text


def _payload_from_bytes(body: bytes) -> object:
    if not body:
        return None
    try:
        return json.loads(body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return body.decode("utf-8", "replace")
