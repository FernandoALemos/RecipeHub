from django.core.management.base import BaseCommand, CommandError

from config.mongo import get_db
from core.store import ensure_indexes
from users.documents import find_by_username, utc_now


class Command(BaseCommand):
    help = "Promote an existing RecipeHub user to administrator (role=admin)."

    def add_arguments(self, parser):
        parser.add_argument(
            "username",
            help="Username of the user to promote.",
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

        if user.get("role") == "super_admin":
            raise CommandError(
                f"User '{user['username']}' is Super Admin and cannot be demoted via make_admin."
            )

        if user.get("role") == "admin":
            self.stdout.write(
                self.style.WARNING(f"User '{user['username']}' is already an administrator.")
            )
            return

        result = db.users.update_one(
            {"_id": user["_id"]},
            {
                "$set": {
                    "role": "admin",
                    "updated_at": utc_now(),
                }
            },
        )
        if result.modified_count != 1:
            raise CommandError(f"Could not promote user '{username}'.")

        self.stdout.write(
            self.style.SUCCESS(f"User '{user['username']}' is now an administrator.")
        )
