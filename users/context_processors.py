from users.permissions import (
    can_manage_active,
    can_manage_categories,
    can_manage_users,
    can_mutate_catalog,
    is_admin,
    is_logged_in,
    is_staff,
    is_super_admin,
)
from users.session import get_current_user


def recipehub_user(request):
    """Expose session user and permission flags to all templates."""
    user = get_current_user(request)
    return {
        "current_user": user,
        "is_logged_in": is_logged_in(user),
        "is_admin": is_admin(user),
        "is_staff": is_staff(user),
        "is_super_admin": is_super_admin(user),
        "can_mutate_catalog": can_mutate_catalog(user),
        "can_manage_categories": can_manage_categories(user),
        "can_manage_active": can_manage_active(user),
        "can_manage_users": can_manage_users(user),
    }
