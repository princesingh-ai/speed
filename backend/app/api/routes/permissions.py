from fastapi import APIRouter, Depends, HTTPException

from app.security.consent import (
    approve_consent,
    deny_consent,
    list_pending_consents,
)
from app.security.dependencies import get_current_user
from app.security.models import User


router = APIRouter(
    prefix="/api/v1/permissions",
    tags=["permissions"],
)


@router.get("/pending")
async def pending_permissions(
    user: User = Depends(get_current_user),
):
    return {
        "requests": list_pending_consents(user.id),
    }


@router.post("/{consent_id}/approve")
async def approve_permission(
    consent_id: str,
    user: User = Depends(get_current_user),
):

    request = approve_consent(
        consent_id,
        user,
    )

    if request is None:
        raise HTTPException(
            status_code=404,
            detail="Permission request not found.",
        )

    return request


@router.post("/{consent_id}/deny")
async def deny_permission(
    consent_id: str,
    user: User = Depends(get_current_user),
):

    request = deny_consent(
        consent_id,
        user,
    )

    if request is None:
        raise HTTPException(
            status_code=404,
            detail="Permission request not found.",
        )

    return request