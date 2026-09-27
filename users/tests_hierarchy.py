from django.contrib.auth.hashers import make_password
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import Client, TestCase

from config.mongo import get_db
from core.store import ensure_indexes
from users.documents import build_user_document
from users.permissions import (
    can_change_user_role,
    can_edit_user,
    can_suspend_user,
    resolve_create_role,
    resolve_edit_role,
)


class RoleHierarchyTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.db = get_db()
        ensure_indexes(self.db)
        self._cleanup()
        self.password = "ComplexPassphrase99"

        self.db.users.insert_one(
            build_user_document(
                username="zz_hier_user",
                email="zz_hier_user@example.com",
                password_hash=make_password(self.password),
                role="user",
            )
        )
        self.db.users.insert_one(
            build_user_document(
                username="zz_hier_admin",
                email="zz_hier_admin@example.com",
                password_hash=make_password(self.password),
                role="admin",
            )
        )
        self.db.users.insert_one(
            build_user_document(
                username="zz_hier_sa",
                email="zz_hier_sa@example.com",
                password_hash=make_password(self.password),
                role="super_admin",
            )
        )

    def tearDown(self):
        self._cleanup()

    def _cleanup(self):
        self.db.users.delete_many(
            {
                "$or": [
                    {"username": {"$regex": r"^zz_hier"}},
                    {"email": {"$regex": r"^zz_hier"}},
                ]
            }
        )

    def _login(self, username):
        response = self.client.post(
            "/login/",
            {"identifier": username, "password": self.password},
        )
        self.assertEqual(response.status_code, 302)

    def _users(self):
        return {
            "user": self.db.users.find_one({"username": "zz_hier_user"}),
            "admin": self.db.users.find_one({"username": "zz_hier_admin"}),
            "sa": self.db.users.find_one({"username": "zz_hier_sa"}),
        }

    def test_permission_helpers_matrix(self):
        users = self._users()
        other_admin = build_user_document(
            username="zz_hier_admin2",
            email="zz_hier_admin2@example.com",
            password_hash=make_password(self.password),
            role="admin",
        )
        self.db.users.insert_one(other_admin)
        other_admin = self.db.users.find_one({"username": "zz_hier_admin2"})

        self.assertTrue(can_edit_user(users["admin"], users["user"]))
        self.assertTrue(can_suspend_user(users["admin"], users["user"]))
        self.assertFalse(can_edit_user(users["admin"], users["sa"]))
        self.assertFalse(can_suspend_user(users["admin"], users["sa"]))
        self.assertFalse(can_edit_user(users["admin"], other_admin))
        self.assertFalse(can_suspend_user(users["admin"], other_admin))

        # Self: edit yes, suspend/role no
        self.assertTrue(can_edit_user(users["admin"], users["admin"]))
        self.assertFalse(can_suspend_user(users["admin"], users["admin"]))
        self.assertFalse(can_change_user_role(users["admin"], users["user"]))

        self.assertTrue(can_edit_user(users["sa"], users["admin"]))
        self.assertTrue(can_suspend_user(users["sa"], users["admin"]))
        self.assertTrue(can_change_user_role(users["sa"], users["user"]))
        self.assertTrue(can_change_user_role(users["sa"], users["admin"]))
        self.assertFalse(can_change_user_role(users["sa"], users["sa"]))
        self.assertFalse(can_suspend_user(users["sa"], users["sa"]))

        self.assertEqual(resolve_create_role(users["admin"], "admin"), "user")
        self.assertEqual(resolve_create_role(users["sa"], "admin"), "admin")
        self.assertIsNone(resolve_create_role(users["sa"], "super_admin"))
        self.assertEqual(
            resolve_edit_role(users["admin"], users["user"], "admin", "user"),
            "user",
        )
        self.assertIsNone(
            resolve_edit_role(users["sa"], users["user"], "super_admin", "user")
        )

    def test_user_cannot_access_users_list(self):
        self._login("zz_hier_user")
        response = self.client.get("/users/", follow=True)
        self.assertContains(response, "Admin access required.")

    def test_admin_list_actions(self):
        self._login("zz_hier_admin")
        response = self.client.get("/users/")
        self.assertContains(response, "+ Create User")
        self.assertContains(response, 'href="/users/zz_hier_user/edit/"')
        self.assertContains(response, 'action="/users/zz_hier_user/active/"')
        self.assertContains(response, 'href="/users/zz_hier_sa/"')
        self.assertNotContains(response, 'href="/users/zz_hier_sa/edit/"')
        self.assertNotContains(response, 'action="/users/zz_hier_sa/active/"')
        # Self: edit yes, suspend no
        self.assertContains(response, 'href="/users/zz_hier_admin/edit/"')
        self.assertNotContains(response, 'action="/users/zz_hier_admin/active/"')

    def test_super_admin_list_actions(self):
        self._login("zz_hier_sa")
        response = self.client.get("/users/")
        self.assertContains(response, 'href="/users/zz_hier_admin/edit/"')
        self.assertContains(response, 'action="/users/zz_hier_admin/active/"')
        self.assertContains(response, 'href="/users/zz_hier_sa/edit/"')
        self.assertNotContains(response, 'action="/users/zz_hier_sa/active/"')

    def test_admin_create_forces_user_role(self):
        self._login("zz_hier_admin")
        response = self.client.post(
            "/users/create/",
            {
                "username": "zz_hier_created",
                "email": "zz_hier_created@example.com",
                "first_name": "New",
                "last_name": "User",
                "password": self.password,
                "confirm_password": self.password,
                "role": "admin",
            },
            follow=True,
        )
        self.assertContains(response, "User created successfully.")
        saved = self.db.users.find_one({"username": "zz_hier_created"})
        self.assertEqual(saved["role"], "user")

    def test_super_admin_can_create_admin_but_not_super_admin(self):
        self._login("zz_hier_sa")
        ok = self.client.post(
            "/users/create/",
            {
                "username": "zz_hier_new_admin",
                "email": "zz_hier_new_admin@example.com",
                "first_name": "New",
                "last_name": "Admin",
                "password": self.password,
                "confirm_password": self.password,
                "role": "admin",
            },
            follow=True,
        )
        self.assertContains(ok, "User created successfully.")
        self.assertEqual(
            self.db.users.find_one({"username": "zz_hier_new_admin"})["role"],
            "admin",
        )

        bad = self.client.post(
            "/users/create/",
            {
                "username": "zz_hier_fake_sa",
                "email": "zz_hier_fake_sa@example.com",
                "first_name": "Fake",
                "last_name": "SA",
                "password": self.password,
                "confirm_password": self.password,
                "role": "super_admin",
            },
        )
        self.assertContains(bad, "Invalid role.")
        self.assertIsNone(self.db.users.find_one({"username": "zz_hier_fake_sa"}))

    def test_admin_cannot_suspend_super_admin(self):
        self._login("zz_hier_admin")
        self.client.post("/users/zz_hier_sa/active/", {"active": "0"})
        self.assertTrue(self.db.users.find_one({"username": "zz_hier_sa"})["active"])

    def test_admin_cannot_self_promote_via_edit(self):
        self._login("zz_hier_admin")
        self.client.post(
            "/users/zz_hier_admin/edit/",
            {
                "username": "zz_hier_admin",
                "email": "zz_hier_admin@example.com",
                "first_name": "Admin",
                "last_name": "User",
                "password": "",
                "confirm_password": "",
                "role": "super_admin",
            },
        )
        saved = self.db.users.find_one({"username": "zz_hier_admin"})
        self.assertEqual(saved["role"], "admin")

    def test_make_super_admin_is_unique(self):
        self.db.users.insert_one(
            build_user_document(
                username="zz_hier_other",
                email="zz_hier_other@example.com",
                password_hash=make_password(self.password),
                role="user",
            )
        )
        with self.assertRaises(CommandError):
            call_command("make_super_admin", "zz_hier_other")

    def test_super_admin_catalog_access(self):
        self._login("zz_hier_sa")
        response = self.client.get("/categories/products/")
        self.assertContains(response, "+ Add Category")
        self.assertContains(response, "Suspend")
