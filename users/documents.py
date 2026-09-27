"""RecipeHub users live in MongoDB, not in Django's auth_user table.

Passwords are stored only as Django password hashes (`password_hash`).
Public Register always creates role=user.
Admins are promoted via make_admin; the unique Super Admin via make_super_admin.
"""

from datetime import datetime, timezone

from users.roles import DEFAULT_USER_ROLE, USER_ROLES


def utc_now():
    return datetime.now(timezone.utc)


def normalize_username(username: str) -> str:
    return (username or "").strip()


def normalize_email(email: str) -> str:
    return (email or "").strip().lower()


def is_valid_role(role: str) -> bool:
    return role in USER_ROLES


def build_user_document(
    *,
    username: str,
    email: str,
    password_hash: str,
    first_name: str = "",
    last_name: str = "",
    role: str = DEFAULT_USER_ROLE,
    active: bool = True,
    now=None,
) -> dict:
    """Build a users document ready for MongoDB insert.

    Expected shape:
    {
        "username": "fernando",
        "email": "fernando@example.com",
        "password_hash": "pbkdf2_sha256$...",
        "first_name": "Fernando",
        "last_name": "Lemos",
        "role": "user",
        "active": True,
        "created_at": datetime(...),
        "updated_at": datetime(...),
    }
    """
    if role not in USER_ROLES:
        raise ValueError(f"Unknown role: {role}")
    if not password_hash:
        raise ValueError("password_hash is required.")

    stamp = now or utc_now()
    return {
        "username": normalize_username(username),
        "email": normalize_email(email),
        "password_hash": password_hash,
        "first_name": (first_name or "").strip(),
        "last_name": (last_name or "").strip(),
        "role": role,
        "active": bool(active),
        "created_at": stamp,
        "updated_at": stamp,
    }


def find_by_username(collection, username: str, exclude_id=None):
    query = {"username": normalize_username(username)}
    if exclude_id is not None:
        query["_id"] = {"$ne": exclude_id}
    return collection.find_one(query)


def find_by_email(collection, email: str, exclude_id=None):
    query = {"email": normalize_email(email)}
    if exclude_id is not None:
        query["_id"] = {"$ne": exclude_id}
    return collection.find_one(query)


def find_by_login(collection, identifier: str):
    """Find a user by username or email (both unique)."""
    raw = (identifier or "").strip()
    if not raw:
        return None
    return collection.find_one(
        {
            "$or": [
                {"username": normalize_username(raw)},
                {"email": normalize_email(raw)},
            ]
        }
    )
