from django.contrib import messages
from django.http import Http404
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST
from pymongo.errors import DuplicateKeyError

from config.mongo import get_db
from core.ids import generate_name_id
from core.store import ensure_indexes, find_by_name_id

from .kinds import CATEGORY_KINDS


def _kind_config(kind):
    config = CATEGORY_KINDS.get(kind)
    if config is None:
        raise Http404("Unknown category kind.")
    return config


def _collection(db, kind):
    return db[_kind_config(kind)["collection"]]


def _get_category_or_404(db, kind, name_id):
    category = find_by_name_id(_collection(db, kind), name_id)
    if category is None:
        raise Http404("Category not found.")
    return category


def _form_from_post(post):
    return {
        "name": post.get("name", "").strip(),
        "description": post.get("description", "").strip(),
        "active": post.get("active") == "on",
    }


def _page_context(kind, **extra):
    return {"kind": kind, "kind_config": _kind_config(kind), **extra}


def category_hub(request):
    return render(request, "categories/hub.html")


def category_list(request, kind):
    _kind_config(kind)
    db = get_db()
    items = [
        {**item, "active": item.get("active", True)}
        for item in _collection(db, kind).find().sort("name", 1)
    ]
    return render(
        request,
        "categories/list.html",
        _page_context(kind, categories=items),
    )


def category_create(request, kind):
    config = _kind_config(kind)
    errors = []
    form = {"name": "", "description": "", "active": True}

    if request.method == "POST":
        form = _form_from_post(request.POST)
        form["active"] = True
        name_id = generate_name_id(form["name"])

        if not form["name"]:
            errors.append("Name is required.")
        if not name_id:
            errors.append("Name could not be converted into a unique name_id.")

        db = get_db()
        ensure_indexes(db)
        collection = _collection(db, kind)
        if name_id and find_by_name_id(collection, name_id):
            errors.append(f"A category with name_id '{name_id}' already exists.")

        if not errors:
            try:
                collection.insert_one(
                    {
                        "name": form["name"],
                        "name_id": name_id,
                        "description": form["description"],
                        "active": True,
                    }
                )
            except DuplicateKeyError:
                errors.append(f"A category with name_id '{name_id}' already exists.")
            else:
                messages.success(request, f"Created category {form['name']}.")
                return redirect("category_list", kind=kind)

    return render(
        request,
        "categories/form.html",
        _page_context(
            kind,
            form=form,
            errors=errors,
            is_edit=False,
            heading=config["add_heading"],
            submit_label=config["create_label"],
        ),
    )


def category_edit(request, kind, name_id):
    config = _kind_config(kind)
    db = get_db()
    ensure_indexes(db)
    collection = _collection(db, kind)
    category = _get_category_or_404(db, kind, name_id)
    errors = []
    form = {
        "name": category.get("name", ""),
        "description": category.get("description", ""),
        "active": category.get("active", True),
    }

    if request.method == "POST":
        form = _form_from_post(request.POST)
        next_name_id = generate_name_id(form["name"])

        if not form["name"]:
            errors.append("Name is required.")
        if not next_name_id:
            errors.append("Name could not be converted into a unique name_id.")
        elif find_by_name_id(collection, next_name_id, exclude_id=category["_id"]):
            errors.append(f"A category with name_id '{next_name_id}' already exists.")

        if not errors:
            try:
                collection.update_one(
                    {"_id": category["_id"]},
                    {
                        "$set": {
                            "name": form["name"],
                            "name_id": next_name_id,
                            "description": form["description"],
                            "active": form["active"],
                        }
                    },
                )
            except DuplicateKeyError:
                errors.append(f"A category with name_id '{next_name_id}' already exists.")
            else:
                messages.success(request, f"Updated category {form['name']}.")
                return redirect("category_list", kind=kind)

    return render(
        request,
        "categories/form.html",
        _page_context(
            kind,
            form=form,
            errors=errors,
            is_edit=True,
            heading=f"Edit {category['name']}",
            submit_label=config["save_label"],
            name_id=category["name_id"],
        ),
    )


@require_POST
def category_set_active(request, kind, name_id):
    _kind_config(kind)
    db = get_db()
    category = _get_category_or_404(db, kind, name_id)
    active = request.POST.get("active") == "1"
    _collection(db, kind).update_one(
        {"_id": category["_id"]},
        {"$set": {"active": active}},
    )
    if active:
        messages.success(request, f"Reactivated category {category['name']}.")
    else:
        messages.success(request, f"Suspended category {category['name']}.")
    return redirect("category_list", kind=kind)
