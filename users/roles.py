USER_ROLES = (
    "user",
    "admin",
    "super_admin",
)

DEFAULT_USER_ROLE = "user"
STAFF_ROLES = ("admin", "super_admin")
# Roles that may be assigned through the UI / create forms.
ASSIGNABLE_ROLES = (
    "user",
    "admin",
)

ROLE_LABELS = {
    "user": "User",
    "admin": "Admin",
    "super_admin": "Super Admin",
}


def role_label(role: str) -> str:
    return ROLE_LABELS.get(role, role or "User")
