from urllib.parse import urlencode

from core.catalog import MEASUREMENT_TYPE_CODES, UNIT_CODES
from core.ids import generate_name_id


def known_measurement_types(values: list[str]) -> list[str]:
    allowed = set(MEASUREMENT_TYPE_CODES)
    return [value for value in values if value in allowed]


def known_units(values: list[str]) -> list[str]:
    allowed = set(UNIT_CODES)
    return [value for value in values if value in allowed]


STATUS_FILTERS = ("all", "active", "inactive")


def status_filter(request) -> str:
    raw = request.POST.get("status") or request.GET.get("status") or "all"
    return raw if raw in STATUS_FILTERS else "all"


def matches_status(active: bool, status: str) -> bool:
    if status == "active":
        return bool(active)
    if status == "inactive":
        return not active
    return True


def request_param(request, name: str, default: str = "") -> str:
    raw = request.POST.get(name)
    if raw is None:
        raw = request.GET.get(name)
    if raw is None:
        return default
    return raw.strip()


def request_param_list(request, name: str) -> list[str]:
    """Collect repeated or comma-separated query/post values, de-duplicated."""
    values = list(request.POST.getlist(name))
    if not values:
        values = list(request.GET.getlist(name))
    cleaned: list[str] = []
    seen: set[str] = set()
    for raw in values:
        for part in str(raw).split(","):
            item = part.strip()
            if item and item not in seen:
                seen.add(item)
                cleaned.append(item)
    return cleaned


def search_query(request) -> str:
    return request_param(request, "q")


def contains_ci(text: str, query: str) -> bool:
    if not query:
        return True
    return query.casefold() in (text or "").casefold()


def matches_user_search(user, query: str) -> bool:
    if not query:
        return True
    return any(
        contains_ci(user.get(field, ""), query)
        for field in ("username", "email", "first_name", "last_name")
    )


def matches_role(role: str, role_filter: str) -> bool:
    if not role_filter:
        return True
    return (role or "") == role_filter


def matches_ingredients_filter(
    recipe_product_name_ids: set[str] | list[str],
    selected_name_ids: list[str],
    mode: str,
) -> bool:
    """Filter recipes by selected product name_ids.

    mode ``all``: recipe must contain every selected ingredient.
    mode ``any``: recipe must contain at least one selected ingredient.
    """
    if not selected_name_ids:
        return True
    selected = set(selected_name_ids)
    present = selected & set(recipe_product_name_ids)
    if mode == "any":
        return bool(present)
    return selected <= set(recipe_product_name_ids)


INGREDIENT_MATCH_FILTERS = ("all", "any")


def ingredient_match_filter(request) -> str:
    raw = request_param(request, "ingredient_match", "all")
    return raw if raw in INGREDIENT_MATCH_FILTERS else "all"


def matches_any_text(query: str, *texts: str) -> bool:
    if not query:
        return True
    return any(contains_ci(text, query) for text in texts)


def matches_name_search(name: str, query: str) -> bool:
    return contains_ci(name, query)


def matches_category_search(category, query: str) -> bool:
    return matches_any_text(query, category.get("name", ""), category.get("description", ""))


def matches_product_search(product, query: str) -> bool:
    if not query:
        return True
    if contains_ci(product.get("name", ""), query):
        return True
    return any(contains_ci(alias, query) for alias in product.get("aliases", []))


def matches_tag_filter(tags, selected: str) -> bool:
    if not selected:
        return True
    selected_key = selected.casefold()
    return any((tag or "").casefold() == selected_key for tag in tags or [])


def parse_max_minutes(raw: str):
    value = (raw or "").strip()
    if not value:
        return None
    try:
        number = int(value)
    except ValueError:
        return None
    return number if number > 0 else None


def matches_max_minutes(actual, maximum) -> bool:
    if maximum is None:
        return True
    if actual is None:
        return False
    try:
        return int(actual) <= int(maximum)
    except (TypeError, ValueError):
        return False


TIME_FILTER_OPTIONS = [
    ("15", "15 min"),
    ("30", "30 min"),
    ("45", "45 min"),
    ("60", "60 min"),
    ("90", "90 min"),
    ("120", "120 min"),
]


def list_filter_values(request, *names: str) -> dict[str, str]:
    values = {"q": search_query(request), "status": status_filter(request)}
    for name in names:
        values[name] = request_param(request, name)
    return values


def _filter_value_is_default(key: str, value, defaults: dict) -> bool:
    if isinstance(value, (list, tuple)):
        return len(value) == 0
    return value == defaults.get(key, "")


def filters_are_active(filters: dict, defaults: dict | None = None) -> bool:
    defaults = defaults or {"status": "all", "ingredient_match": "all"}
    for key, value in filters.items():
        if not value:
            continue
        if _filter_value_is_default(key, value, defaults):
            continue
        return True
    return False


def filters_querystring(filters: dict, defaults: dict | None = None) -> str:
    defaults = defaults or {"status": "all", "ingredient_match": "all"}
    params = []
    for key, value in filters.items():
        if not value:
            continue
        if _filter_value_is_default(key, value, defaults):
            continue
        if isinstance(value, (list, tuple)):
            for item in value:
                if item:
                    params.append((key, item))
        else:
            params.append((key, value))
    return urlencode(params)


def list_url_with_filters(base_url: str, filters: dict) -> str:
    query = filters_querystring(filters)
    return f"{base_url}?{query}" if query else base_url


def find_by_name_id(collection, name_id: str, exclude_id=None):
    query = {"name_id": name_id}
    if exclude_id is not None:
        query["_id"] = {"$ne": exclude_id}
    return collection.find_one(query)


def _drop_index_quietly(collection, *index_names: str) -> None:
    existing = collection.index_information()
    for index_name in index_names:
        if index_name in existing:
            collection.drop_index(index_name)


def _migrate_name_id(collection) -> None:
    for document in collection.find():
        name_id = generate_name_id(document.get("name", ""))
        updates = {"$set": {"name_id": name_id}}
        unset_fields = {}
        if "slug" in document:
            unset_fields["slug"] = ""
        if "name_key" in document:
            unset_fields["name_key"] = ""
        if unset_fields:
            updates["$unset"] = unset_fields
        collection.update_one({"_id": document["_id"]}, updates)


def ensure_indexes(db) -> None:
    _drop_index_quietly(db.product_categories, "slug_1")
    _drop_index_quietly(db.products, "name_key_1", "name_1")
    _migrate_name_id(db.product_categories)
    _migrate_name_id(db.recipe_categories)
    _migrate_name_id(db.products)
    _migrate_name_id(db.recipes)
    db.product_categories.create_index("name_id", unique=True)
    db.recipe_categories.create_index("name_id", unique=True)
    db.products.create_index("name_id", unique=True)
    db.recipes.create_index("name_id", unique=True)
    db.users.create_index("username", unique=True)
    db.users.create_index("email", unique=True)
