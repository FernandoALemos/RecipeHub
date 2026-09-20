import json
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from config.mongo import get_client
from core.store import ensure_indexes


class Command(BaseCommand):
    help = (
        "Import RecipeHub collections from data/*.json. "
        "Resolves portable name_id references into ObjectIds."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--database",
            default=None,
            help="MongoDB database name (default: settings.MONGO_DB_NAME).",
        )
        parser.add_argument(
            "--input-dir",
            default=None,
            help="Directory with JSON files (default: <BASE_DIR>/data).",
        )
        parser.add_argument(
            "--clear",
            action="store_true",
            help="Drop target collections before importing.",
        )

    def handle(self, *args, **options):
        data_dir = Path(options["input_dir"] or (Path(settings.BASE_DIR) / "data"))
        db_name = options["database"] or settings.MONGO_DB_NAME
        db = get_client()[db_name]

        files = {
            "product_categories": data_dir / "product_categories.json",
            "recipe_categories": data_dir / "recipe_categories.json",
            "products": data_dir / "products.json",
            "recipes": data_dir / "recipes.json",
        }
        missing = [str(path) for path in files.values() if not path.exists()]
        if missing:
            raise CommandError(
                "Missing export files:\n  " + "\n  ".join(missing)
            )

        product_categories = self.read_json(files["product_categories"])
        recipe_categories = self.read_json(files["recipe_categories"])
        products = self.read_json(files["products"])
        recipes = self.read_json(files["recipes"])

        if options["clear"]:
            for name in (
                "recipes",
                "products",
                "recipe_categories",
                "product_categories",
            ):
                db[name].drop()
            self.stdout.write(f"Cleared collections in `{db_name}`.")

        ensure_indexes(db)

        product_category_ids = self.import_categories(
            db.product_categories,
            product_categories,
            "product category",
        )
        recipe_category_ids = self.import_categories(
            db.recipe_categories,
            recipe_categories,
            "recipe category",
        )
        product_ids = self.import_products(
            db.products,
            products,
            product_category_ids,
        )
        recipe_count = self.import_recipes(
            db.recipes,
            recipes,
            recipe_category_ids,
            product_ids,
        )

        self.stdout.write(self.style.SUCCESS(f"Data imported into `{db_name}`."))
        self.stdout.write(f"  product_categories: {len(product_category_ids)}")
        self.stdout.write(f"  recipe_categories: {len(recipe_category_ids)}")
        self.stdout.write(f"  products: {len(product_ids)}")
        self.stdout.write(f"  recipes: {recipe_count}")

    def read_json(self, path: Path):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise CommandError(f"Invalid JSON in {path}: {exc}") from exc
        if not isinstance(data, list):
            raise CommandError(f"Expected a JSON list in {path}.")
        return data

    def import_categories(self, collection, items, label):
        ids_by_name = {}
        for item in items:
            name_id = item.get("name_id")
            name = item.get("name")
            if not name_id or not name:
                raise CommandError(f"Each {label} needs name and name_id.")
            document = {
                "name": name,
                "name_id": name_id,
                "description": item.get("description", ""),
                "active": item.get("active", True),
            }
            existing = collection.find_one({"name_id": name_id})
            if existing:
                collection.update_one({"_id": existing["_id"]}, {"$set": document})
                ids_by_name[name_id] = existing["_id"]
            else:
                result = collection.insert_one(document)
                ids_by_name[name_id] = result.inserted_id
        return ids_by_name

    def import_products(self, collection, items, category_ids):
        ids_by_name = {}
        for item in items:
            name_id = item.get("name_id")
            name = item.get("name")
            category_name_id = item.get("category_name_id")
            if not name_id or not name:
                raise CommandError("Each product needs name and name_id.")
            if not category_name_id or category_name_id not in category_ids:
                raise CommandError(
                    f"Product `{name_id}` references unknown category "
                    f"`{category_name_id}`."
                )
            document = {
                "name": name,
                "name_id": name_id,
                "description": item.get("description", ""),
                "aliases": item.get("aliases", []),
                "category_id": category_ids[category_name_id],
                "measurement_types": item.get("measurement_types", []),
                "allowed_units": item.get("allowed_units", []),
                "default_unit": item.get("default_unit"),
                "active": item.get("active", True),
            }
            existing = collection.find_one({"name_id": name_id})
            if existing:
                collection.update_one({"_id": existing["_id"]}, {"$set": document})
                ids_by_name[name_id] = existing["_id"]
            else:
                result = collection.insert_one(document)
                ids_by_name[name_id] = result.inserted_id
        return ids_by_name

    def import_recipes(self, collection, items, category_ids, product_ids):
        count = 0
        for item in items:
            name_id = item.get("name_id")
            name = item.get("name")
            if not name_id or not name:
                raise CommandError("Each recipe needs name and name_id.")

            recipe_category_ids = []
            for category_name_id in item.get("category_name_ids", []):
                if category_name_id not in category_ids:
                    raise CommandError(
                        f"Recipe `{name_id}` references unknown recipe category "
                        f"`{category_name_id}`."
                    )
                recipe_category_ids.append(category_ids[category_name_id])

            ingredients = []
            for ingredient in item.get("ingredients", []):
                product_name_id = ingredient.get("product_name_id")
                if not product_name_id or product_name_id not in product_ids:
                    raise CommandError(
                        f"Recipe `{name_id}` references unknown product "
                        f"`{product_name_id}`."
                    )
                ingredients.append(
                    {
                        "product_id": product_ids[product_name_id],
                        "quantity": ingredient.get("quantity"),
                        "unit": ingredient.get("unit"),
                        "preparation": ingredient.get("preparation", ""),
                    }
                )

            steps = []
            for index, step in enumerate(item.get("steps", [])):
                steps.append(
                    {
                        "step_number": step.get("step_number")
                        or step.get("order")
                        or index + 1,
                        "description": step.get("description", ""),
                    }
                )

            document = {
                "name": name,
                "name_id": name_id,
                "description": item.get("description", ""),
                "servings": item.get("servings"),
                "category_ids": recipe_category_ids,
                "ingredients": ingredients,
                "steps": steps,
                "prep_time_minutes": item.get("prep_time_minutes"),
                "cook_time_minutes": item.get("cook_time_minutes"),
                "difficulty": item.get("difficulty"),
                "tags": item.get("tags", []),
                "active": item.get("active", True),
            }
            existing = collection.find_one({"name_id": name_id})
            if existing:
                collection.update_one({"_id": existing["_id"]}, {"$set": document})
            else:
                collection.insert_one(document)
            count += 1
        return count
