from django.contrib.auth.hashers import check_password, make_password
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.http import Http404
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST
from pymongo.errors import DuplicateKeyError

from config.mongo import get_db
from core.notices import (
    account_created,
    account_inactive,
    created,
    email_taken,
    invalid_credentials,
    logged_in,
    logged_out,
    reactivated,
    suspended,
    updated,
    username_taken,
)
from core.store import (
    ensure_indexes,
    filters_are_active,
    list_filter_values,
    list_url_with_filters,
    matches_role,
    matches_status,
    matches_user_search,
)
from users.decorators import admin_required, login_required
from users.documents import (
    build_user_document,
    find_by_email,
    find_by_login,
    find_by_username,
    utc_now,
)
from users.permissions import (
    assignable_roles_for,
    can_change_user_role,
    can_edit_user,
    can_manage_users,
    can_suspend_user,
    can_view_user,
    resolve_create_role,
    resolve_edit_role,
    same_user,
)
from users.roles import DEFAULT_USER_ROLE, ROLE_LABELS, role_label
from users.session import clear_user_session, get_current_user, set_user_session

ROLE_FILTER_OPTIONS = tuple(ROLE_LABELS.items())


def _empty_register_form():
    return {
        "username": "",
        "email": "",
        "first_name": "",
        "last_name": "",
        "password": "",
        "confirm_password": "",
    }


def _form_from_post(post):
    return {
        "username": post.get("username", "").strip(),
        "email": post.get("email", "").strip(),
        "first_name": post.get("first_name", "").strip(),
        "last_name": post.get("last_name", "").strip(),
        "password": post.get("password", ""),
        "confirm_password": post.get("confirm_password", ""),
    }


def _admin_user_form_from_post(post):
    return {
        "username": post.get("username", "").strip(),
        "email": post.get("email", "").strip(),
        "first_name": post.get("first_name", "").strip(),
        "last_name": post.get("last_name", "").strip(),
        "password": post.get("password", ""),
        "confirm_password": post.get("confirm_password", ""),
        "role": post.get("role", DEFAULT_USER_ROLE).strip(),
    }


def _admin_user_form_from_user(user):
    return {
        "username": user.get("username", ""),
        "email": user.get("email", ""),
        "first_name": user.get("first_name", ""),
        "last_name": user.get("last_name", ""),
        "password": "",
        "confirm_password": "",
        "role": user.get("role", DEFAULT_USER_ROLE),
    }


def _safe_next_url(raw: str) -> str | None:
    if raw and raw.startswith("/") and not raw.startswith("//"):
        return raw
    return None


def _decorate_user_row(actor, user):
    role = user.get("role", DEFAULT_USER_ROLE)
    return {
        **user,
        "active": user.get("active", True),
        "role_label": role_label(role),
        "can_view": can_view_user(actor, user),
        "can_edit": can_edit_user(actor, user),
        "can_suspend": can_suspend_user(actor, user),
    }


def _validate_identity_fields(form, *, require_password: bool):
    errors = []
    if not form["username"]:
        errors.append("Username is required.")
    if not form["email"]:
        errors.append("Email is required.")
    else:
        try:
            validate_email(form["email"])
        except ValidationError:
            errors.append("Enter a valid email address.")

    password = form.get("password") or ""
    confirm = form.get("confirm_password") or ""
    if require_password or password or confirm:
        if not password:
            errors.append("Password is required.")
        if not confirm:
            errors.append("Confirm password is required.")
        elif password and password != confirm:
            errors.append("Passwords do not match.")
        elif password:
            try:
                validate_password(password)
            except ValidationError as exc:
                errors.extend(list(exc.messages))
    return errors


def _list_redirect(request):
    filters = list_filter_values(request, "role")
    return redirect(list_url_with_filters(reverse("user_list"), filters))


def register(request):
    db = get_db()
    ensure_indexes(db)
    errors = []
    form = _empty_register_form()

    if request.method == "POST":
        form = _form_from_post(request.POST)
        password = form["password"]
        confirm_password = form["confirm_password"]
        form["password"] = ""
        form["confirm_password"] = ""

        username = form["username"]
        email = form["email"]
        errors = _validate_identity_fields(
            {**form, "password": password, "confirm_password": confirm_password},
            require_password=True,
        )

        username_exists = bool(username and find_by_username(db.users, username))
        email_exists = bool(email and find_by_email(db.users, email))
        if username_exists:
            username_taken(request)
        if email_exists:
            email_taken(request)

        if not errors and not username_exists and not email_exists:
            document = build_user_document(
                username=username,
                email=email,
                password_hash=make_password(password),
                first_name=form["first_name"],
                last_name=form["last_name"],
                role=DEFAULT_USER_ROLE,
                active=True,
            )
            try:
                db.users.insert_one(document)
            except DuplicateKeyError:
                if find_by_username(db.users, username):
                    username_taken(request)
                else:
                    email_taken(request)
            else:
                account_created(request)
                return redirect("login")

    return render(
        request,
        "users/register.html",
        {
            "form": form,
            "errors": errors,
            "heading": "Create Account",
        },
    )


def login(request):
    if get_current_user(request):
        return redirect("home")

    db = get_db()
    ensure_indexes(db)
    errors = []
    form = {"identifier": "", "password": ""}
    next_url = _safe_next_url(request.GET.get("next") or request.POST.get("next") or "")

    if request.method == "POST":
        identifier = request.POST.get("identifier", "").strip()
        password = request.POST.get("password", "")
        form["identifier"] = identifier

        if not identifier:
            errors.append("Username or email is required.")
        if not password:
            errors.append("Password is required.")

        if not errors:
            user = find_by_login(db.users, identifier)
            if user is None:
                invalid_credentials(request)
            elif not user.get("active", True):
                account_inactive(request)
            elif not check_password(password, user.get("password_hash", "")):
                invalid_credentials(request)
            else:
                set_user_session(request, user)
                logged_in(request)
                return redirect(next_url or "home")

    return render(
        request,
        "users/login.html",
        {
            "form": form,
            "errors": errors,
            "heading": "Login",
            "next_url": next_url or "",
        },
    )


@require_POST
def logout(request):
    clear_user_session(request)
    logged_out(request)
    return redirect("home")


@login_required
def profile(request):
    user = get_current_user(request)
    return render(
        request,
        "users/profile.html",
        {
            "heading": "Profile",
            "profile_user": {
                **user,
                "active": user.get("active", True),
                "role_label": role_label(user.get("role")),
            },
        },
    )


@admin_required
def user_list(request):
    db = get_db()
    ensure_indexes(db)
    actor = get_current_user(request)
    filters = list_filter_values(request, "role")
    items = []
    for user in db.users.find().sort("username", 1):
        active = user.get("active", True)
        if not matches_status(active, filters["status"]):
            continue
        if not matches_role(user.get("role", DEFAULT_USER_ROLE), filters["role"]):
            continue
        if not matches_user_search(user, filters["q"]):
            continue
        items.append(_decorate_user_row(actor, user))

    return render(
        request,
        "users/list.html",
        {
            "users": items,
            "filters": filters,
            "filters_active": filters_are_active(filters),
            "clear_url": reverse("user_list"),
            "search_placeholder": "Search username, email, name…",
            "role_options": ROLE_FILTER_OPTIONS,
        },
    )


@admin_required
def user_detail(request, username):
    db = get_db()
    ensure_indexes(db)
    actor = get_current_user(request)
    user = find_by_username(db.users, username)
    if user is None or not can_view_user(actor, user):
        raise Http404("User not found.")
    return render(
        request,
        "users/detail.html",
        {
            "heading": user["username"],
            "viewed_user": _decorate_user_row(actor, user),
        },
    )


@admin_required
def user_create(request):
    db = get_db()
    ensure_indexes(db)
    actor = get_current_user(request)
    role_choices = assignable_roles_for(actor)
    errors = []
    form = {
        "username": "",
        "email": "",
        "first_name": "",
        "last_name": "",
        "password": "",
        "confirm_password": "",
        "role": DEFAULT_USER_ROLE,
    }

    if request.method == "POST":
        form = _admin_user_form_from_post(request.POST)
        password = form["password"]
        confirm = form["confirm_password"]
        form["password"] = ""
        form["confirm_password"] = ""

        errors = _validate_identity_fields(
            {**form, "password": password, "confirm_password": confirm},
            require_password=True,
        )
        role = resolve_create_role(actor, form["role"])
        if role is None:
            errors.append("Invalid role.")
        else:
            form["role"] = role

        username_exists = bool(form["username"] and find_by_username(db.users, form["username"]))
        email_exists = bool(form["email"] and find_by_email(db.users, form["email"]))
        if username_exists:
            username_taken(request)
        if email_exists:
            email_taken(request)

        if not errors and role and not username_exists and not email_exists:
            document = build_user_document(
                username=form["username"],
                email=form["email"],
                password_hash=make_password(password),
                first_name=form["first_name"],
                last_name=form["last_name"],
                role=role,
                active=True,
            )
            try:
                db.users.insert_one(document)
            except DuplicateKeyError:
                if find_by_username(db.users, form["username"]):
                    username_taken(request)
                else:
                    email_taken(request)
            else:
                created(request, "User")
                return redirect("user_list")

    return render(
        request,
        "users/form.html",
        {
            "heading": "Create User",
            "submit_label": "Create user",
            "form": form,
            "errors": errors,
            "is_edit": False,
            "role_choices": [(code, role_label(code)) for code in role_choices],
            "role_fixed": not bool(role_choices),
            "fixed_role_label": role_label(DEFAULT_USER_ROLE),
            "show_password": True,
            "password_required": True,
            "back_url": reverse("user_list"),
        },
    )


@login_required
def user_edit(request, username):
    db = get_db()
    ensure_indexes(db)
    actor = get_current_user(request)
    user = find_by_username(db.users, username)
    if user is None:
        raise Http404("User not found.")
    if not can_edit_user(actor, user):
        return redirect("home")

    editing_self = same_user(actor, user)
    can_set_role = can_change_user_role(actor, user)
    role_choices = assignable_roles_for(actor) if can_set_role else ()
    errors = []
    form = _admin_user_form_from_user(user)

    if request.method == "POST":
        form = _admin_user_form_from_post(request.POST)
        password = form["password"]
        confirm = form["confirm_password"]
        form["password"] = ""
        form["confirm_password"] = ""

        errors = _validate_identity_fields(
            {**form, "password": password, "confirm_password": confirm},
            require_password=False,
        )
        next_role = resolve_edit_role(
            actor,
            user,
            form["role"],
            user.get("role", DEFAULT_USER_ROLE),
        )
        if next_role is None:
            errors.append("Invalid role.")
        else:
            form["role"] = next_role

        username_exists = bool(
            form["username"]
            and find_by_username(db.users, form["username"], exclude_id=user["_id"])
        )
        email_exists = bool(
            form["email"] and find_by_email(db.users, form["email"], exclude_id=user["_id"])
        )
        if username_exists:
            username_taken(request)
        if email_exists:
            email_taken(request)

        if not errors and next_role and not username_exists and not email_exists:
            updates = {
                "username": form["username"],
                "email": form["email"],
                "first_name": form["first_name"],
                "last_name": form["last_name"],
                "role": next_role,
                "updated_at": utc_now(),
            }
            if password:
                updates["password_hash"] = make_password(password)
            try:
                db.users.update_one({"_id": user["_id"]}, {"$set": updates})
            except DuplicateKeyError:
                if find_by_username(db.users, form["username"], exclude_id=user["_id"]):
                    username_taken(request)
                else:
                    email_taken(request)
            else:
                if editing_self:
                    refreshed = db.users.find_one({"_id": user["_id"]})
                    set_user_session(request, refreshed)
                updated(request, "User")
                if editing_self and not can_manage_users(actor):
                    return redirect("profile")
                return redirect("user_detail", username=form["username"])

    return render(
        request,
        "users/form.html",
        {
            "heading": f"Edit {user['username']}",
            "submit_label": "Save user",
            "form": form,
            "errors": errors,
            "is_edit": True,
            "role_choices": [(code, role_label(code)) for code in role_choices],
            "role_fixed": not can_set_role,
            "fixed_role_label": role_label(user.get("role")),
            "show_password": True,
            "password_required": False,
            "editing_self": editing_self,
            "back_url": (
                reverse("profile")
                if editing_self and not can_manage_users(actor)
                else reverse("user_detail", args=[user["username"]])
            ),
        },
    )


@admin_required
@require_POST
def user_set_active(request, username):
    db = get_db()
    ensure_indexes(db)
    actor = get_current_user(request)
    user = find_by_username(db.users, username)
    if user is None:
        raise Http404("User not found.")
    if not can_suspend_user(actor, user):
        return _list_redirect(request)

    active = request.POST.get("active") == "1"
    db.users.update_one(
        {"_id": user["_id"]},
        {"$set": {"active": active, "updated_at": utc_now()}},
    )
    if active:
        reactivated(request, "User")
    else:
        suspended(request, "User")
    return _list_redirect(request)
