from django.core.management.base import BaseCommand, CommandError

from config.mongo import get_db
from core.store import ensure_indexes
from users.documents import find_by_username, utc_now


class Command(BaseCommand):
    help = (
        "Promote an existing RecipeHub user to the unique Super Admin "
        "(role=super_admin). Fails if another Super Admin already exists."
    )

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
            self.stdout.write(
                self.style.WARNING(f"User '{user['username']}' is already Super Admin.")
            )
            return

        existing = db.users.find_one({"role": "super_admin"})
        if existing is not None:
            raise CommandError(
                f"Super Admin already exists ({existing['username']}). "
                "Transfer is a separate atomic operation."
            )

        result = db.users.update_one(
            {"_id": user["_id"]},
            {
                "$set": {
                    "role": "super_admin",
                    "updated_at": utc_now(),
                }
            },
        )
        if result.modified_count != 1:
            raise CommandError(f"Could not promote user '{username}'.")

        self.stdout.write(
            self.style.SUCCESS(f"User '{user['username']}' is now Super Admin.")
        )
