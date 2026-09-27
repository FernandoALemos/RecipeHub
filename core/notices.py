from django.contrib import messages


def created(request, label: str) -> None:
    messages.success(request, f"{label} created successfully.")


def updated(request, label: str) -> None:
    messages.success(request, f"{label} updated successfully.")


def already_exists(request, label: str) -> None:
    messages.error(request, f"A {label.lower()} with this name already exists.")


def username_taken(request) -> None:
    messages.warning(request, "Username already exists.")


def email_taken(request) -> None:
    messages.warning(request, "Email already registered.")


def account_created(request) -> None:
    messages.success(request, "Account created successfully.")


def invalid_credentials(request) -> None:
    messages.error(request, "Invalid credentials.")


def account_inactive(request) -> None:
    messages.warning(request, "Account is inactive.")


def logged_in(request) -> None:
    messages.success(request, "Logged in successfully.")


def logged_out(request) -> None:
    messages.success(request, "Logged out successfully.")


def suspended(request, label: str) -> None:
    messages.warning(request, f"{label} suspended successfully.")


def reactivated(request, label: str) -> None:
    messages.success(request, f"{label} reactivated successfully.")
