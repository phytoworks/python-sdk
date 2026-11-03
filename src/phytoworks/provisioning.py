"""Advisory provisioning checks derived from the selected organization's access info."""

from __future__ import annotations

from typing import Literal, TypedDict

from .models import AccessInfo

ProvisioningResult = Literal["allowed", "denied", "unknown"]


class ProvisioningCheck(TypedDict):
    operation: Literal["SPOT_CREATE", "AGENT_CREATE", "DEVICE_KEY_ISSUE"]
    result: ProvisioningResult
    requiredPermissions: list[list[str]]
    currentRole: str | None


_ACTION_GRANTS = {
    "CREATE": ("CREATE", "MANAGE", "ALL"),
    "UPDATE": ("UPDATE", "CONTROL", "MANAGE", "ALL"),
    "CONTROL": ("CONTROL", "MANAGE", "ALL"),
    "MANAGE": ("MANAGE", "ALL"),
    "ALL": ("ALL",),
}


def _grant_options(resource: str, action: str) -> tuple[str, ...]:
    return tuple(f"{resource}:{granted}" for granted in _ACTION_GRANTS[action])


def _single_permission_alternatives(resources: tuple[str, ...], action: str) -> tuple[tuple[str, ...], ...]:
    return tuple((permission,) for resource in resources for permission in _grant_options(resource, action))


def _and_permission_alternatives(
    resource: str, action: str, dependencies: tuple[tuple[str, str], ...]
) -> tuple[tuple[str, ...], ...]:
    return tuple(
        (grant, dependency)
        for grant in _grant_options(resource, action)
        for dependency_resource, dependency_action in dependencies
        for dependency in _grant_options(dependency_resource, dependency_action)
    )


_ORGANIZATION_MANAGE = _single_permission_alternatives(("organization", "system"), "MANAGE")
_REQUIRED_PERMISSIONS: tuple[tuple[tuple[str, ...], ...], ...] = (
    _ORGANIZATION_MANAGE + _single_permission_alternatives(("spot",), "CREATE"),
    _ORGANIZATION_MANAGE
    + _and_permission_alternatives("agent", "CREATE", (("spot", "UPDATE"), ("organization", "UPDATE"))),
    _single_permission_alternatives(("agent", "spot", "organization", "system"), "MANAGE"),
)


def _permission_set(access_info: AccessInfo) -> set[tuple[str, str]]:
    permissions: set[tuple[str, str]] = set()
    for value in access_info.organization_permissions or []:
        resource, separator, action = value.partition(":")
        if separator and resource and action:
            permissions.add((resource.casefold(), action.upper()))
    return permissions


def _allows(permissions: set[tuple[str, str]], required: str) -> bool:
    resource, action = required.split(":", 1)
    return any((resource, granted_action) in permissions for granted_action in _ACTION_GRANTS[action])


def check_provisioning(access_info: AccessInfo) -> list[ProvisioningCheck]:
    """Summarize visible grants without replacing Hub authorization on a later write."""

    permissions = _permission_set(access_info)
    system_super_admin = access_info.system_role == "system_super_admin"
    organization_manage = _allows(permissions, "organization:MANAGE") or _allows(permissions, "system:MANAGE")
    agent_create = _allows(permissions, "agent:CREATE")
    spot_update = _allows(permissions, "spot:UPDATE") or _allows(permissions, "organization:UPDATE")
    spot_create = system_super_admin or organization_manage or _allows(permissions, "spot:CREATE")

    if system_super_admin or organization_manage or (agent_create and spot_update):
        agent_result: ProvisioningResult = "allowed"
    elif not organization_manage and not agent_create:
        agent_result = "denied"
    else:
        agent_result = "unknown"

    device_key_result: ProvisioningResult = (
        "allowed"
        if system_super_admin
        or any(_allows(permissions, required) for group in _REQUIRED_PERMISSIONS[2] for required in group)
        else "unknown"
    )
    current_role = access_info.organization_role

    return [
        {
            "operation": "SPOT_CREATE",
            "result": "allowed" if spot_create else "denied",
            "requiredPermissions": [list(group) for group in _REQUIRED_PERMISSIONS[0]],
            "currentRole": current_role,
        },
        {
            "operation": "AGENT_CREATE",
            "result": agent_result,
            "requiredPermissions": [list(group) for group in _REQUIRED_PERMISSIONS[1]],
            "currentRole": current_role,
        },
        {
            "operation": "DEVICE_KEY_ISSUE",
            "result": device_key_result,
            "requiredPermissions": [list(group) for group in _REQUIRED_PERMISSIONS[2]],
            "currentRole": current_role,
        },
    ]
