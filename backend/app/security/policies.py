from app.security.models import Permission
from app.security.policy import (
    ResourceScope,
    RiskLevel,
)


def evaluate_policy(
    permission: Permission,
    scope: ResourceScope,
) -> tuple[bool, bool, RiskLevel, str]:
    """
    Returns:

    allowed,
    requires_consent,
    risk,
    reason
    """

    # External network access is disabled by default.
    if permission == Permission.NETWORK_EXTERNAL:
        return (
            False,
            False,
            RiskLevel.CRITICAL,
            "External network access is disabled by default.",
        )

    # Entire-device scanning is highly privileged.
    if permission == Permission.FILE_SCAN_DEVICE:
        if scope != ResourceScope.DEVICE:
            return (
                False,
                False,
                RiskLevel.HIGH,
                "Device scanning requires device scope.",
            )

        return (
            True,
            True,
            RiskLevel.HIGH,
            "Scanning the entire device requires explicit user consent.",
        )

    # Deleting files always requires explicit consent.
    if permission == Permission.FILE_DELETE:
        return (
            True,
            True,
            RiskLevel.HIGH,
            "File deletion requires explicit user consent.",
        )

    # Sandbox execution is considered high risk.
    if permission == Permission.SANDBOX_EXECUTE:
        return (
            True,
            True,
            RiskLevel.HIGH,
            "Sandbox execution requires explicit user consent.",
        )

    # Agent spawning can create additional autonomous activity.
    if permission == Permission.AGENT_SPAWN:
        return (
            True,
            True,
            RiskLevel.HIGH,
            "Spawning an agent requires explicit user consent.",
        )

    # External MCP access is privileged.
    if permission == Permission.MCP_USE:
        return (
            True,
            True,
            RiskLevel.MEDIUM,
            "Using an MCP server requires explicit user consent.",
        )

    # Ordinary workspace/file operations.
    if permission in {
        Permission.FILE_LIST,
        Permission.FILE_READ,
        Permission.FILE_WRITE,
        Permission.DOCUMENT_READ,
        Permission.DOCUMENT_CREATE,
        Permission.CHAT_USE,
    }:
        return (
            True,
            False,
            RiskLevel.LOW,
            "Operation is permitted under the current policy.",
        )

    # Internal network communication is allowed.
    if permission == Permission.NETWORK_INTERNAL:
        return (
            True,
            False,
            RiskLevel.LOW,
            "Internal network communication is permitted.",
        )

    return (
        False,
        False,
        RiskLevel.MEDIUM,
        "No policy explicitly permits this operation.",
    )