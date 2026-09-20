from bson import ObjectId
from bson.errors import InvalidId
from django.http import Http404
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST
from pymongo.errors import DuplicateKeyError

from config.mongo import get_db
from core.catalog import MEASUREMENT_TYPES, UNITS
from core.ids import generate_name_id
from core.notices import already_exists, created, reactivated, suspended, updated
from core.store import (
    ensure_indexes,
    filters_are_active,
    find_by_name_id,
    known_measurement_types,
    known_units,
    list_filter_values,
    list_url_with_filters,
    matches_product_search,
    matches_status,
)


def _parse_aliases(raw: str) -> list[str]:
    return [part.strip() for part in raw.split(",") if part.strip()]


def _get_product_or_404(db, name_id):
    product = find_by_name_id(db.products, name_id)
    if product is None:
        raise Http404("Product not found.")
    return product


def _category_options(db, include_id=None):
    options = []
    for item in db.product_categories.find().sort("name", 1):
        is_current = include_id is not None and item["_id"] == include_id
        if item.get("active", True) or is_current:
            label = item["name"]
            if not item.get("active", True):
                label = f"{label} (suspended)"
            options.append({"id": str(item["_id"]), "name": label})
    return options


def _empty_product_form():
    return {
        "name": "",
        "description": "",
        "category_id": "",
        "aliases": "",
        "measurement_types": [],
        "allowed_units": [],
        "default_unit": "",
        "active": True,
    }


def _form_from_product(product):
    return {
        "name": product.get("name", ""),
        "description": product.get("description", ""),
        "category_id": str(product.get("category_id", "")),
        "aliases": ", ".join(product.get("aliases", [])),
        "measurement_types": product.get("measurement_types", []),
        "allowed_units": product.get("allowed_units", []),
        "default_unit": product.get("default_unit", ""),
        "active": product.get("active", True),
    }


def _form_from_post(post):
    return {
        "name": post.get("name", "").strip(),
        "description": post.get("description", "").strip(),
        "category_id": post.get("category_id", "").strip(),
        "aliases": post.get("aliases", "").strip(),
        "measurement_types": known_measurement_types(post.getlist("measurement_types")),
        "allowed_units": known_units(post.getlist("allowed_units")),
        "default_unit": post.get("default_unit", "").strip(),
        "active": post.get("active") == "on",
    }


def _validate_product_form(form, db, exclude_id=None):
    errors = []
    name_taken = False
    name_id = generate_name_id(form["name"])

    if not form["name"]:
        errors.append("Name is required.")
    if not name_id:
        errors.append("Name could not be converted into a unique name_id.")
    if not form["category_id"]:
        errors.append("Category is required.")
    if not form["measurement_types"]:
        errors.append("Select at least one measurement type.")
    if not form["allowed_units"]:
        errors.append("Select at least one allowed unit.")
    if not form["default_unit"]:
        errors.append("Default unit is required.")
    elif form["default_unit"] not in form["allowed_units"]:
        errors.append("Default unit must be one of the allowed units.")

    category = None
    if form["category_id"]:
        try:
            category = db.product_categories.find_one({"_id": ObjectId(form["category_id"])})
        except InvalidId:
            category = None
        if category is None:
            errors.append("Selected category was not found.")

    if name_id and find_by_name_id(db.products, name_id, exclude_id=exclude_id):
        name_taken = True

    return errors, name_id, category, name_taken


def _product_form_page(form, errors, categories, is_edit=False, heading="", submit_label="", name_id=""):
    return {
        "form": form,
        "errors": errors,
        "categories": categories,
        "measurement_types": MEASUREMENT_TYPES,
        "units": UNITS,
        "is_edit": is_edit,
        "heading": heading,
        "submit_label": submit_label,
        "name_id": name_id,
    }


def _list_redirect(request):
    filters = list_filter_values(request, "category", "unit")
    return redirect(list_url_with_filters(reverse("product_list"), filters))


def product_list(request):
    db = get_db()
    filters = list_filter_values(request, "category", "unit")
    categories = {item["_id"]: item for item in db.product_categories.find()}
    category_options = [
        {"id": item["name_id"], "name": item["name"]}
        for item in db.product_categories.find().sort("name", 1)
    ]
    items = []
    for product in db.products.find().sort("name", 1):
        active = product.get("active", True)
        if not matches_status(active, filters["status"]):
            continue
        if not matches_product_search(product, filters["q"]):
            continue
        category = categories.get(product.get("category_id"))
        if filters["category"]:
            if category is None or category.get("name_id") != filters["category"]:
                continue
        if filters["unit"]:
            allowed = product.get("allowed_units", [])
            default_unit = product.get("default_unit")
            if filters["unit"] != default_unit and filters["unit"] not in allowed:
                continue
        items.append(
            {
                **product,
                "category_name": category["name"] if category else "—",
                "active": active,
            }
        )
    return render(
        request,
        "products/list.html",
        {
            "products": items,
            "filters": filters,
            "filters_active": filters_are_active(filters),
            "clear_url": reverse("product_list"),
            "search_placeholder": "Search by name or alias",
            "category_options": category_options,
            "unit_options": UNITS,
        },
    )

def product_create(request):
    db = get_db()
    ensure_indexes(db)
    categories = _category_options(db)
    errors = []
    form = _empty_product_form()

    if request.method == "POST":
        form = _form_from_post(request.POST)
        form["active"] = True
        errors, name_id, category, name_taken = _validate_product_form(form, db)
        if name_taken:
            already_exists(request, "product")

        if not errors and not name_taken and category is not None:
            try:
                db.products.insert_one(
                    {
                        "name": form["name"],
                        "name_id": name_id,
                        "description": form["description"],
                        "aliases": _parse_aliases(form["aliases"]),
                        "category_id": category["_id"],
                        "measurement_types": form["measurement_types"],
                        "allowed_units": form["allowed_units"],
                        "default_unit": form["default_unit"],
                        "active": True,
                    }
                )
            except DuplicateKeyError:
                already_exists(request, "product")
            else:
                created(request, "Product")
                return redirect("product_list")

    return render(
        request,
        "products/form.html",
        _product_form_page(
            form,
            errors,
            categories,
            heading="Add product",
            submit_label="Create product",
        ),
    )


def product_edit(request, name_id):
    db = get_db()
    ensure_indexes(db)
    product = _get_product_or_404(db, name_id)
    categories = _category_options(db, include_id=product.get("category_id"))
    errors = []
    form = _form_from_product(product)

    if request.method == "POST":
        form = _form_from_post(request.POST)
        errors, next_name_id, category, name_taken = _validate_product_form(
            form,
            db,
            exclude_id=product["_id"],
        )
        if name_taken:
            already_exists(request, "product")

        if not errors and not name_taken and category is not None:
            try:
                db.products.update_one(
                    {"_id": product["_id"]},
                    {
                        "$set": {
                            "name": form["name"],
                            "name_id": next_name_id,
                            "description": form["description"],
                            "aliases": _parse_aliases(form["aliases"]),
                            "category_id": category["_id"],
                            "measurement_types": form["measurement_types"],
                            "allowed_units": form["allowed_units"],
                            "default_unit": form["default_unit"],
                            "active": form["active"],
                        }
                    },
                )
            except DuplicateKeyError:
                already_exists(request, "product")
            else:
                updated(request, "Product")
                return redirect("product_list")

    return render(
        request,
        "products/form.html",
        _product_form_page(
            form,
            errors,
            categories,
            is_edit=True,
            heading=f"Edit {product['name']}",
            submit_label="Save product",
            name_id=product["name_id"],
        ),
    )


@require_POST
def product_set_active(request, name_id):
    db = get_db()
    product = _get_product_or_404(db, name_id)
    active = request.POST.get("active") == "1"
    db.products.update_one(
        {"_id": product["_id"]},
        {"$set": {"active": active}},
    )
    if active:
        reactivated(request, "Product")
    else:
        suspended(request, "Product")
    return _list_redirect(request)
