"""Resolve product_categories by name_id, then insert products with category_id."""

import sys
from pathlib import Path

from pymongo import MongoClient
from pymongo.errors import DuplicateKeyError

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.ids import generate_name_id
from core.store import ensure_indexes
from initial_products import PRODUCTS

MONGO_URI = "mongodb://127.0.0.1:27017"
DB_NAME = "recipe_hub"


def build_documents(db):
    documents = []
    for seed in PRODUCTS:
        category_name_id = seed["category_name_id"]
        category = db.product_categories.find_one({"name_id": category_name_id})
        if category is None:
            raise SystemExit(
                f"No existe product_category con name_id={category_name_id!r} "
                f"(producto {seed['name']!r})"
            )

        document = {key: value for key, value in seed.items() if key != "category_name_id"}
        document["name_id"] = generate_name_id(seed["name"])
        document["category_id"] = category["_id"]
        documents.append(document)
    return documents


def main() -> None:
    client = MongoClient(MONGO_URI)
    db = client[DB_NAME]
    ensure_indexes(db)
    collection = db.products

    documents = build_documents(db)
    existing = {doc["name_id"] for doc in collection.find({}, {"name_id": 1, "_id": 0})}
    to_insert = [doc for doc in documents if doc["name_id"] not in existing]

    if to_insert:
        result = collection.insert_many(to_insert)
        print(f"Insertados {len(result.inserted_ids)} products:")
        for doc in to_insert:
            print(f"  + {doc['name_id']:24} {doc['name']}")
    else:
        print("No hay products nuevos para insertar.")

    print(f"\nTotal en {DB_NAME}.products: {collection.count_documents({})}")
    pipeline = [
        {
            "$lookup": {
                "from": "product_categories",
                "localField": "category_id",
                "foreignField": "_id",
                "as": "category",
            }
        },
        {"$unwind": "$category"},
        {"$sort": {"category.name_id": 1, "name": 1}},
        {
            "$project": {
                "_id": 0,
                "name": 1,
                "name_id": 1,
                "default_unit": 1,
                "category": "$category.name",
                "category_name_id": "$category.name_id",
            }
        },
    ]
    for doc in collection.aggregate(pipeline):
        print(f"  {doc['category_name_id']:24} {doc['name']:22} {doc['default_unit']}")
    client.close()


if __name__ == "__main__":
    try:
        main()
    except DuplicateKeyError as exc:
        raise SystemExit(f"name_id duplicado: {exc}") from exc
