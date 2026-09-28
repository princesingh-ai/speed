from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.security.authorization import authorization_service
from app.security.dependencies import get_current_user, require_permission
from app.security.models import Permission, User
from app.security.policy import ResourceScope
from app.security.gateway import security_gateway

router = APIRouter(
    prefix="/api/v1/security",
    tags=["security"],
)

class AuthorizationTestRequest(BaseModel):
    permission: Permission
    scope: ResourceScope
    resource: str
    reason: str = "Security gateway test."
    consent_id: str | None = None
    task_id: str | None = None


@router.get("/test/file-read")
async def test_file_read(
    user: User = Depends(
        require_permission(Permission.FILE_READ)
    ),
):
    return {
        "status": "allowed",
        "user": user.username,
        "permission": Permission.FILE_READ.value,
    }


@router.get("/test/sandbox")
async def test_sandbox(
    user: User = Depends(
        require_permission(Permission.SANDBOX_EXECUTE)
    ),
):
    return {
        "status": "allowed",
        "user": user.username,
        "permission": Permission.SANDBOX_EXECUTE.value,
    }


@router.post("/test/device-scan")
async def test_device_scan(
    task_id: str,
    user: User = Depends(get_current_user),
    consent_id: str | None = None):
    
    permission = Permission.FILE_SCAN_DEVICE
    scope = ResourceScope.DEVICE
    resource = "/"

    decision = security_gateway.authorize(
        user=user,
        task_id=task_id,
        permission=permission,
        scope=scope,
        resource=resource,
        reason=(
            "Search the entire device for documents "
            "relevant to the current task."
        ),
        consent_id=consent_id,
    )

    if not decision.allowed:
        return {
            "status": "denied",
            "decision": decision,
        }

    if decision.requires_consent:
        consent = authorization_service.request_consent(
            user=user,
            task_id=task_id,
            permission=permission,
            scope=scope,
            resource=resource,
            reason=(
                "Search the entire device for documents "
                "relevant to the current task."
            ),
        )

        return {
            "status": "waiting_for_consent",
            "decision": decision,
            "consent": consent,
        }

    return {
        "status": "authorized",
        "decision": decision,
    }


@router.post("/test/authorize")
async def test_authorize(
    request: AuthorizationTestRequest,
    user: User = Depends(get_current_user),
):
    decision = security_gateway.authorize(
    user=user,
    task_id=request.task_id,
    permission=request.permission,
    scope=request.scope,
    resource=request.resource,
    reason=request.reason,
    consent_id=request.consent_id,
)

    return {
        "status": (
            "authorized"
            if decision.allowed and not decision.requires_consent
            else "denied"
            if not decision.allowed
            else "waiting_for_consent"
        ),
        "decision": decision,
    }