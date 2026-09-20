import json
from pathlib import Path

from bson import ObjectId
from django.conf import settings
from django.core.management import call_command
from django.test import Client, TestCase

from config.mongo import get_db
from core.ids import generate_name_id
from core.store import ensure_indexes


class NameIdTests(TestCase):
    def test_generate_name_id_examples(self):
        self.assertEqual(generate_name_id("Apple"), "apple")
        self.assertEqual(generate_name_id("Black Pepper"), "black_pepper")
        self.assertEqual(generate_name_id("Olive Oil"), "olive_oil")
        self.assertEqual(generate_name_id("Fish & Seafood"), "fish_seafood")
        self.assertEqual(generate_name_id("Flours & Starches"), "flours_starches")
        self.assertEqual(generate_name_id("Limón"), "limon")
        self.assertEqual(generate_name_id("Ají Molido"), "aji_molido")
        self.assertEqual(generate_name_id("BLACK PEPPER"), "black_pepper")
        self.assertEqual(generate_name_id("Black  Pepper"), "black_pepper")


class CatalogPersistenceTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.db = get_db()
        ensure_indexes(self.db)
        self._cleanup_hardening()

    def tearDown(self):
        self._cleanup_hardening()

    def _cleanup_hardening(self):
        self.db.product_categories.delete_many({"name_id": {"$regex": r"^zz_"}})
        self.db.recipe_categories.delete_many({"name_id": {"$regex": r"^zz_"}})
        self.db.products.delete_many({"name_id": {"$regex": r"^zz_"}})
        self.db.recipes.delete_many({"name_id": {"$regex": r"^zz_"}})

    def test_create_category_saves_name_id(self):
        response = self.client.post(
            "/categories/products/create/",
            {
                "name": "ZZ Hardening Test",
                "description": "Temporary category for backend checks",
            },
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        saved = self.db.product_categories.find_one({"name_id": "zz_hardening_test"})
        self.assertIsNotNone(saved)
        self.assertEqual(saved["name"], "ZZ Hardening Test")
        self.assertEqual(saved["name_id"], "zz_hardening_test")
        self.assertNotIn("slug", saved)
        self.assertTrue(saved["active"])

    def test_duplicate_category_name_id_is_rejected(self):
        self.client.post(
            "/categories/products/create/",
            {"name": "ZZ Hardening Test", "description": ""},
        )
        response = self.client.post(
            "/categories/products/create/",
            {"name": "ZZ  HARDENING   TEST", "description": ""},
        )
        self.assertContains(response, "A category with this name already exists.")
        self.assertContains(response, "toast-error")
        self.assertEqual(
            self.db.product_categories.count_documents({"name_id": "zz_hardening_test"}),
            1,
        )

    def test_create_product_stores_category_id_objectid(self):
        dairy = self.db.product_categories.find_one({"name_id": "dairy"})
        self.assertIsNotNone(dairy)
        response = self.client.post(
            "/products/create/",
            {
                "name": "ZZ Hardening Oil",
                "description": "Temporary product",
                "category_id": str(dairy["_id"]),
                "aliases": "test oil",
                "measurement_types": ["volume", "culinary_volume"],
                "allowed_units": ["ml", "tbsp"],
                "default_unit": "ml",
            },
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        saved = self.db.products.find_one({"name_id": "zz_hardening_oil"})
        self.assertIsNotNone(saved)
        self.assertIsInstance(saved["category_id"], ObjectId)
        self.assertEqual(saved["category_id"], dairy["_id"])
        self.assertEqual(saved["name_id"], "zz_hardening_oil")
        self.assertNotIn("category", saved)
        self.assertNotIn("name_key", saved)
        self.assertEqual(saved["default_unit"], "ml")

    def test_default_unit_must_be_allowed(self):
        dairy = self.db.product_categories.find_one({"name_id": "dairy"})
        response = self.client.post(
            "/products/create/",
            {
                "name": "ZZ Hardening Oil",
                "description": "",
                "category_id": str(dairy["_id"]),
                "measurement_types": ["volume"],
                "allowed_units": ["ml"],
                "default_unit": "kg",
            },
        )
        self.assertContains(response, "Default unit must be one of the allowed units")
        self.assertIsNone(self.db.products.find_one({"name_id": "zz_hardening_oil"}))

    def test_duplicate_product_name_id_is_rejected(self):
        dairy = self.db.product_categories.find_one({"name_id": "dairy"})
        first = self.client.post(
            "/products/create/",
            {
                "name": "ZZ Hardening Oil",
                "description": "",
                "category_id": str(dairy["_id"]),
                "measurement_types": ["volume"],
                "allowed_units": ["ml"],
                "default_unit": "ml",
            },
            follow=True,
        )
        self.assertEqual(first.status_code, 200)
        response = self.client.post(
            "/products/create/",
            {
                "name": "zz hardening oil",
                "description": "",
                "category_id": str(dairy["_id"]),
                "measurement_types": ["volume"],
                "allowed_units": ["ml"],
                "default_unit": "ml",
            },
        )
        self.assertContains(response, "A product with this name already exists.")
        self.assertContains(response, "toast-error")
        self.assertEqual(generate_name_id("zz hardening oil"), "zz_hardening_oil")
        self.assertEqual(self.db.products.count_documents({"name_id": "zz_hardening_oil"}), 1)

    def test_export_uses_name_id_not_objectid(self):
        import tempfile

        with tempfile.TemporaryDirectory() as temp_dir:
            call_command("export_data", output_dir=temp_dir)
            data_dir = Path(temp_dir)
            categories = json.loads(
                (data_dir / "product_categories.json").read_text(encoding="utf-8")
            )
            products = json.loads(
                (data_dir / "products.json").read_text(encoding="utf-8")
            )
            self.assertTrue(any(item["name_id"] == "dairy" for item in categories))
            self.assertTrue(all("slug" not in item for item in categories))
            egg = next(item for item in products if item["name"] == "Egg")
            self.assertEqual(egg["name_id"], "egg")
            self.assertEqual(egg["category_name_id"], "eggs")
            self.assertNotIn("category_id", egg)
            self.assertNotIn("category_slug", egg)
            self.assertNotIn("_id", egg)

    def test_edit_category_regenerates_name_id(self):
        self.client.post(
            "/categories/products/create/",
            {"name": "ZZ Hardening Test", "description": "old"},
        )
        response = self.client.post(
            "/categories/products/zz_hardening_test/edit/",
            {
                "name": "ZZ Hardening Renamed",
                "description": "new",
                "active": "on",
            },
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(self.db.product_categories.find_one({"name_id": "zz_hardening_test"}))
        saved = self.db.product_categories.find_one({"name_id": "zz_hardening_renamed"})
        self.assertIsNotNone(saved)
        self.assertEqual(saved["name"], "ZZ Hardening Renamed")
        self.assertEqual(saved["description"], "new")
        self.assertTrue(saved["active"])

    def test_edit_category_rejects_duplicate_name_id(self):
        self.client.post(
            "/categories/products/create/",
            {"name": "ZZ Hardening Test", "description": ""},
        )
        response = self.client.post(
            "/categories/products/zz_hardening_test/edit/",
            {"name": "Dairy", "description": "", "active": "on"},
        )
        self.assertContains(response, "A category with this name already exists.")
        self.assertContains(response, "toast-error")
        self.assertIsNotNone(self.db.product_categories.find_one({"name_id": "zz_hardening_test"}))
        self.assertEqual(
            self.db.product_categories.count_documents({"name_id": "dairy"}),
            1,
        )

    def test_suspend_and_reactivate_category(self):
        self.client.post(
            "/categories/products/create/",
            {"name": "ZZ Hardening Test", "description": ""},
        )
        suspend = self.client.post(
            "/categories/products/zz_hardening_test/active/",
            {"active": "0"},
            follow=True,
        )
        self.assertEqual(suspend.status_code, 200)
        self.assertFalse(
            self.db.product_categories.find_one({"name_id": "zz_hardening_test"})["active"]
        )
        self.assertContains(suspend, "Reactivate")
        self.assertContains(suspend, "Category suspended successfully.")
        self.assertContains(suspend, "toast-warning")
        self.assertContains(suspend, "Inactive")
        reactivate = self.client.post(
            "/categories/products/zz_hardening_test/active/",
            {"active": "1"},
            follow=True,
        )
        self.assertTrue(
            self.db.product_categories.find_one({"name_id": "zz_hardening_test"})["active"]
        )
        self.assertContains(reactivate, "Suspend")
        self.assertContains(reactivate, "Category reactivated successfully.")

    def test_edit_unknown_category_is_404(self):
        response = self.client.get("/categories/products/does_not_exist/edit/")
        self.assertEqual(response.status_code, 404)

    def test_edit_product_updates_fields_and_name_id(self):
        dairy = self.db.product_categories.find_one({"name_id": "dairy"})
        eggs = self.db.product_categories.find_one({"name_id": "eggs"})
        self.client.post(
            "/products/create/",
            {
                "name": "ZZ Hardening Oil",
                "description": "Temporary product",
                "category_id": str(dairy["_id"]),
                "aliases": "test oil",
                "measurement_types": ["volume"],
                "allowed_units": ["ml"],
                "default_unit": "ml",
            },
        )
        response = self.client.post(
            "/products/zz_hardening_oil/edit/",
            {
                "name": "ZZ Hardening Oil Two",
                "description": "Updated product",
                "category_id": str(eggs["_id"]),
                "aliases": "oil two",
                "measurement_types": ["volume", "culinary_volume"],
                "allowed_units": ["ml", "tbsp"],
                "default_unit": "tbsp",
                "active": "on",
            },
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(self.db.products.find_one({"name_id": "zz_hardening_oil"}))
        saved = self.db.products.find_one({"name_id": "zz_hardening_oil_two"})
        self.assertIsNotNone(saved)
        self.assertEqual(saved["name"], "ZZ Hardening Oil Two")
        self.assertEqual(saved["description"], "Updated product")
        self.assertEqual(saved["category_id"], eggs["_id"])
        self.assertEqual(saved["aliases"], ["oil two"])
        self.assertEqual(saved["default_unit"], "tbsp")
        self.assertTrue(saved["active"])

    def test_edit_product_rejects_duplicate_name_id(self):
        dairy = self.db.product_categories.find_one({"name_id": "dairy"})
        self.client.post(
            "/products/create/",
            {
                "name": "ZZ Hardening Oil",
                "category_id": str(dairy["_id"]),
                "measurement_types": ["volume"],
                "allowed_units": ["ml"],
                "default_unit": "ml",
            },
        )
        response = self.client.post(
            "/products/zz_hardening_oil/edit/",
            {
                "name": "Egg",
                "category_id": str(dairy["_id"]),
                "measurement_types": ["volume"],
                "allowed_units": ["ml"],
                "default_unit": "ml",
                "active": "on",
            },
        )
        self.assertContains(response, "A product with this name already exists.")
        self.assertContains(response, "toast-error")
        self.assertIsNotNone(self.db.products.find_one({"name_id": "zz_hardening_oil"}))
        self.assertEqual(self.db.products.count_documents({"name_id": "egg"}), 1)

    def test_suspend_and_reactivate_product(self):
        dairy = self.db.product_categories.find_one({"name_id": "dairy"})
        self.client.post(
            "/products/create/",
            {
                "name": "ZZ Hardening Oil",
                "category_id": str(dairy["_id"]),
                "measurement_types": ["volume"],
                "allowed_units": ["ml"],
                "default_unit": "ml",
            },
        )
        suspend = self.client.post(
            "/products/zz_hardening_oil/active/",
            {"active": "0"},
            follow=True,
        )
        self.assertFalse(self.db.products.find_one({"name_id": "zz_hardening_oil"})["active"])
        self.assertContains(suspend, "Product suspended successfully.")
        reactivate = self.client.post(
            "/products/zz_hardening_oil/active/",
            {"active": "1"},
            follow=True,
        )
        self.assertTrue(self.db.products.find_one({"name_id": "zz_hardening_oil"})["active"])
        self.assertContains(reactivate, "Product reactivated successfully.")

    def test_category_list_uses_edit_and_suspend_actions(self):
        response = self.client.get("/categories/products/")
        self.assertContains(response, "/categories/products/dairy/edit/")
        self.assertContains(response, "Suspend")
        self.assertContains(response, 'name="q"')
        self.assertContains(response, 'name="status"')
        self.assertNotContains(response, "Clear filters")
        self.assertNotContains(response, "Delete")

    def test_category_hub_links_both_kinds(self):
        response = self.client.get("/categories/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "/categories/products/")
        self.assertContains(response, "/categories/recipes/")

    def test_unknown_category_kind_is_404(self):
        response = self.client.get("/categories/tags/")
        self.assertEqual(response.status_code, 404)

    def test_recipe_and_product_categories_are_separate(self):
        self.client.post(
            "/categories/recipes/create/",
            {"name": "ZZ Hardening Recipe Cat", "description": "recipe side"},
        )
        recipe_saved = self.db.recipe_categories.find_one(
            {"name_id": "zz_hardening_recipe_cat"}
        )
        self.assertIsNotNone(recipe_saved)
        self.assertIsNone(
            self.db.product_categories.find_one({"name_id": "zz_hardening_recipe_cat"})
        )
        self.assertEqual(
            self.db.recipe_categories.count_documents({"name_id": "other"}),
            1,
        )
        self.assertEqual(
            self.db.product_categories.count_documents({"name_id": "other"}),
            1,
        )

    def test_edit_recipe_category_regenerates_name_id(self):
        self.client.post(
            "/categories/recipes/create/",
            {"name": "ZZ Hardening Recipe Cat", "description": "old"},
        )
        response = self.client.post(
            "/categories/recipes/zz_hardening_recipe_cat/edit/",
            {
                "name": "ZZ Hardening Recipe Renamed",
                "description": "new",
                "active": "on",
            },
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(
            self.db.recipe_categories.find_one({"name_id": "zz_hardening_recipe_cat"})
        )
        saved = self.db.recipe_categories.find_one(
            {"name_id": "zz_hardening_recipe_renamed"}
        )
        self.assertEqual(saved["name"], "ZZ Hardening Recipe Renamed")
        self.assertEqual(saved["description"], "new")

    def test_suspend_and_reactivate_recipe_category(self):
        self.client.post(
            "/categories/recipes/create/",
            {"name": "ZZ Hardening Recipe Cat", "description": ""},
        )
        self.client.post(
            "/categories/recipes/zz_hardening_recipe_cat/active/",
            {"active": "0"},
            follow=True,
        )
        self.assertFalse(
            self.db.recipe_categories.find_one(
                {"name_id": "zz_hardening_recipe_cat"}
            )["active"]
        )
        self.client.post(
            "/categories/recipes/zz_hardening_recipe_cat/active/",
            {"active": "1"},
            follow=True,
        )
        self.assertTrue(
            self.db.recipe_categories.find_one(
                {"name_id": "zz_hardening_recipe_cat"}
            )["active"]
        )

    def test_export_includes_recipe_categories(self):
        import tempfile

        with tempfile.TemporaryDirectory() as temp_dir:
            call_command("export_data", output_dir=temp_dir)
            recipe_categories = json.loads(
                (Path(temp_dir) / "recipe_categories.json").read_text(encoding="utf-8")
            )
            desserts = next(item for item in recipe_categories if item["name_id"] == "desserts")
            self.assertEqual(desserts["name"], "Desserts")
            self.assertNotIn("_id", desserts)
            self.assertNotIn("slug", desserts)

    def test_category_status_filter_hides_inactive_from_active(self):
        self.client.post(
            "/categories/products/create/",
            {"name": "ZZ Hardening Test", "description": ""},
        )
        self.client.post(
            "/categories/products/zz_hardening_test/active/",
            {"active": "0", "status": "active"},
            follow=True,
        )
        active_list = self.client.get("/categories/products/?status=active")
        self.assertNotContains(active_list, "ZZ Hardening Test")
        inactive_list = self.client.get("/categories/products/?status=inactive")
        self.assertContains(inactive_list, "ZZ Hardening Test")
        self.assertContains(inactive_list, "Inactive")
        self.assertContains(inactive_list, "Reactivate")

    def test_product_status_filter_hides_inactive_from_active(self):
        dairy = self.db.product_categories.find_one({"name_id": "dairy"})
        self.client.post(
            "/products/create/",
            {
                "name": "ZZ Hardening Oil",
                "category_id": str(dairy["_id"]),
                "measurement_types": ["volume"],
                "allowed_units": ["ml"],
                "default_unit": "ml",
            },
        )
        self.client.post(
            "/products/zz_hardening_oil/active/",
            {"active": "0", "status": "active"},
        )
        active_list = self.client.get("/products/?status=active")
        self.assertNotContains(active_list, "ZZ Hardening Oil")
        inactive_list = self.client.get("/products/?status=inactive")
        self.assertContains(inactive_list, "ZZ Hardening Oil")
        self.assertContains(inactive_list, "Inactive")

    def test_edit_category_same_name_updates_description(self):
        self.client.post(
            "/categories/products/create/",
            {"name": "ZZ Hardening Test", "description": "old"},
        )
        response = self.client.post(
            "/categories/products/zz_hardening_test/edit/",
            {
                "name": "ZZ Hardening Test",
                "description": "only description changed",
                "active": "on",
            },
            follow=True,
        )
        self.assertContains(response, "Category updated successfully.")
        self.assertContains(response, "toast-success")
        saved = self.db.product_categories.find_one({"name_id": "zz_hardening_test"})
        self.assertEqual(saved["description"], "only description changed")

    def test_duplicate_recipe_category_shows_error_toast(self):
        response = self.client.post(
            "/categories/recipes/create/",
            {"name": "DESSERTS", "description": ""},
        )
        self.assertContains(response, "A category with this name already exists.")
        self.assertContains(response, "toast-error")
        self.assertEqual(self.db.recipe_categories.count_documents({"name_id": "desserts"}), 1)

    def test_create_success_uses_toast(self):
        response = self.client.post(
            "/categories/products/create/",
            {"name": "ZZ Hardening Test", "description": ""},
            follow=True,
        )
        self.assertContains(response, "Category created successfully.")
        self.assertContains(response, "toast-success")

    def _recipe_payload(self, **overrides):
        water = self.db.products.find_one({"name_id": "water"})
        oil = self.db.products.find_one({"name_id": "olive_oil"})
        doughs = self.db.recipe_categories.find_one({"name_id": "doughs"})
        mains = self.db.recipe_categories.find_one({"name_id": "main_courses"})
        payload = {
            "name": "ZZ Hardening Pizza",
            "description": "Test recipe",
            "servings": "4",
            "difficulty": "medium",
            "prep_time_minutes": "30",
            "cook_time_minutes": "10",
            "tags": "Italian, Oven",
            "category_ids": [str(doughs["_id"]), str(mains["_id"])],
            "ingredient_product_id": [str(water["_id"]), str(oil["_id"])],
            "ingredient_quantity": ["1", "1"],
            "ingredient_unit": ["cup", "tbsp"],
            "ingredient_preparation": ["", ""],
            "step_description": ["Mix.", "Bake."],
        }
        payload.update(overrides)
        return payload

    def test_create_recipe_stores_used_unit_not_default(self):
        water = self.db.products.find_one({"name_id": "water"})
        oil = self.db.products.find_one({"name_id": "olive_oil"})
        response = self.client.post("/recipes/create/", self._recipe_payload(), follow=True)
        self.assertEqual(response.status_code, 200)
        saved = self.db.recipes.find_one({"name_id": "zz_hardening_pizza"})
        self.assertIsNotNone(saved)
        self.assertEqual(saved["servings"], 4)
        self.assertEqual(saved["tags"], ["italian", "oven"])
        self.assertEqual(len(saved["category_ids"]), 2)
        self.assertIsInstance(saved["category_ids"][0], ObjectId)
        self.assertEqual(saved["ingredients"][0]["product_id"], water["_id"])
        self.assertEqual(saved["ingredients"][0]["unit"], "cup")
        self.assertNotEqual(saved["ingredients"][0]["unit"], water["default_unit"])
        self.assertEqual(saved["ingredients"][1]["product_id"], oil["_id"])
        self.assertEqual(saved["ingredients"][1]["unit"], "tbsp")
        self.assertNotIn("default_unit", saved["ingredients"][0])
        self.assertEqual(saved["steps"][0]["step_number"], 1)
        self.assertEqual(saved["steps"][1]["step_number"], 2)
        self.assertContains(response, "Recipe created successfully.")

    def test_recipe_rejects_unit_outside_allowed_units(self):
        water = self.db.products.find_one({"name_id": "water"})
        payload = self._recipe_payload(
            ingredient_product_id=[str(water["_id"])],
            ingredient_quantity=["1"],
            ingredient_unit=["unit"],
            ingredient_preparation=[""],
        )
        response = self.client.post("/recipes/create/", payload)
        self.assertContains(response, "is not allowed")
        self.assertIsNone(self.db.recipes.find_one({"name_id": "zz_hardening_pizza"}))

    def test_duplicate_recipe_name_id_is_rejected(self):
        self.client.post("/recipes/create/", self._recipe_payload())
        response = self.client.post(
            "/recipes/create/",
            self._recipe_payload(name="zz hardening pizza"),
        )
        self.assertContains(response, "A recipe with this name already exists.")
        self.assertEqual(self.db.recipes.count_documents({"name_id": "zz_hardening_pizza"}), 1)

    def test_recipe_form_includes_product_unit_catalog(self):
        water = self.db.products.find_one({"name_id": "water"})
        response = self.client.get("/recipes/create/")
        self.assertContains(response, "product-catalog")
        self.assertContains(response, "product-options")
        self.assertContains(response, str(water["_id"]))
        self.assertContains(response, "default_unit")
        self.assertContains(response, "allowed_units")
        self.assertContains(response, "js-product-search")
        self.assertContains(response, "Search a product")
    def test_recipe_detail_shows_ingredients_and_steps(self):
        self.client.post("/recipes/create/", self._recipe_payload())
        response = self.client.get("/recipes/zz_hardening_pizza/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "ZZ Hardening Pizza")
        self.assertContains(response, "Water")
        self.assertContains(response, "cup")
        self.assertContains(response, "Olive Oil")
        self.assertContains(response, "tbsp")
        self.assertContains(response, "Mix.")
        self.assertContains(response, "Bake.")
        self.assertContains(response, "Active")
        self.assertContains(response, "/recipes/zz_hardening_pizza/edit/")

    def test_edit_recipe_updates_fields_and_reorders_steps(self):
        self.client.post("/recipes/create/", self._recipe_payload())
        water = self.db.products.find_one({"name_id": "water"})
        oil = self.db.products.find_one({"name_id": "olive_oil"})
        doughs = self.db.recipe_categories.find_one({"name_id": "doughs"})
        form = self.client.get("/recipes/zz_hardening_pizza/edit/")
        self.assertContains(form, 'value="ZZ Hardening Pizza"')
        self.assertContains(form, 'data-selected="cup"')
        self.assertContains(form, "Bake.")

        response = self.client.post(
            "/recipes/zz_hardening_pizza/edit/",
            self._recipe_payload(
                name="ZZ Hardening Pizza Edited",
                servings="6",
                ingredient_product_id=[str(oil["_id"]), str(water["_id"])],
                ingredient_quantity=["2", "1"],
                ingredient_unit=["tsp", "cup"],
                ingredient_preparation=["", ""],
                step_description=["Bake.", "Mix."],
                category_ids=[str(doughs["_id"])],
            ),
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Recipe updated successfully.")
        self.assertContains(response, "ZZ Hardening Pizza Edited")
        saved = self.db.recipes.find_one({"name_id": "zz_hardening_pizza_edited"})
        self.assertIsNotNone(saved)
        self.assertIsNone(self.db.recipes.find_one({"name_id": "zz_hardening_pizza"}))
        self.assertEqual(saved["servings"], 6)
        self.assertEqual(len(saved["category_ids"]), 1)
        self.assertEqual(saved["ingredients"][0]["product_id"], oil["_id"])
        self.assertEqual(saved["ingredients"][0]["unit"], "tsp")
        self.assertEqual(saved["ingredients"][0]["quantity"], 2)
        self.assertNotIn("default_unit", saved["ingredients"][0])
        self.assertEqual(saved["steps"][0]["description"], "Bake.")
        self.assertEqual(saved["steps"][0]["step_number"], 1)
        self.assertEqual(saved["steps"][1]["description"], "Mix.")
        self.assertEqual(saved["steps"][1]["step_number"], 2)

    def test_edit_recipe_rejects_unit_outside_allowed_units(self):
        self.client.post("/recipes/create/", self._recipe_payload())
        water = self.db.products.find_one({"name_id": "water"})
        payload = self._recipe_payload(
            ingredient_product_id=[str(water["_id"])],
            ingredient_quantity=["1"],
            ingredient_unit=["unit"],
            ingredient_preparation=[""],
        )
        response = self.client.post("/recipes/zz_hardening_pizza/edit/", payload)
        self.assertContains(response, "is not allowed")
        saved = self.db.recipes.find_one({"name_id": "zz_hardening_pizza"})
        self.assertEqual(saved["ingredients"][0]["unit"], "cup")

    def test_suspend_and_reactivate_recipe(self):
        self.client.post("/recipes/create/", self._recipe_payload())
        suspend = self.client.post(
            "/recipes/zz_hardening_pizza/active/",
            {"active": "0", "status": "all"},
            follow=True,
        )
        self.assertEqual(suspend.status_code, 200)
        self.assertFalse(self.db.recipes.find_one({"name_id": "zz_hardening_pizza"})["active"])
        self.assertContains(suspend, "Reactivate")
        self.assertContains(suspend, "Recipe suspended successfully.")
        self.assertContains(suspend, "Inactive")
        reactivate = self.client.post(
            "/recipes/zz_hardening_pizza/active/",
            {"active": "1", "status": "all"},
            follow=True,
        )
        self.assertTrue(self.db.recipes.find_one({"name_id": "zz_hardening_pizza"})["active"])
        self.assertContains(reactivate, "Suspend")
        self.assertContains(reactivate, "Recipe reactivated successfully.")

    def test_recipe_list_uses_view_edit_and_suspend_actions(self):
        self.client.post("/recipes/create/", self._recipe_payload())
        response = self.client.get("/recipes/")
        self.assertContains(response, "/recipes/zz_hardening_pizza/")
        self.assertContains(response, "/recipes/zz_hardening_pizza/edit/")
        self.assertContains(response, "View")
        self.assertContains(response, "Edit")
        self.assertContains(response, "Suspend")
        self.assertContains(response, 'name="q"')
        self.assertContains(response, 'name="category"')
        self.assertContains(response, 'name="ingredient"')
        self.assertContains(response, 'name="difficulty"')
        self.assertContains(response, 'name="tag"')
        self.assertContains(response, 'name="max_prep"')
        self.assertNotContains(response, "Delete")

    def test_recipe_status_filter_hides_inactive_from_active(self):
        self.client.post("/recipes/create/", self._recipe_payload())
        self.db.recipes.update_one(
            {"name_id": "zz_hardening_pizza"},
            {"$set": {"active": False}},
        )
        active = self.client.get("/recipes/?status=active")
        self.assertNotContains(active, "ZZ Hardening Pizza")
        inactive = self.client.get("/recipes/?status=inactive")
        self.assertContains(inactive, "ZZ Hardening Pizza")

    def test_category_search_is_case_insensitive(self):
        response = self.client.get("/categories/products/?q=DaIrY")
        self.assertContains(response, "Dairy")
        self.assertContains(response, "Clear filters")
        by_description = self.client.get("/categories/products/?q=yogurt")
        self.assertContains(by_description, "Dairy")
        missing = self.client.get("/categories/products/?q=zzzz_not_found")
        self.assertContains(missing, "No categories match these filters.")

    def test_product_search_matches_name_and_aliases(self):
        dairy = self.db.product_categories.find_one({"name_id": "dairy"})
        self.client.post(
            "/products/create/",
            {
                "name": "ZZ Mozzarella Cheese",
                "category_id": str(dairy["_id"]),
                "aliases": "Muzzarella, Mozzarella",
                "measurement_types": ["mass"],
                "allowed_units": ["g", "kg"],
                "default_unit": "g",
            },
        )
        by_alias = self.client.get("/products/?q=muzzarella")
        self.assertContains(by_alias, "ZZ Mozzarella Cheese")
        by_case = self.client.get("/products/?q=APPLE")
        self.assertContains(by_case, "Apple")
        self.assertContains(by_case, "Apple Cider Vinegar")

    def test_product_filters_combine_search_category_unit_and_status(self):
        oils = self.db.product_categories.find_one({"name_id": "oils_fats"})
        self.assertIsNotNone(oils)
        self.assertIsNotNone(self.db.products.find_one({"name_id": "olive_oil"}))

        response = self.client.get(
            "/products/",
            {
                "q": "oil",
                "category": "oils_fats",
                "unit": "tbsp",
                "status": "active",
            },
        )
        self.assertContains(response, "Olive Oil")
        self.assertContains(response, "Clear filters")

        wrong_unit = self.client.get(
            "/products/",
            {
                "q": "oil",
                "category": "oils_fats",
                "unit": "dozen",
                "status": "active",
            },
        )
        self.assertNotContains(wrong_unit, "Olive Oil")
    def test_recipe_filters_combine_name_category_ingredient_difficulty_and_tags(self):
        self.client.post("/recipes/create/", self._recipe_payload())
        oil = self.db.products.find_one({"name_id": "olive_oil"})
        response = self.client.get(
            "/recipes/",
            {
                "q": "pizza",
                "category": "doughs",
                "ingredient": oil["name_id"],
                "difficulty": "medium",
                "tag": "oven",
                "max_prep": "60",
                "max_cook": "30",
                "status": "active",
            },
        )
        self.assertContains(response, "ZZ Hardening Pizza")
        self.assertContains(response, "Clear filters")
        self.assertContains(response, 'name="tag"')
        self.assertContains(response, 'name="max_prep"')
        self.assertContains(response, 'name="max_cook"')

        wrong = self.client.get(
            "/recipes/",
            {
                "q": "pizza",
                "category": "doughs",
                "ingredient": oil["name_id"],
                "difficulty": "hard",
                "tag": "oven",
                "status": "active",
            },
        )
        self.assertNotContains(wrong, "ZZ Hardening Pizza")
        self.assertContains(wrong, "No recipes match these filters.")

        too_short_prep = self.client.get(
            "/recipes/",
            {
                "q": "pizza",
                "max_prep": "15",
                "status": "active",
            },
        )
        self.assertNotContains(too_short_prep, "ZZ Hardening Pizza")

    def test_import_data_rebuilds_relations_on_separate_database(self):
        import tempfile

        from config.mongo import get_client

        db_name = "recipe_hub_test_import"
        client = get_client()
        with tempfile.TemporaryDirectory() as temp_dir:
            call_command("export_data", output_dir=temp_dir)
            expected = {
                name: len(json.loads((Path(temp_dir) / f"{name}.json").read_text(encoding="utf-8")))
                for name in (
                    "product_categories",
                    "recipe_categories",
                    "products",
                    "recipes",
                )
            }
            recipes_data = json.loads(
                (Path(temp_dir) / "recipes.json").read_text(encoding="utf-8")
            )
            self.assertGreaterEqual(expected["recipes"], 1)

            call_command(
                "import_data",
                database=db_name,
                input_dir=temp_dir,
                clear=True,
            )
            db = client[db_name]
            try:
                self.assertEqual(
                    db.product_categories.count_documents({}),
                    expected["product_categories"],
                )
                self.assertEqual(
                    db.recipe_categories.count_documents({}),
                    expected["recipe_categories"],
                )
                self.assertEqual(db.products.count_documents({}), expected["products"])
                self.assertEqual(db.recipes.count_documents({}), expected["recipes"])

                sample = next(item for item in recipes_data if item.get("ingredients"))
                recipe = db.recipes.find_one({"name_id": sample["name_id"]})
                self.assertIsNotNone(recipe)
                first = sample["ingredients"][0]
                product = db.products.find_one({"name_id": first["product_name_id"]})
                self.assertIsNotNone(product)
                self.assertEqual(recipe["ingredients"][0]["product_id"], product["_id"])
                self.assertEqual(recipe["ingredients"][0]["unit"], first["unit"])
                self.assertNotIn("product_name_id", recipe["ingredients"][0])

                if sample.get("category_name_ids"):
                    category = db.recipe_categories.find_one(
                        {"name_id": sample["category_name_ids"][0]}
                    )
                    self.assertIsNotNone(category)
                    self.assertIn(category["_id"], recipe["category_ids"])
            finally:
                client.drop_database(db_name)
