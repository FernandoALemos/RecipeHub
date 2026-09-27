from django.contrib.auth.hashers import check_password, make_password
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import Client, TestCase
from pymongo.errors import DuplicateKeyError

from config.mongo import get_db
from core.store import ensure_indexes
from users.documents import build_user_document, find_by_email, find_by_username
from users.roles import DEFAULT_USER_ROLE, USER_ROLES


class UsersCollectionTests(TestCase):
    def setUp(self):
        self.db = get_db()
        ensure_indexes(self.db)
        self._cleanup()

    def tearDown(self):
        self._cleanup()

    def _cleanup(self):
        self.db.users.delete_many(
            {
                "$or": [
                    {"username": {"$regex": r"^zz_"}},
                    {"email": {"$regex": r"^zz_"}},
                ]
            }
        )

    def test_users_have_unique_username_and_email_indexes(self):
        indexes = self.db.users.index_information()
        username = indexes.get("username_1")
        email = indexes.get("email_1")
        self.assertIsNotNone(username)
        self.assertIsNotNone(email)
        self.assertTrue(username.get("unique"))
        self.assertTrue(email.get("unique"))

    def test_build_user_document_shape_and_password_hash(self):
        password_hash = make_password("SecretPass123")
        document = build_user_document(
            username="  ZZ_Fernando  ",
            email="  ZZ_Fernando@Example.COM ",
            password_hash=password_hash,
            first_name="Fernando",
            last_name="Lemos",
        )
        self.assertEqual(document["username"], "ZZ_Fernando")
        self.assertEqual(document["email"], "zz_fernando@example.com")
        self.assertEqual(document["role"], DEFAULT_USER_ROLE)
        self.assertIn(document["role"], USER_ROLES)
        self.assertTrue(document["active"])
        self.assertEqual(document["password_hash"], password_hash)
        self.assertNotEqual(document["password_hash"], "SecretPass123")
        self.assertTrue(check_password("SecretPass123", document["password_hash"]))
        self.assertIn("created_at", document)
        self.assertIn("updated_at", document)
        self.assertNotIn("password", document)

    def test_username_and_email_unique_constraints(self):
        password_hash = make_password("SecretPass123")
        first = build_user_document(
            username="zz_unique_user",
            email="zz_unique@example.com",
            password_hash=password_hash,
        )
        self.db.users.insert_one(first)

        with self.assertRaises(DuplicateKeyError):
            self.db.users.insert_one(
                build_user_document(
                    username="zz_unique_user",
                    email="zz_other@example.com",
                    password_hash=password_hash,
                )
            )

        with self.assertRaises(DuplicateKeyError):
            self.db.users.insert_one(
                build_user_document(
                    username="zz_other_user",
                    email="zz_unique@example.com",
                    password_hash=password_hash,
                )
            )

        self.assertIsNotNone(find_by_username(self.db.users, "zz_unique_user"))
        self.assertIsNotNone(find_by_email(self.db.users, "ZZ_UNIQUE@EXAMPLE.COM"))


class RegisterViewTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.db = get_db()
        ensure_indexes(self.db)
        self._cleanup()

    def tearDown(self):
        self._cleanup()

    def _cleanup(self):
        self.db.users.delete_many(
            {
                "$or": [
                    {"username": {"$regex": r"^zz_"}},
                    {"email": {"$regex": r"^zz_"}},
                ]
            }
        )

    def _payload(self, **overrides):
        payload = {
            "username": "zz_register_user",
            "email": "zz_register@example.com",
            "first_name": "Test",
            "last_name": "User",
            "password": "ComplexPassphrase99",
            "confirm_password": "ComplexPassphrase99",
        }
        payload.update(overrides)
        return payload

    def test_register_valid_user(self):
        response = self.client.post("/register/", self._payload(), follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Account created successfully.")
        saved = self.db.users.find_one({"username": "zz_register_user"})
        self.assertIsNotNone(saved)
        self.assertEqual(saved["email"], "zz_register@example.com")
        self.assertEqual(saved["role"], "user")
        self.assertTrue(saved["active"])
        self.assertIn("password_hash", saved)
        self.assertNotIn("password", saved)
        self.assertNotEqual(saved["password_hash"], "ComplexPassphrase99")
        self.assertTrue(check_password("ComplexPassphrase99", saved["password_hash"]))
        self.assertContains(response, "Login")

    def test_register_rejects_duplicate_username(self):
        self.client.post("/register/", self._payload())
        response = self.client.post(
            "/register/",
            self._payload(email="zz_other_register@example.com"),
        )
        self.assertContains(response, "Username already exists.")
        self.assertEqual(self.db.users.count_documents({"username": "zz_register_user"}), 1)

    def test_register_rejects_duplicate_email(self):
        self.client.post("/register/", self._payload())
        response = self.client.post(
            "/register/",
            self._payload(username="zz_register_user_2"),
        )
        self.assertContains(response, "Email already registered.")
        self.assertEqual(
            self.db.users.count_documents({"email": "zz_register@example.com"}),
            1,
        )

    def test_register_rejects_password_mismatch(self):
        response = self.client.post(
            "/register/",
            self._payload(confirm_password="DifferentPass99"),
        )
        self.assertContains(response, "Passwords do not match.")
        self.assertIsNone(self.db.users.find_one({"username": "zz_register_user"}))

    def test_register_rejects_weak_password(self):
        response = self.client.post(
            "/register/",
            self._payload(password="12345678", confirm_password="12345678"),
        )
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(self.db.users.find_one({"username": "zz_register_user"}))
        self.assertTrue(
            b"password" in response.content.lower()
            or b"common" in response.content.lower()
            or b"numeric" in response.content.lower()
        )

    def test_register_cannot_set_admin_role(self):
        response = self.client.post(
            "/register/",
            {**self._payload(), "role": "admin"},
            follow=True,
        )
        self.assertContains(response, "Account created successfully.")
        saved = self.db.users.find_one({"username": "zz_register_user"})
        self.assertEqual(saved["role"], "user")


class MakeAdminCommandTests(TestCase):
    def setUp(self):
        self.db = get_db()
        ensure_indexes(self.db)
        self._cleanup()
        self.db.users.insert_one(
            build_user_document(
                username="zz_promo_user",
                email="zz_promo@example.com",
                password_hash=make_password("ComplexPassphrase99"),
                first_name="Promo",
                last_name="User",
                role="user",
            )
        )

    def tearDown(self):
        self._cleanup()

    def _cleanup(self):
        self.db.users.delete_many(
            {
                "$or": [
                    {"username": {"$regex": r"^zz_"}},
                    {"email": {"$regex": r"^zz_"}},
                ]
            }
        )

    def test_make_admin_promotes_existing_user(self):
        call_command("make_admin", "zz_promo_user")
        saved = self.db.users.find_one({"username": "zz_promo_user"})
        self.assertEqual(saved["role"], "admin")
        self.assertIn("updated_at", saved)

    def test_make_admin_is_idempotent(self):
        call_command("make_admin", "zz_promo_user")
        call_command("make_admin", "zz_promo_user")
        saved = self.db.users.find_one({"username": "zz_promo_user"})
        self.assertEqual(saved["role"], "admin")

    def test_make_admin_missing_user_raises(self):
        with self.assertRaises(CommandError):
            call_command("make_admin", "zz_does_not_exist")


class LoginViewTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.db = get_db()
        ensure_indexes(self.db)
        self._cleanup()
        self.password = "ComplexPassphrase99"
        self.db.users.insert_one(
            build_user_document(
                username="zz_login_user",
                email="zz_login@example.com",
                password_hash=make_password(self.password),
                first_name="Login",
                last_name="User",
            )
        )

    def tearDown(self):
        self._cleanup()

    def _cleanup(self):
        self.db.users.delete_many(
            {
                "$or": [
                    {"username": {"$regex": r"^zz_"}},
                    {"email": {"$regex": r"^zz_"}},
                ]
            }
        )

    def test_login_with_username_and_correct_password(self):
        response = self.client.post(
            "/login/",
            {"identifier": "zz_login_user", "password": self.password},
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Logged in successfully.")
        self.assertContains(response, "zz_login_user")
        self.assertNotContains(response, ">Login</a>")
        user = self.db.users.find_one({"username": "zz_login_user"})
        self.assertEqual(self.client.session.get("user_id"), str(user["_id"]))

    def test_login_with_email_and_correct_password(self):
        response = self.client.post(
            "/login/",
            {"identifier": "ZZ_LOGIN@EXAMPLE.COM", "password": self.password},
            follow=True,
        )
        self.assertContains(response, "Logged in successfully.")
        user = self.db.users.find_one({"username": "zz_login_user"})
        self.assertEqual(self.client.session.get("user_id"), str(user["_id"]))

    def test_login_rejects_wrong_password(self):
        response = self.client.post(
            "/login/",
            {"identifier": "zz_login_user", "password": "WrongPassphrase99"},
        )
        self.assertContains(response, "Invalid credentials.")
        self.assertIsNone(self.client.session.get("user_id"))

    def test_login_rejects_unknown_user(self):
        response = self.client.post(
            "/login/",
            {"identifier": "zz_nobody", "password": self.password},
        )
        self.assertContains(response, "Invalid credentials.")
        self.assertIsNone(self.client.session.get("user_id"))

    def test_login_rejects_inactive_user(self):
        self.db.users.update_one(
            {"username": "zz_login_user"},
            {"$set": {"active": False}},
        )
        response = self.client.post(
            "/login/",
            {"identifier": "zz_login_user", "password": self.password},
        )
        self.assertContains(response, "Account is inactive.")
        self.assertIsNone(self.client.session.get("user_id"))


class ProfileLogoutAndAdminListTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.db = get_db()
        ensure_indexes(self.db)
        self._cleanup()
        self.password = "ComplexPassphrase99"
        self.db.users.insert_one(
            build_user_document(
                username="zz_plain_user",
                email="zz_plain@example.com",
                password_hash=make_password(self.password),
                first_name="Plain",
                last_name="User",
                role="user",
            )
        )
        self.db.users.insert_one(
            build_user_document(
                username="zz_admin_user",
                email="zz_admin@example.com",
                password_hash=make_password(self.password),
                first_name="Admin",
                last_name="User",
                role="admin",
            )
        )

    def tearDown(self):
        self._cleanup()

    def _cleanup(self):
        self.db.users.delete_many(
            {
                "$or": [
                    {"username": {"$regex": r"^zz_"}},
                    {"email": {"$regex": r"^zz_"}},
                ]
            }
        )

    def _login(self, username):
        response = self.client.post(
            "/login/",
            {"identifier": username, "password": self.password},
        )
        self.assertEqual(response.status_code, 302)

    def test_profile_requires_login(self):
        response = self.client.get("/profile/")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response["Location"])

    def test_profile_shows_current_user(self):
        self._login("zz_plain_user")
        response = self.client.get("/profile/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "zz_plain_user")
        self.assertContains(response, "zz_plain@example.com")
        self.assertContains(response, "User")
        self.assertNotContains(response, "password_hash")

    def test_logout_clears_session(self):
        self._login("zz_plain_user")
        self.assertIsNotNone(self.client.session.get("user_id"))
        response = self.client.post("/logout/", follow=True)
        self.assertContains(response, "Logged out successfully.")
        self.assertIsNone(self.client.session.get("user_id"))
        self.assertContains(response, "Login")

    def test_users_list_requires_admin(self):
        self._login("zz_plain_user")
        response = self.client.get("/users/", follow=True)
        self.assertContains(response, "Admin access required.")
        self.assertNotContains(response, "zz_admin@example.com")

    def test_users_list_requires_login(self):
        response = self.client.get("/users/")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response["Location"])

    def test_admin_can_list_and_view_users(self):
        self._login("zz_admin_user")
        response = self.client.get("/users/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "zz_plain_user")
        self.assertContains(response, "zz_admin_user")

        detail = self.client.get("/users/zz_plain_user/")
        self.assertEqual(detail.status_code, 200)
        self.assertContains(detail, "zz_plain@example.com")
        self.assertNotContains(detail, "password_hash")

    def test_users_list_filters_by_role_and_search(self):
        self._login("zz_admin_user")
        response = self.client.get("/users/", {"role": "user", "q": "plain"})
        self.assertContains(response, "zz_plain_user")
        self.assertContains(response, "<strong>zz_plain_user</strong>")
        self.assertNotContains(response, "<strong>zz_admin_user</strong>")
        self.assertNotContains(response, "zz_admin@example.com")
