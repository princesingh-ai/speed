from app.security.consent import create_consent_request
from app.security.models import Permission, User
from app.security.policy import (
    AuthorizationDecision,
    ResourceScope,
)
from app.security.policies import evaluate_policy
from app.security.store import get_user_permissions


class AuthorizationService:

    def authorize(
        self,
        user: User,
        permission: Permission,
        scope: ResourceScope,
        resource: str,
        reason: str,
    ) -> AuthorizationDecision:

        # 1. RBAC

        permissions = get_user_permissions(user)

        if permission not in permissions:
            return AuthorizationDecision(
                allowed=False,
                requires_consent=False,
                permission=permission,
                scope=scope,
                risk="high",
                reason=(
                    f"User does not have permission "
                    f"{permission.value}."
                ),
            )

        # 2. Policy

        (
            allowed,
            requires_consent,
            risk,
            policy_reason,
        ) = evaluate_policy(
            permission,
            scope,
        )

        if not allowed:
            return AuthorizationDecision(
                allowed=False,
                requires_consent=False,
                permission=permission,
                scope=scope,
                risk=risk,
                reason=policy_reason,
            )

        # 3. Consent

        return AuthorizationDecision(
            allowed=True,
            requires_consent=requires_consent,
            permission=permission,
            scope=scope,
            risk=risk,
            reason=policy_reason,
        )

    def request_consent(
        self,
        user,
        permission,
        scope,
        resource,
        reason,
        task_id: str | None = None,
    ):
        allowed, requires_consent, risk, policy_reason = evaluate_policy(
            permission,
            scope,
        )

        if not allowed:
            raise PermissionError(policy_reason)

        if not requires_consent:
            raise ValueError("This operation does not require consent.")

        return create_consent_request(
            user=user,
            permission=permission,
            scope=scope,
            resource=resource,
            reason=reason,
            risk=risk,
            task_id=task_id,
        )

authorization_service = AuthorizationService()