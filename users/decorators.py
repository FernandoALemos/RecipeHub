from functools import wraps

from django.contrib import messages
from django.shortcuts import redirect
from django.urls import reverse

from users.permissions import is_staff, is_super_admin
from users.session import get_current_user


def login_required(view):
    """Require a RecipeHub Mongo session user (not Django auth)."""

    @wraps(view)
    def wrapper(request, *args, **kwargs):
        if get_current_user(request) is None:
            login_url = reverse("login")
            return redirect(f"{login_url}?next={request.get_full_path()}")
        return view(request, *args, **kwargs)

    return wrapper


def admin_required(view):
    """Require admin or super_admin (catalog staff / user list)."""

    @wraps(view)
    @login_required
    def wrapper(request, *args, **kwargs):
        user = get_current_user(request)
        if not is_staff(user):
            messages.error(request, "Admin access required.")
            return redirect("home")
        return view(request, *args, **kwargs)

    return wrapper


def super_admin_required(view):
    """Require the unique Super Admin role."""

    @wraps(view)
    @login_required
    def wrapper(request, *args, **kwargs):
        user = get_current_user(request)
        if not is_super_admin(user):
            messages.error(request, "Super Admin access required.")
            return redirect("home")
        return view(request, *args, **kwargs)

    return wrapper
