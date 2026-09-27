import getpass

from django.contrib.auth.hashers import make_password
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError

from config.mongo import get_db
from core.store import ensure_indexes
from users.documents import find_by_username, utc_now


class Command(BaseCommand):
    help = "Reset password_hash for an existing RecipeHub user in MongoDB."

    def add_arguments(self, parser):
        parser.add_argument("username", help="Username of the account to update.")
        parser.add_argument(
            "--password",
            default=None,
            help="New password (omit to type it interactively).",
        )

    def handle(self, *args, **options):
        username = (options["username"] or "").strip()
        if not username:
            raise CommandError("Username is required.")

        db = get_db()
        ensure_indexes(db)
        user = find_by_username(db.users, username)
        if user is None:
            raise CommandError(f"User '{username}' does not exist.")

        password = options["password"]
        if not password:
            password = getpass.getpass("New password: ")
            confirm = getpass.getpass("New password (again): ")
            if password != confirm:
                raise CommandError("Passwords do not match.")
        try:
            validate_password(password, user=None)
        except ValidationError as exc:
            raise CommandError("\n".join(exc.messages)) from exc

        result = db.users.update_one(
            {"_id": user["_id"]},
            {
                "$set": {
                    "password_hash": make_password(password),
                    "updated_at": utc_now(),
                }
            },
        )
        if result.matched_count != 1:
            raise CommandError(f"Could not update password for '{username}'.")

        self.stdout.write(
            self.style.SUCCESS(
                f"Password updated for '{user['username']}'. "
                "Run `python manage.py export_data` to refresh data/users.json."
            )
        )
