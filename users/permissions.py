"""RecipeHub authorization helpers (Mongo session users).

Hierarchy: user < admin < super_admin

Catalog:
  guest  — read
  user   — create/edit products & recipes (always born active)
  admin / super_admin — categories, suspend catalog, manage users

User administration differences live mainly between admin and super_admin.
"""

from users.roles import ASSIGNABLE_ROLES, DEFAULT_USER_ROLE, STAFF_ROLES


def is_logged_in(user) -> bool:
    return user is not None


def user_role(user) -> str:
    if not user:
        return ""
    return user.get("role") or DEFAULT_USER_ROLE


def is_user(user) -> bool:
    return user_role(user) == "user"


def is_admin(user) -> bool:
    """Exact role == admin (not super_admin)."""
    return user_role(user) == "admin"


def is_super_admin(user) -> bool:
    return user_role(user) == "super_admin"


def is_staff(user) -> bool:
    """Admin or Super Admin — catalog staff and user-list access."""
    return user_role(user) in STAFF_ROLES


def same_user(actor, target) -> bool:
    if not actor or not target:
        return False
    return actor.get("_id") == target.get("_id")


def can_mutate_catalog(user) -> bool:
    """Create/edit products and recipes (any authenticated user)."""
    return is_logged_in(user)


def can_manage_categories(user) -> bool:
    return is_staff(user)


def can_manage_active(user) -> bool:
    """Suspend/reactivate catalog items."""
    return is_staff(user)


def can_manage_users(user) -> bool:
    """Access /users/ list and basic user admin."""
    return is_staff(user)


def can_view_user(actor, target) -> bool:
    if not target:
        return False
    if same_user(actor, target):
        return True
    return is_staff(actor)


def can_edit_user(actor, target) -> bool:
    """Personal fields (and role when allowed separately)."""
    if not actor or not target:
        return False
    if same_user(actor, target):
        return True
    if is_super_admin(target):
        return False
    if is_admin(target):
        return is_super_admin(actor)
    # target is a normal user
    return is_staff(actor)


def can_change_user_role(actor, target) -> bool:
    """Only Super Admin may set user ↔ admin. Never on self or Super Admin."""
    if not is_super_admin(actor) or not target:
        return False
    if same_user(actor, target):
        return False
    if is_super_admin(target):
        return False
    return True


def can_suspend_user(actor, target) -> bool:
    if not actor or not target:
        return False
    if same_user(actor, target):
        return False
    if is_super_admin(target):
        return False
    if is_admin(target):
        return is_super_admin(actor)
    return is_staff(actor)


def assignable_roles_for(actor) -> tuple[str, ...]:
    """Roles the actor may choose when creating/editing someone else."""
    if is_super_admin(actor):
        return ASSIGNABLE_ROLES
    return ()


def resolve_create_role(actor, posted_role: str) -> str | None:
    """
    Return the role to store on create, or None if the posted role is illegal.
    Admin always creates users. Super Admin may choose user|admin.
    """
    if is_super_admin(actor):
        if posted_role in ASSIGNABLE_ROLES:
            return posted_role
        return None
    if is_staff(actor):
        return DEFAULT_USER_ROLE
    return None


def resolve_edit_role(actor, target, posted_role: str, existing_role: str) -> str | None:
    """
    Return the role to store on edit, or None if illegal.
    Self-edit and non-SA keep existing role. SA may set user|admin on others.
    """
    if not can_change_user_role(actor, target):
        return existing_role
    if posted_role not in ASSIGNABLE_ROLES:
        return None
    return posted_role


def resolve_active_on_create() -> bool:
    """Products/recipes always start active; never trust the form."""
    return True


def resolve_active_on_edit(user, posted_active: bool, existing_active: bool) -> bool:
    """Only staff may change catalog active; others keep the stored value."""
    if can_manage_active(user):
        return bool(posted_active)
    return bool(existing_active)
