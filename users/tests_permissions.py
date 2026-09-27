from django.contrib.auth.hashers import make_password
from django.test import Client, TestCase

from config.mongo import get_db
from core.store import ensure_indexes
from users.documents import build_user_document


class PermissionMatrixTests(TestCase):
    """Guest / user / admin access against the RecipeHub permission matrix."""

    def setUp(self):
        self.client = Client()
        self.db = get_db()
        ensure_indexes(self.db)
        self._cleanup()
        self.password = "ComplexPassphrase99"

        dairy = self.db.product_categories.find_one({"name_id": "dairy"})
        self.assertIsNotNone(dairy)
        self.dairy_id = dairy["_id"]

        self.db.products.insert_one(
            {
                "name": "ZZ Perm Product",
                "name_id": "zz_perm_product",
                "description": "",
                "aliases": [],
                "category_id": self.dairy_id,
                "measurement_types": ["mass"],
                "allowed_units": ["g"],
                "default_unit": "g",
                "active": True,
            }
        )
        doughs = self.db.recipe_categories.find_one({"name_id": "doughs"})
        self.db.recipes.insert_one(
            {
                "name": "ZZ Perm Recipe",
                "name_id": "zz_perm_recipe",
                "description": "",
                "servings": 2,
                "difficulty": "easy",
                "prep_time_minutes": 10,
                "cook_time_minutes": 5,
                "tags": [],
                "category_ids": [doughs["_id"]],
                "ingredients": [],
                "steps": [{"step_number": 1, "description": "Mix."}],
                "active": True,
            }
        )
        self.db.product_categories.insert_one(
            {
                "name": "ZZ Perm Category",
                "name_id": "zz_perm_category",
                "description": "",
                "active": True,
            }
        )

        self.db.users.insert_one(
            build_user_document(
                username="zz_perm_user",
                email="zz_perm_user@example.com",
                password_hash=make_password(self.password),
                role="user",
            )
        )
        self.db.users.insert_one(
            build_user_document(
                username="zz_perm_admin",
                email="zz_perm_admin@example.com",
                password_hash=make_password(self.password),
                role="admin",
            )
        )

    def tearDown(self):
        self._cleanup()

    def _cleanup(self):
        self.db.products.delete_many({"name_id": {"$regex": r"^zz_perm"}})
        self.db.recipes.delete_many({"name_id": {"$regex": r"^zz_perm"}})
        self.db.product_categories.delete_many({"name_id": {"$regex": r"^zz_perm"}})
        self.db.recipe_categories.delete_many({"name_id": {"$regex": r"^zz_perm"}})
        self.db.users.delete_many(
            {
                "$or": [
                    {"username": {"$regex": r"^zz_perm"}},
                    {"email": {"$regex": r"^zz_perm"}},
                ]
            }
        )

    def _login(self, username):
        response = self.client.post(
            "/login/",
            {"identifier": username, "password": self.password},
        )
        self.assertEqual(response.status_code, 302)

    def test_guest_can_read_but_not_mutate(self):
        self.assertEqual(self.client.get("/products/").status_code, 200)
        self.assertEqual(self.client.get("/recipes/").status_code, 200)
        self.assertEqual(self.client.get("/categories/products/").status_code, 200)

        products = self.client.get("/products/")
        self.assertNotContains(products, "+ Add Product")
        self.assertNotContains(products, "/products/zz_perm_product/edit/")
        self.assertNotContains(products, "Suspend")

        categories = self.client.get("/categories/products/")
        self.assertNotContains(categories, "+ Add Category")
        self.assertNotContains(categories, "/categories/products/zz_perm_category/edit/")

        create = self.client.get("/products/create/")
        self.assertEqual(create.status_code, 302)
        self.assertIn("/login/", create["Location"])

        suspend = self.client.post(
            "/products/zz_perm_product/active/",
            {"active": "0"},
        )
        self.assertEqual(suspend.status_code, 302)
        self.assertIn("/login/", suspend["Location"])
        self.assertTrue(self.db.products.find_one({"name_id": "zz_perm_product"})["active"])

    def test_user_can_edit_catalog_but_not_categories_or_suspend(self):
        self._login("zz_perm_user")

        products = self.client.get("/products/")
        self.assertContains(products, "+ Add Product")
        self.assertContains(products, "/products/zz_perm_product/edit/")
        self.assertNotContains(products, "Suspend")

        categories = self.client.get("/categories/products/")
        self.assertNotContains(categories, "+ Add Category")
        self.assertNotContains(categories, "Suspend")
        self.assertNotContains(categories, "/categories/products/zz_perm_category/edit/")

        cat_create = self.client.get("/categories/products/create/", follow=True)
        self.assertContains(cat_create, "Admin access required.")

        suspend = self.client.post(
            "/products/zz_perm_product/active/",
            {"active": "0"},
            follow=True,
        )
        self.assertContains(suspend, "Admin access required.")
        self.assertTrue(self.db.products.find_one({"name_id": "zz_perm_product"})["active"])

        recipe_suspend = self.client.post(
            "/recipes/zz_perm_recipe/active/",
            {"active": "0"},
            follow=True,
        )
        self.assertContains(recipe_suspend, "Admin access required.")
        self.assertTrue(self.db.recipes.find_one({"name_id": "zz_perm_recipe"})["active"])

        users = self.client.get("/users/", follow=True)
        self.assertContains(users, "Admin access required.")

    def test_user_cannot_deactivate_product_via_edit_form(self):
        self._login("zz_perm_user")
        response = self.client.post(
            "/products/zz_perm_product/edit/",
            {
                "name": "ZZ Perm Product",
                "description": "edited",
                "category_id": str(self.dairy_id),
                "aliases": "",
                "measurement_types": ["mass"],
                "allowed_units": ["g"],
                "default_unit": "g",
                # Attempt to clear active — backend must ignore.
            },
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        saved = self.db.products.find_one({"name_id": "zz_perm_product"})
        self.assertEqual(saved["description"], "edited")
        self.assertTrue(saved["active"])

    def test_user_created_product_is_always_active(self):
        self._login("zz_perm_user")
        response = self.client.post(
            "/products/create/",
            {
                "name": "ZZ Perm Created",
                "description": "",
                "category_id": str(self.dairy_id),
                "aliases": "",
                "measurement_types": ["mass"],
                "allowed_units": ["g"],
                "default_unit": "g",
            },
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        saved = self.db.products.find_one({"name_id": "zz_perm_created"})
        self.assertIsNotNone(saved)
        self.assertTrue(saved["active"])

    def test_admin_can_manage_categories_and_suspend(self):
        self._login("zz_perm_admin")

        categories = self.client.get("/categories/products/")
        self.assertContains(categories, "+ Add Category")
        self.assertContains(categories, "/categories/products/zz_perm_category/edit/")
        self.assertContains(categories, "Suspend")

        products = self.client.get("/products/")
        self.assertContains(products, "Suspend")

        suspend = self.client.post(
            "/products/zz_perm_product/active/",
            {"active": "0"},
            follow=True,
        )
        self.assertContains(suspend, "Product suspended successfully.")
        self.assertFalse(self.db.products.find_one({"name_id": "zz_perm_product"})["active"])

        users = self.client.get("/users/")
        self.assertEqual(users.status_code, 200)
        self.assertContains(users, "zz_perm_user")
