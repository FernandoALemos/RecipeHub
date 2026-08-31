"""Load initial recipe_categories. name_id is generated from name."""

import sys
from pathlib import Path

from pymongo import MongoClient
from pymongo.errors import DuplicateKeyError

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.ids import generate_name_id
from core.store import ensure_indexes
from recipe_categories import RECIPE_CATEGORIES

MONGO_URI = "mongodb://127.0.0.1:27017"
DB_NAME = "recipe_hub"
COLLECTION = "recipe_categories"


def main() -> None:
    client = MongoClient(MONGO_URI)
    db = client[DB_NAME]
    ensure_indexes(db)
    collection = db[COLLECTION]

    existing = {doc["name_id"] for doc in collection.find({}, {"name_id": 1, "_id": 0})}
    to_insert = []
    for category in RECIPE_CATEGORIES:
        name_id = generate_name_id(category["name"])
        if name_id in existing:
            continue
        to_insert.append(
            {
                "name": category["name"],
                "name_id": name_id,
                "description": category["description"],
                "active": category["active"],
            }
        )

    if to_insert:
        result = collection.insert_many(to_insert)
        print(f"Insertados {len(result.inserted_ids)} documentos nuevos:")
        for category in to_insert:
            print(f"  + {category['name_id']:24} {category['name']}")
    else:
        print("No hay categorías nuevas para insertar.")

    print(f"\nTotal en {DB_NAME}.{COLLECTION}: {collection.count_documents({})}")
    for doc in collection.find({}, {"name": 1, "name_id": 1}).sort("name_id", 1):
        print(f"  {doc['name_id']:24} {doc['name']}")
    client.close()


if __name__ == "__main__":
    try:
        main()
    except DuplicateKeyError as exc:
        raise SystemExit(f"name_id duplicado: {exc}") from exc
