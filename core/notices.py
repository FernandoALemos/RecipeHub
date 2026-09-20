from django.contrib import messages


def created(request, label: str) -> None:
    messages.success(request, f"{label} created successfully.")


def updated(request, label: str) -> None:
    messages.success(request, f"{label} updated successfully.")


def already_exists(request, label: str) -> None:
    messages.error(request, f"A {label.lower()} with this name already exists.")


def suspended(request, label: str) -> None:
    messages.warning(request, f"{label} suspended successfully.")


def reactivated(request, label: str) -> None:
    messages.success(request, f"{label} reactivated successfully.")
