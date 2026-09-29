# temp RBAC store

from pwdlib import PasswordHash

from app.security.models import Permission, Role, User


password_hash = PasswordHash.recommended()


ROLES: dict[str, Role] = {
    "user": Role(
        name="user",
        permissions={
            Permission.CHAT_USE,
            Permission.FILE_LIST,
            Permission.FILE_READ,
            Permission.FILE_WRITE,
            Permission.DOCUMENT_READ,
            Permission.DOCUMENT_CREATE,
        },
    ),
    "developer": Role(
        name="developer",
        permissions={
            Permission.CHAT_USE,
            Permission.FILE_LIST,
            Permission.FILE_READ,
            Permission.FILE_WRITE,
            Permission.FILE_DELETE,
            Permission.DOCUMENT_READ,
            Permission.DOCUMENT_CREATE,
            Permission.SANDBOX_CREATE,
            Permission.SANDBOX_EXECUTE,
            Permission.AGENT_EXECUTE,
            Permission.MCP_USE,
            Permission.NETWORK_INTERNAL,
        },
    ),
    "admin": Role(
        name="admin",
        permissions=set(Permission),
    ),
}


USERS: dict[str, User] = {
    # Deliberate development account; replace this store before production use.
    "admin": User(
        id="user-admin",
        username="admin",
        password_hash=password_hash.hash("admin-password"),
        roles=["admin"],
    ),
    "prince": User(
        id="user-prince",
        username="prince",
        password_hash=password_hash.hash("change-me"),
        roles=["admin"],
    ),
    "testuser": User(
        id="user-test",
        username="testuser",
        password_hash=password_hash.hash("test-password"),
        roles=["user"],
    ),
}


def get_user(username: str) -> User | None:
    return USERS.get(username)


def get_role(name: str) -> Role | None:
    return ROLES.get(name)


def verify_password(
    plain_password: str,
    hashed_password: str,
) -> bool:
    return password_hash.verify(
        plain_password,
        hashed_password,
    )


def get_user_permissions(user: User) -> set[Permission]:
    permissions: set[Permission] = set()

    for role_name in user.roles:
        role = get_role(role_name)

        if role:
            permissions.update(role.permissions)

    return permissions
