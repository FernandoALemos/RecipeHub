# RecipeHub

Kitchen catalog app built with Django + MongoDB. Categories, products and recipes
are stored as Mongo documents. Portable backups live in `data/*.json`.

## Requirements

On a clean Windows PC you need:

- Git
- Python 3.10+
- MongoDB Community Server running on `127.0.0.1:27017`

Laragon is optional. MongoDB Compass is optional (useful to inspect data).

## Fresh setup

```powershell
git clone https://github.com/FernandoALemos/RecipeHub.git
cd RecipeHub

python -m venv .venv
.\.venv\Scripts\Activate.ps1

pip install -r requirements.txt

copy .env.example .env
# edit .env if needed

python manage.py import_data --clear
python manage.py runserver 127.0.0.1:8000
```

Open [http://127.0.0.1:8000/](http://127.0.0.1:8000/).

After a clean import from an up-to-date `data/*.json` snapshot you should see the same counts as your export. A recent live snapshot looks like:

- 17 product categories
- 18 recipe categories
- 36 products
- 1+ recipes (for example Pizza Muzzarella)

Refresh the portable backup anytime with:

```powershell
python manage.py export_data
```

## Environment variables

`.env` is loaded automatically by Django settings. Start from `.env.example`:

| Variable | Default | Purpose |
|---|---|---|
| `DJANGO_SECRET_KEY` | insecure fallback | Django secret |
| `DJANGO_DEBUG` | `1` | Debug mode |
| `DJANGO_ALLOWED_HOSTS` | `127.0.0.1,localhost` | Allowed hosts |
| `MONGO_URI` | `mongodb://127.0.0.1:27017` | Mongo connection |
| `MONGO_DB_NAME` | `recipe_hub` | Database name |

## Export / import

Export current Mongo data to portable JSON (`name_id` references, no ObjectIds):

```powershell
python manage.py export_data
```

Writes:

- `data/product_categories.json`
- `data/recipe_categories.json`
- `data/products.json`
- `data/recipes.json`

Import JSON back into Mongo (order matters: categories → products → recipes):

```powershell
python manage.py import_data --clear
```

Safe dry-run style test on a separate database without touching `recipe_hub`:

```powershell
python manage.py export_data --output-dir tmp_export
python manage.py import_data --database recipe_hub_test_import --input-dir tmp_export --clear
```

Or import straight from `data/`:

```powershell
python manage.py import_data --database recipe_hub_test_import --clear
```

ObjectIds are generated again on each machine. Relations are rebuilt from:

- `category_name_id`
- `category_name_ids`
- `product_name_id`

## Day-to-day

```powershell
.\.venv\Scripts\Activate.ps1
python manage.py runserver 127.0.0.1:8000
```

## Notes

- Do not copy `.venv` between PCs; create a new one with `python -m venv .venv`.
- Do not commit `.env`.
- SQLite (`db.sqlite3`) is only Django’s default DB; kitchen data lives in MongoDB.
