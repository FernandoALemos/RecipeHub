import json
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand

from config.mongo import get_client


def serialize_category(category):
    return {
        "name": category["name"],
        "name_id": category["name_id"],
        "description": category.get("description", ""),
        "active": category.get("active", True),
    }


def serialize_product(product, categories):
    category = categories.get(product.get("category_id"))

    return {
        "name": product["name"],
        "name_id": product["name_id"],
        "description": product.get("description", ""),
        "aliases": product.get("aliases", []),
        "category_name_id": (
            category["name_id"]
            if category
            else None
        ),
        "measurement_types": product.get(
            "measurement_types",
            [],
        ),
        "allowed_units": product.get(
            "allowed_units",
            [],
        ),
        "default_unit": product.get(
            "default_unit",
        ),
        "active": product.get("active", True),
    }


def serialize_recipe(recipe, products, categories):
    category_name_ids = []
    for category_id in recipe.get("category_ids", []):
        category = categories.get(category_id)
        if category:
            category_name_ids.append(category["name_id"])

    ingredients = []
    for item in recipe.get("ingredients", []):
        product = products.get(item.get("product_id"))
        ingredients.append(
            {
                "product_name_id": product["name_id"] if product else None,
                "quantity": item.get("quantity"),
                "unit": item.get("unit"),
                "preparation": item.get("preparation", ""),
            }
        )

    steps = []
    for index, item in enumerate(recipe.get("steps", [])):
        steps.append(
            {
                "step_number": item.get("step_number") or item.get("order") or index + 1,
                "description": item.get("description", ""),
            }
        )

    return {
        "name": recipe["name"],
        "name_id": recipe["name_id"],
        "description": recipe.get("description", ""),
        "servings": recipe.get("servings"),
        "category_name_ids": category_name_ids,
        "ingredients": ingredients,
        "steps": steps,
        "prep_time_minutes": recipe.get("prep_time_minutes"),
        "cook_time_minutes": recipe.get("cook_time_minutes"),
        "difficulty": recipe.get("difficulty"),
        "tags": recipe.get("tags", []),
        "active": recipe.get("active", True),
    }


class Command(BaseCommand):
    help = "Export RecipeHub collections to JSON"

    def add_arguments(self, parser):
        parser.add_argument(
            "--output-dir",
            default=None,
            help="Directory for JSON files (default: <BASE_DIR>/data).",
        )
        parser.add_argument(
            "--database",
            default=None,
            help="MongoDB database name (default: settings.MONGO_DB_NAME).",
        )

    def handle(self, *args, **options):
        data_dir = Path(options["output_dir"] or (Path(settings.BASE_DIR) / "data"))
        data_dir.mkdir(parents=True, exist_ok=True)

        db_name = options["database"] or settings.MONGO_DB_NAME
        db = get_client()[db_name]
        product_categories = list(
            db["product_categories"].find().sort("name", 1)
        )
        recipe_categories = list(
            db["recipe_categories"].find().sort("name", 1)
        )
        category_map = {
            category["_id"]: category
            for category in product_categories
        }

        product_categories_data = [
            serialize_category(category)
            for category in product_categories
        ]
        recipe_categories_data = [
            serialize_category(category)
            for category in recipe_categories
        ]

        products = list(
            db["products"].find().sort("name", 1)
        )
        products_data = [
            serialize_product(product, category_map)
            for product in products
        ]
        product_map = {item["_id"]: item for item in products}
        recipe_category_map = {
            category["_id"]: category
            for category in recipe_categories
        }
        recipes = list(db["recipes"].find().sort("name", 1))
        recipes_data = [
            serialize_recipe(recipe, product_map, recipe_category_map)
            for recipe in recipes
        ]

        self.write_json(
            data_dir / "product_categories.json",
            product_categories_data,
        )
        self.write_json(
            data_dir / "recipe_categories.json",
            recipe_categories_data,
        )
        self.write_json(
            data_dir / "products.json",
            products_data,
        )
        self.write_json(
            data_dir / "recipes.json",
            recipes_data,
        )

        self.stdout.write(
            self.style.SUCCESS(
                f"Data exported successfully to `{data_dir}`."
            )
        )
        self.stdout.write(f"  product_categories: {len(product_categories_data)}")
        self.stdout.write(f"  recipe_categories: {len(recipe_categories_data)}")
        self.stdout.write(f"  products: {len(products_data)}")
        self.stdout.write(f"  recipes: {len(recipes_data)}")

    def write_json(self, path, data):
        with path.open(
            "w",
            encoding="utf-8",
        ) as file:
            json.dump(
                data,
                file,
                ensure_ascii=False,
                indent=4,
            )
            file.write("\n")
