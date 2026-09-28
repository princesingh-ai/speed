import time
import uuid

from app.security.models import Permission, User
from app.security.policy import (
    ConsentRequest,
    ConsentStatus,
    ResourceScope,
    RiskLevel,
)


CONSENT_TTL_SECONDS = 10 * 60

CONSENT_REQUESTS: dict[str, ConsentRequest] = {}


def create_consent_request(
    user: User,
    permission: Permission,
    scope: ResourceScope,
    resource: str,
    reason: str,
    risk: RiskLevel,
    task_id: str | None = None,
):

    now = time.time()

    request = ConsentRequest(
        id=f"consent_{uuid.uuid4().hex}",
        user_id=user.id,
        task_id=task_id,
        permission=permission,
        scope=scope,
        resource=resource,
        reason=reason,
        risk=risk,
        status=ConsentStatus.PENDING,
        created_at=now,
        expires_at=now + CONSENT_TTL_SECONDS,
    )

    CONSENT_REQUESTS[request.id] = request

    return request


def get_consent_request(
    consent_id: str,
) -> ConsentRequest | None:

    request = CONSENT_REQUESTS.get(consent_id)

    if request is None:
        return None

    if (
        request.status in {ConsentStatus.PENDING, ConsentStatus.APPROVED}
        and time.time() > request.expires_at
    ):
        request.status = ConsentStatus.EXPIRED

    return request


def list_pending_consents(
    user_id: str,
) -> list[ConsentRequest]:

    results = []

    for request in CONSENT_REQUESTS.values():

        if request.user_id != user_id:
            continue

        current = get_consent_request(request.id)

        if (
            current
            and current.status == ConsentStatus.PENDING
        ):
            results.append(current)

    return results


def approve_consent(
    consent_id: str,
    user: User,
) -> ConsentRequest | None:

    request = get_consent_request(consent_id)

    if request is None:
        return None

    if request.user_id != user.id:
        return None

    if request.status != ConsentStatus.PENDING:
        return request

    request.status = ConsentStatus.APPROVED
    request.approved_at = time.time()
    request.approved_by = user.id

    return request


def deny_consent(
    consent_id: str,
    user: User,
) -> ConsentRequest | None:

    request = get_consent_request(consent_id)

    if request is None:
        return None

    if request.user_id != user.id:
        return None

    if request.status != ConsentStatus.PENDING:
        return request

    request.status = ConsentStatus.DENIED
    request.denied_at = time.time()

    return request
