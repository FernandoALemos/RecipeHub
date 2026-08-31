from core.catalog import MEASUREMENT_TYPE_CODES, UNIT_CODES
from core.ids import generate_name_id


def known_measurement_types(values: list[str]) -> list[str]:
    allowed = set(MEASUREMENT_TYPE_CODES)
    return [value for value in values if value in allowed]


def known_units(values: list[str]) -> list[str]:
    allowed = set(UNIT_CODES)
    return [value for value in values if value in allowed]


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
    db.product_categories.create_index("name_id", unique=True)
    db.recipe_categories.create_index("name_id", unique=True)
    db.products.create_index("name_id", unique=True)
