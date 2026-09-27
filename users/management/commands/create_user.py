import getpass

from django.contrib.auth.hashers import make_password
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.core.validators import validate_email
from pymongo.errors import DuplicateKeyError

from config.mongo import get_db
from core.store import ensure_indexes
from users.documents import build_user_document, find_by_email, find_by_username
from users.roles import DEFAULT_USER_ROLE, USER_ROLES


class Command(BaseCommand):
    help = (
        "Create a RecipeHub user in MongoDB (with password hash). "
        "Use this after a fresh Mongo data directory so accounts persist via export_data."
    )

    def add_arguments(self, parser):
        parser.add_argument("username", help="Unique username.")
        parser.add_argument("--email", required=True, help="Unique email.")
        parser.add_argument("--first-name", default="", dest="first_name")
        parser.add_argument("--last-name", default="", dest="last_name")
        parser.add_argument(
            "--role",
            default=DEFAULT_USER_ROLE,
            choices=[role for role in USER_ROLES if role != "super_admin"],
            help="Role for the new user (default: user). Use make_super_admin for Super Admin.",
        )
        parser.add_argument(
            "--password",
            default=None,
            help="Password (omit to type it interactively).",
        )

    def handle(self, *args, **options):
        username = (options["username"] or "").strip()
        email = (options["email"] or "").strip()
        role = options["role"]
        if not username:
            raise CommandError("Username is required.")
        try:
            validate_email(email)
        except ValidationError as exc:
            raise CommandError("; ".join(exc.messages)) from exc

        db = get_db()
        ensure_indexes(db)
        if find_by_username(db.users, username):
            raise CommandError(f"Username '{username}' already exists.")
        if find_by_email(db.users, email):
            raise CommandError(f"Email '{email}' already registered.")

        password = options["password"]
        if not password:
            password = getpass.getpass("Password: ")
            confirm = getpass.getpass("Password (again): ")
            if password != confirm:
                raise CommandError("Passwords do not match.")
        try:
            validate_password(password)
        except ValidationError as exc:
            raise CommandError("\n".join(exc.messages)) from exc

        document = build_user_document(
            username=username,
            email=email,
            password_hash=make_password(password),
            first_name=options["first_name"],
            last_name=options["last_name"],
            role=role,
            active=True,
        )
        try:
            db.users.insert_one(document)
        except DuplicateKeyError as exc:
            raise CommandError("Username or email already exists.") from exc

        self.stdout.write(
            self.style.SUCCESS(
                f"User '{username}' created with role={role}. "
                "Run `python manage.py export_data` so the account survives Mongo restarts."
            )
        )
