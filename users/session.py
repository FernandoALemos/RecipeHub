"""Session helpers for RecipeHub MongoDB users.

We store only ``user_id`` (string ObjectId) in the Django session.
The full user document is loaded from Mongo when needed.
"""

from bson import ObjectId
from bson.errors import InvalidId

from config.mongo import get_db

SESSION_USER_ID_KEY = "user_id"


def set_user_session(request, user) -> None:
    request.session[SESSION_USER_ID_KEY] = str(user["_id"])
    request.session.cycle_key()


def clear_user_session(request) -> None:
    request.session.pop(SESSION_USER_ID_KEY, None)
    request.session.cycle_key()


def get_session_user_id(request):
    return request.session.get(SESSION_USER_ID_KEY)


def get_current_user(request):
    """Return the Mongo user for this session, or None."""
    user_id = get_session_user_id(request)
    if not user_id:
        return None
    try:
        oid = ObjectId(user_id)
    except (InvalidId, TypeError):
        clear_user_session(request)
        return None

    user = get_db().users.find_one({"_id": oid})
    if user is None or not user.get("active", True):
        clear_user_session(request)
        return None
    return user
