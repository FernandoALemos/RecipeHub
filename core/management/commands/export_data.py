import json
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand

from config.mongo import get_db


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


class Command(BaseCommand):
    help = "Export RecipeHub collections to JSON"

    def handle(self, *args, **options):
        data_dir = Path(settings.BASE_DIR) / "data"
        data_dir.mkdir(exist_ok=True)

        db = get_db()
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

        self.stdout.write(
            self.style.SUCCESS(
                "Data exported successfully."
            )
        )
        self.stdout.write(f"  product_categories: {len(product_categories_data)}")
        self.stdout.write(f"  recipe_categories: {len(recipe_categories_data)}")
        self.stdout.write(f"  products: {len(products_data)}")

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
