from enum import Enum

from pydantic import BaseModel, Field

from app.security.models import Permission, User


class ResourceScope(str, Enum):
    UPLOADED_FILE = "uploaded_file"
    WORKSPACE = "workspace"
    PROJECT = "project"
    HOME = "home"
    DEVICE = "device"


class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class AuthorizationDecision(BaseModel):
    allowed: bool
    requires_consent: bool = False
    permission: Permission
    scope: ResourceScope
    risk: RiskLevel
    reason: str

class AuthorizationResult(BaseModel):
    allowed: bool
    requires_consent: bool
    consent_id: str | None = None
    task_id: str | None = None

    permission: Permission
    scope: ResourceScope
    resource: str
    risk: RiskLevel

    reason: str

class ConsentStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    DENIED = "denied"
    EXPIRED = "expired"
    REVOKED = "revoked"


class ConsentRequest(BaseModel):
    id: str
    user_id: str

    task_id: str | None = None

    permission: Permission
    scope: ResourceScope
    resource: str
    reason: str

    risk: RiskLevel

    status: ConsentStatus = ConsentStatus.PENDING

    created_at: float
    expires_at: float

    approved_at: float | None = None
    denied_at: float | None = None
    approved_by: str | None = None