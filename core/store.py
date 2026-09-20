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


def search_query(request) -> str:
    return request_param(request, "q")


def contains_ci(text: str, query: str) -> bool:
    if not query:
        return True
    return query.casefold() in (text or "").casefold()


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


def filters_are_active(filters: dict[str, str], defaults: dict[str, str] | None = None) -> bool:
    defaults = defaults or {"status": "all"}
    for key, value in filters.items():
        if not value:
            continue
        if value != defaults.get(key, ""):
            return True
    return False


def filters_querystring(filters: dict[str, str], defaults: dict[str, str] | None = None) -> str:
    defaults = defaults or {"status": "all"}
    params = []
    for key, value in filters.items():
        if not value:
            continue
        if value == defaults.get(key, ""):
            continue
        params.append((key, value))
    return urlencode(params)


def list_url_with_filters(base_url: str, filters: dict[str, str]) -> str:
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
