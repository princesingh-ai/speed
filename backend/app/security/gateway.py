from app.security.authorization import authorization_service
from app.security.consent import get_consent_request
from app.task.service import task_service
from app.security.models import Permission, User
from app.security.policy import (
    AuthorizationResult,
    ResourceScope,
    RiskLevel
)


class SecurityGateway:
    """
    Central security boundary for SPEED tool execution.

    Every privileged tool operation must pass through
    this gateway before the actual tool is executed.
    """

    def authorize(
        self,
        *,
        user: User,
        permission: Permission,
        scope: ResourceScope,
        resource: str,
        reason: str,
        consent_id: str | None = None,
        task_id: str | None = None
    ) -> AuthorizationResult:

        if task_id is not None:
            task = task_service.get_task(task_id)

        if task is None:
            return AuthorizationResult(
                allowed=False,
                requires_consent=False,
                task_id=task_id,
                permission=permission,
                scope=scope,
                resource=resource,
                risk=RiskLevel.HIGH,
                reason="Task not found.",
            )

        if task.user_id != user.id:
            return AuthorizationResult(
                allowed=False,
                requires_consent=False,
                task_id=task_id,
                permission=permission,
                scope=scope,
                resource=resource,
                risk=RiskLevel.HIGH,
                reason="Task belongs to another user.",
            )

        # --------------------------------------------------
        # 1. Base authorization
        # --------------------------------------------------

        decision = authorization_service.authorize(
            user=user,
            permission=permission,
            scope=scope,
            resource=resource,
            reason=reason,
        )

        if not decision.allowed:
            return AuthorizationResult(
                allowed=False,
                requires_consent=False,
                permission=permission,
                task_id=task_id,
                scope=scope,
                resource=resource,
                risk=decision.risk,
                reason=decision.reason,
            )

        # --------------------------------------------------
        # 2. Operation does not require consent
        # --------------------------------------------------

        if not decision.requires_consent:
            return AuthorizationResult(
                allowed=True,
                requires_consent=False,
                task_id=task_id,
                permission=permission,
                scope=scope,
                resource=resource,
                risk=decision.risk,
                reason=decision.reason,
            )

        # --------------------------------------------------
        # 3. Consent required but not supplied
        # --------------------------------------------------

        if consent_id is None:
            return AuthorizationResult(
                allowed=True,
                requires_consent=True,
                permission=permission,
                scope=scope,
                task_id=task_id,
                resource=resource,
                risk=decision.risk,
                reason="This operation requires explicit user consent.",
            )

        # --------------------------------------------------
        # 4. Retrieve consent
        # --------------------------------------------------

        consent = get_consent_request(consent_id)

        if consent is None:
            return AuthorizationResult(
                allowed=False,
                requires_consent=True,
                permission=permission,
                scope=scope,
                resource=resource,
                task_id=task_id,
                risk=decision.risk,
                reason="Consent request not found.",
            )

        # --------------------------------------------------
        # 5. Consent must be approved
        # --------------------------------------------------

        if consent.status.value != "approved":
            return AuthorizationResult(
                allowed=False,
                requires_consent=True,
                consent_id=consent.id,
                permission=permission,
                task_id=task_id,
                scope=scope,
                resource=resource,
                risk=decision.risk,
                reason=(
                    f"Consent is not approved. "
                    f"Current status: {consent.status.value}."
                ),
            )

        # --------------------------------------------------
        # 6. User must match
        # --------------------------------------------------

        if consent.user_id != user.id:
            return AuthorizationResult(
                allowed=False,
                requires_consent=True,
                consent_id=consent.id,
                task_id=task_id,
                permission=permission,
                scope=scope,
                resource=resource,
                risk=decision.risk,
                reason="Consent belongs to another user.",
            )

        if consent.task_id != task_id:
            return AuthorizationResult(
                allowed=False,
                requires_consent=True,
                consent_id=consent.id,
                permission=permission,
                task_id=task_id,
                scope=scope,
                resource=resource,
                risk=decision.risk,
                reason="Consent belongs to a different task.",
        )

        # --------------------------------------------------
        # 7. Permission must match
        # --------------------------------------------------

        if consent.permission != permission:
            return AuthorizationResult(
                allowed=False,
                requires_consent=True,
                consent_id=consent.id,
                task_id=task_id,
                permission=permission,
                scope=scope,
                resource=resource,
                risk=decision.risk,
                reason=(
                    "Consent permission does not match "
                    "the requested operation."
                ),
            )

        # --------------------------------------------------
        # 8. Scope must match
        # --------------------------------------------------

        if consent.scope != scope:
            return AuthorizationResult(
                allowed=False,
                requires_consent=True,
                task_id=task_id,
                consent_id=consent.id,
                permission=permission,
                scope=scope,
                resource=resource,
                risk=decision.risk,
                reason=(
                    "Consent scope does not match "
                    "the requested operation."
                ),
            )

        # --------------------------------------------------
        # 9. Resource must match
        # --------------------------------------------------

        if consent.resource != resource:
            return AuthorizationResult(
                allowed=False,
                requires_consent=True,
                consent_id=consent.id,
                task_id=task_id,
                permission=permission,
                scope=scope,
                resource=resource,
                risk=decision.risk,
                reason=(
                    "Consent resource does not match "
                    "the requested operation."
                ),
            )

        # --------------------------------------------------
        # 10. Fully authorized
        # --------------------------------------------------

        return AuthorizationResult(
            allowed=True,
            requires_consent=False,
            consent_id=consent.id,
            task_id=task_id,
            permission=permission,
            scope=scope,
            resource=resource,
            risk=decision.risk,
            reason="Operation authorized by approved consent.",
        )


security_gateway = SecurityGateway()