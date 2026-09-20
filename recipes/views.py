from bson import ObjectId
from bson.errors import InvalidId
from django.http import Http404
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST
from pymongo.errors import DuplicateKeyError

from config.mongo import get_db
from core.ids import generate_name_id
from core.notices import already_exists, created, reactivated, suspended, updated
from core.store import (
    TIME_FILTER_OPTIONS,
    ensure_indexes,
    filters_are_active,
    find_by_name_id,
    list_filter_values,
    list_url_with_filters,
    matches_max_minutes,
    matches_name_search,
    matches_status,
    matches_tag_filter,
    parse_max_minutes,
)

DIFFICULTIES = [
    ("easy", "Easy"),
    ("medium", "Medium"),
    ("hard", "Hard"),
]
DIFFICULTY_LABELS = dict(DIFFICULTIES)


def _parse_tags(raw: str) -> list[str]:
    seen = []
    for part in raw.split(","):
        tag = generate_name_id(part.strip())
        if tag and tag not in seen:
            seen.append(tag)
    return seen


def _parse_optional_int(raw: str, field: str, errors: list[str], minimum=0):
    value = raw.strip()
    if not value:
        return None
    try:
        number = int(value)
    except ValueError:
        errors.append(f"{field} must be a whole number.")
        return raw
    if number < minimum:
        errors.append(f"{field} must be at least {minimum}.")
        return raw
    return number


def _parse_quantity(raw: str, unit: str):
    value = raw.strip()
    if unit == "to_taste" and not value:
        return None, None
    if not value:
        return raw, "Quantity is required."
    try:
        number = float(value)
    except ValueError:
        return raw, "Quantity must be a number."
    if number <= 0:
        return raw, "Quantity must be greater than 0."
    if number.is_integer():
        return int(number), None
    return number, None


def _get_recipe_or_404(db, name_id):
    recipe = find_by_name_id(db.recipes, name_id)
    if recipe is None:
        raise Http404("Recipe not found.")
    return recipe


def _product_catalog(db, include_ids=None):
    include_ids = set(include_ids or [])
    options = []
    catalog = {}
    by_id = {}
    for product in db.products.find().sort("name", 1):
        is_current = product["_id"] in include_ids
        if not product.get("active", True) and not is_current:
            continue
        pid = str(product["_id"])
        label = product["name"]
        if not product.get("active", True):
            label = f"{label} (suspended)"
        options.append({"id": pid, "name": label})
        catalog[pid] = {
            "allowed_units": product.get("allowed_units", []),
            "default_unit": product.get("default_unit") or "",
        }
        by_id[product["_id"]] = product
    return options, catalog, by_id


def _recipe_category_options(db, include_ids=None):
    include_ids = set(include_ids or [])
    options = []
    for item in db.recipe_categories.find().sort("name", 1):
        is_current = item["_id"] in include_ids
        if item.get("active", True) or is_current:
            label = item["name"]
            if not item.get("active", True):
                label = f"{label} (suspended)"
            options.append({"id": str(item["_id"]), "name": label})
    return options


def _empty_form():
    return {
        "name": "",
        "description": "",
        "servings": "4",
        "difficulty": "medium",
        "prep_time_minutes": "",
        "cook_time_minutes": "",
        "tags": "",
        "category_ids": [],
        "ingredients": [
            {"product_id": "", "quantity": "", "unit": "", "preparation": ""},
        ],
        "steps": [{"description": ""}],
    }


def _form_from_recipe(recipe):
    ingredients = [
        {
            "product_id": str(item.get("product_id", "")),
            "quantity": "" if item.get("quantity") is None else item.get("quantity"),
            "unit": item.get("unit", ""),
            "preparation": item.get("preparation", ""),
        }
        for item in recipe.get("ingredients", [])
    ]
    steps = [
        {"description": item.get("description", "")}
        for item in recipe.get("steps", [])
    ]
    return {
        "name": recipe.get("name", ""),
        "description": recipe.get("description", ""),
        "servings": recipe.get("servings", ""),
        "difficulty": recipe.get("difficulty", "medium"),
        "prep_time_minutes": (
            "" if recipe.get("prep_time_minutes") is None else recipe.get("prep_time_minutes")
        ),
        "cook_time_minutes": (
            "" if recipe.get("cook_time_minutes") is None else recipe.get("cook_time_minutes")
        ),
        "tags": ", ".join(recipe.get("tags", [])),
        "category_ids": [str(category_id) for category_id in recipe.get("category_ids", [])],
        "ingredients": ingredients
        or [{"product_id": "", "quantity": "", "unit": "", "preparation": ""}],
        "steps": steps or [{"description": ""}],
    }


def _collect_ingredients(post, products_by_id):
    errors = []
    form_rows = []
    saved = []
    product_ids = post.getlist("ingredient_product_id")
    quantities = post.getlist("ingredient_quantity")
    units = post.getlist("ingredient_unit")
    preparations = post.getlist("ingredient_preparation")
    count = max(len(product_ids), len(quantities), len(units), len(preparations), 1)

    for index in range(count):
        product_id = product_ids[index].strip() if index < len(product_ids) else ""
        quantity_raw = quantities[index].strip() if index < len(quantities) else ""
        unit = units[index].strip() if index < len(units) else ""
        preparation = preparations[index].strip() if index < len(preparations) else ""
        if not product_id and not quantity_raw and not unit and not preparation:
            continue

        row = {
            "product_id": product_id,
            "quantity": quantity_raw,
            "unit": unit,
            "preparation": preparation,
        }
        form_rows.append(row)

        product = None
        if product_id:
            try:
                product = products_by_id.get(ObjectId(product_id))
            except InvalidId:
                product = None
        if product is None:
            errors.append("Each ingredient must use an existing product.")
            continue

        allowed = product.get("allowed_units", [])
        quantity, quantity_error = _parse_quantity(quantity_raw, unit)
        if quantity_error:
            errors.append(f"{product['name']}: {quantity_error}")
        if not unit:
            errors.append(f"{product['name']}: Unit is required.")
        elif unit not in allowed:
            errors.append(
                f"{product['name']}: unit '{unit}' is not allowed. "
                f"Use one of: {', '.join(allowed)}."
            )
        elif quantity_error is None:
            saved.append(
                {
                    "product_id": product["_id"],
                    "quantity": quantity,
                    "unit": unit,
                    "preparation": preparation,
                }
            )

    if not form_rows:
        form_rows = [{"product_id": "", "quantity": "", "unit": "", "preparation": ""}]
        errors.append("Add at least one ingredient.")
    return form_rows, saved, errors


def _collect_steps(post):
    errors = []
    form_rows = []
    saved = []
    for description in post.getlist("step_description"):
        text = description.strip()
        if not text:
            continue
        form_rows.append({"description": text})
        saved.append({"step_number": len(saved) + 1, "description": text})
    if not form_rows:
        form_rows = [{"description": ""}]
        errors.append("Add at least one step.")
    return form_rows, saved, errors


def _collect_categories(post, db):
    errors = []
    selected = []
    saved = []
    for raw in post.getlist("category_ids"):
        value = raw.strip()
        if not value:
            continue
        selected.append(value)
        try:
            category = db.recipe_categories.find_one({"_id": ObjectId(value)})
        except InvalidId:
            category = None
        if category is None:
            errors.append("Selected recipe category was not found.")
        else:
            saved.append(category["_id"])
    if not saved and not errors:
        errors.append("Select at least one recipe category.")
    return selected, saved, errors


def _process_recipe_post(request, db, products_by_id, exclude_id=None):
    form = _empty_form()
    form["name"] = request.POST.get("name", "").strip()
    form["description"] = request.POST.get("description", "").strip()
    form["servings"] = request.POST.get("servings", "").strip()
    form["difficulty"] = request.POST.get("difficulty", "").strip()
    form["prep_time_minutes"] = request.POST.get("prep_time_minutes", "").strip()
    form["cook_time_minutes"] = request.POST.get("cook_time_minutes", "").strip()
    form["tags"] = request.POST.get("tags", "").strip()
    form["category_ids"], category_ids, category_errors = _collect_categories(request.POST, db)
    form["ingredients"], ingredients, ingredient_errors = _collect_ingredients(
        request.POST,
        products_by_id,
    )
    form["steps"], steps, step_errors = _collect_steps(request.POST)

    errors = []
    errors.extend(category_errors)
    errors.extend(ingredient_errors)
    errors.extend(step_errors)

    name_id = generate_name_id(form["name"])
    name_taken = False
    if not form["name"]:
        errors.append("Name is required.")
    if not name_id:
        errors.append("Name could not be converted into a unique name_id.")
    elif find_by_name_id(db.recipes, name_id, exclude_id=exclude_id):
        name_taken = True

    servings = _parse_optional_int(form["servings"], "Servings", errors, minimum=1)
    if form["servings"] == "":
        errors.append("Servings is required.")
    prep_time = _parse_optional_int(form["prep_time_minutes"], "Prep time", errors)
    cook_time = _parse_optional_int(form["cook_time_minutes"], "Cook time", errors)
    if form["difficulty"] not in DIFFICULTY_LABELS:
        errors.append("Difficulty is required.")

    document = None
    if not errors and not name_taken and isinstance(servings, int):
        document = {
            "name": form["name"],
            "name_id": name_id,
            "description": form["description"],
            "servings": servings,
            "category_ids": category_ids,
            "ingredients": ingredients,
            "steps": steps,
            "prep_time_minutes": prep_time if isinstance(prep_time, int) else None,
            "cook_time_minutes": cook_time if isinstance(cook_time, int) else None,
            "difficulty": form["difficulty"],
            "tags": _parse_tags(form["tags"]),
        }
    return form, errors, document, name_taken


def _recipe_form_page(
    form,
    errors,
    heading,
    submit_label,
    product_options,
    product_catalog,
    category_options,
    is_edit=False,
    name_id="",
    back_url="",
    back_label="Back to list",
):
    return {
        "form": form,
        "errors": errors,
        "heading": heading,
        "submit_label": submit_label,
        "difficulties": DIFFICULTIES,
        "product_options": product_options,
        "product_catalog": product_catalog,
        "category_options": category_options,
        "is_edit": is_edit,
        "name_id": name_id,
        "back_url": back_url,
        "back_label": back_label,
    }


def _minutes_label(value):
    if value is None or value == "":
        return "—"
    return f"{value} min"


def _step_number(step, index):
    return step.get("step_number") or step.get("order") or index + 1


def _decorate_recipe(recipe, db):
    categories = {item["_id"]: item for item in db.recipe_categories.find()}
    products = {item["_id"]: item for item in db.products.find()}
    names = [
        categories[category_id]["name"]
        for category_id in recipe.get("category_ids", [])
        if category_id in categories
    ]
    ingredients = []
    for item in recipe.get("ingredients", []):
        product = products.get(item.get("product_id"))
        ingredients.append(
            {
                "product_name": product["name"] if product else "—",
                "quantity": item.get("quantity"),
                "unit": item.get("unit", ""),
                "preparation": item.get("preparation", ""),
            }
        )
    steps = sorted(
        (
            {
                "step_number": _step_number(item, index),
                "description": item.get("description", ""),
            }
            for index, item in enumerate(recipe.get("steps", []))
        ),
        key=lambda item: item["step_number"],
    )
    return {
        **recipe,
        "category_names": ", ".join(names) if names else "—",
        "active": recipe.get("active", True),
        "difficulty_label": DIFFICULTY_LABELS.get(recipe.get("difficulty"), recipe.get("difficulty") or "—"),
        "prep_time_label": _minutes_label(recipe.get("prep_time_minutes")),
        "cook_time_label": _minutes_label(recipe.get("cook_time_minutes")),
        "ingredient_rows": ingredients,
        "step_rows": steps,
        "tag_labels": recipe.get("tags", []),
    }


def _list_redirect(request):
    filters = list_filter_values(
        request,
        "category",
        "ingredient",
        "difficulty",
        "tag",
        "max_prep",
        "max_cook",
    )
    return redirect(list_url_with_filters(reverse("recipe_list"), filters))


def recipe_list(request):
    db = get_db()
    filters = list_filter_values(
        request,
        "category",
        "ingredient",
        "difficulty",
        "tag",
        "max_prep",
        "max_cook",
    )
    categories = {item["_id"]: item for item in db.recipe_categories.find()}
    products = {item["_id"]: item for item in db.products.find()}
    category_options = [
        {"id": item["name_id"], "name": item["name"]}
        for item in db.recipe_categories.find().sort("name", 1)
    ]
    ingredient_options = [
        {"id": item["name_id"], "name": item["name"]}
        for item in db.products.find().sort("name", 1)
        if item.get("active", True)
    ]
    tag_ids = sorted(
        {
            tag
            for recipe in db.recipes.find({}, {"tags": 1})
            for tag in recipe.get("tags", [])
            if tag
        }
    )
    tag_options = [{"id": tag, "name": tag.replace("_", " ")} for tag in tag_ids]
    if filters["difficulty"] and filters["difficulty"] not in DIFFICULTY_LABELS:
        filters["difficulty"] = ""
    if filters["tag"] and filters["tag"] not in tag_ids:
        filters["tag"] = ""
    if filters["max_prep"] and filters["max_prep"] not in {code for code, _ in TIME_FILTER_OPTIONS}:
        filters["max_prep"] = ""
    if filters["max_cook"] and filters["max_cook"] not in {code for code, _ in TIME_FILTER_OPTIONS}:
        filters["max_cook"] = ""
    max_prep = parse_max_minutes(filters["max_prep"])
    max_cook = parse_max_minutes(filters["max_cook"])

    items = []
    for recipe in db.recipes.find().sort("name", 1):
        active = recipe.get("active", True)
        if not matches_status(active, filters["status"]):
            continue
        if not matches_name_search(recipe.get("name", ""), filters["q"]):
            continue
        if not matches_tag_filter(recipe.get("tags", []), filters["tag"]):
            continue
        if filters["difficulty"] and recipe.get("difficulty") != filters["difficulty"]:
            continue
        if not matches_max_minutes(recipe.get("prep_time_minutes"), max_prep):
            continue
        if not matches_max_minutes(recipe.get("cook_time_minutes"), max_cook):
            continue

        recipe_categories = [
            categories[category_id]
            for category_id in recipe.get("category_ids", [])
            if category_id in categories
        ]
        if filters["category"]:
            if not any(item.get("name_id") == filters["category"] for item in recipe_categories):
                continue

        if filters["ingredient"]:
            has_ingredient = False
            for item in recipe.get("ingredients", []):
                product = products.get(item.get("product_id"))
                if product and product.get("name_id") == filters["ingredient"]:
                    has_ingredient = True
                    break
            if not has_ingredient:
                continue

        names = [item["name"] for item in recipe_categories]
        items.append(
            {
                **recipe,
                "category_names": ", ".join(names) if names else "—",
                "active": active,
            }
        )
    return render(
        request,
        "recipes/list.html",
        {
            "recipes": items,
            "filters": filters,
            "filters_active": filters_are_active(filters),
            "clear_url": reverse("recipe_list"),
            "search_placeholder": "Search by name",
            "category_options": category_options,
            "ingredient_options": ingredient_options,
            "difficulty_options": DIFFICULTIES,
            "tag_options": tag_options,
            "time_options": TIME_FILTER_OPTIONS,
        },
    )

def recipe_detail(request, name_id):
    db = get_db()
    recipe = _decorate_recipe(_get_recipe_or_404(db, name_id), db)
    return render(request, "recipes/detail.html", {"recipe": recipe})


def recipe_create(request):
    db = get_db()
    ensure_indexes(db)
    product_options, product_catalog, products_by_id = _product_catalog(db)
    category_options = _recipe_category_options(db)
    errors = []
    form = _empty_form()

    if request.method == "POST":
        form, errors, document, name_taken = _process_recipe_post(request, db, products_by_id)
        if name_taken:
            already_exists(request, "recipe")
        if document is not None:
            try:
                db.recipes.insert_one({**document, "active": True})
            except DuplicateKeyError:
                already_exists(request, "recipe")
            else:
                created(request, "Recipe")
                return redirect("recipe_list")

    return render(
        request,
        "recipes/form.html",
        _recipe_form_page(
            form,
            errors,
            heading="Add recipe",
            submit_label="Create recipe",
            product_options=product_options,
            product_catalog=product_catalog,
            category_options=category_options,
            back_url=reverse("recipe_list"),
        ),
    )


def recipe_edit(request, name_id):
    db = get_db()
    ensure_indexes(db)
    recipe = _get_recipe_or_404(db, name_id)
    include_products = [item.get("product_id") for item in recipe.get("ingredients", [])]
    product_options, product_catalog, products_by_id = _product_catalog(
        db,
        include_ids=include_products,
    )
    category_options = _recipe_category_options(db, include_ids=recipe.get("category_ids", []))
    errors = []
    form = _form_from_recipe(recipe)

    if request.method == "POST":
        form, errors, document, name_taken = _process_recipe_post(
            request,
            db,
            products_by_id,
            exclude_id=recipe["_id"],
        )
        if name_taken:
            already_exists(request, "recipe")
        if document is not None:
            try:
                db.recipes.update_one(
                    {"_id": recipe["_id"]},
                    {"$set": {**document, "active": recipe.get("active", True)}},
                )
            except DuplicateKeyError:
                already_exists(request, "recipe")
            else:
                updated(request, "Recipe")
                return redirect("recipe_detail", name_id=document["name_id"])

    return render(
        request,
        "recipes/form.html",
        _recipe_form_page(
            form,
            errors,
            heading=f"Edit {recipe['name']}",
            submit_label="Save recipe",
            product_options=product_options,
            product_catalog=product_catalog,
            category_options=category_options,
            is_edit=True,
            name_id=recipe["name_id"],
            back_url=reverse("recipe_detail", args=[recipe["name_id"]]),
            back_label="Back to recipe",
        ),
    )


@require_POST
def recipe_set_active(request, name_id):
    db = get_db()
    recipe = _get_recipe_or_404(db, name_id)
    active = request.POST.get("active") == "1"
    db.recipes.update_one(
        {"_id": recipe["_id"]},
        {"$set": {"active": active}},
    )
    if active:
        reactivated(request, "Recipe")
    else:
        suspended(request, "Recipe")
    return _list_redirect(request)
