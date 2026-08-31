import json

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
        self.assertContains(response, "already exists")
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
        self.assertContains(response, "already exists")
        self.assertEqual(generate_name_id("zz hardening oil"), "zz_hardening_oil")
        self.assertEqual(self.db.products.count_documents({"name_id": "zz_hardening_oil"}), 1)

    def test_export_uses_name_id_not_objectid(self):
        call_command("export_data")
        data_dir = settings.BASE_DIR / "data"
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
        self.assertContains(response, "already exists")
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
        reactivate = self.client.post(
            "/categories/products/zz_hardening_test/active/",
            {"active": "1"},
            follow=True,
        )
        self.assertTrue(
            self.db.product_categories.find_one({"name_id": "zz_hardening_test"})["active"]
        )
        self.assertContains(reactivate, "Suspend")

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
        self.assertContains(response, "already exists")
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
        self.client.post(
            "/products/zz_hardening_oil/active/",
            {"active": "0"},
            follow=True,
        )
        self.assertFalse(self.db.products.find_one({"name_id": "zz_hardening_oil"})["active"])
        self.client.post(
            "/products/zz_hardening_oil/active/",
            {"active": "1"},
            follow=True,
        )
        self.assertTrue(self.db.products.find_one({"name_id": "zz_hardening_oil"})["active"])

    def test_category_list_uses_edit_and_suspend_actions(self):
        response = self.client.get("/categories/products/")
        self.assertContains(response, "/categories/products/dairy/edit/")
        self.assertContains(response, "Suspend")
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
        call_command("export_data")
        data_dir = settings.BASE_DIR / "data"
        recipe_categories = json.loads(
            (data_dir / "recipe_categories.json").read_text(encoding="utf-8")
        )
        desserts = next(item for item in recipe_categories if item["name_id"] == "desserts")
        self.assertEqual(desserts["name"], "Desserts")
        self.assertNotIn("_id", desserts)
        self.assertNotIn("slug", desserts)
