# Paso 2.1 — esquemas de `product_categories` y `products`

Colección de productos: **`product_categories`** (antes `categories`).
Así no se confunde con tags o categorías de recetas cuando lleguemos a `recipes`.

El esquema del documento de categoría:

```python
{
    "name": "...",
    "name_id": "...",  # generado con generate_name_id(name), unique
    "description": "...",
    "active": True,
}
```

Las **17** categorías ya están en `recipe_hub.product_categories` (PyMongo 3.13, MongoDB 4.0 de Laragon). Datos: `seeds/product_categories.py`. Script: `seeds/load_product_categories.py`.

---

## Relación

```
product_categories._id
      ↑
      │  1 product_category → many products
      │
products.category_id
      ↑
      │  (más adelante)
      │
recipes.ingredients[].product_id
```

```
Product category → Product → Recipe ingredient
```

Ejemplos:

```
Dairy
 ├── Whole Milk
 ├── Skim Milk
 ├── Natural Yogurt
 ├── Greek Yogurt
 └── Cream

Oils & Fats
 ├── Olive Oil
 ├── Sunflower Oil
 └── Vegetable Oil

Condiments & Sauces
 ├── White Vinegar
 ├── Apple Cider Vinegar
 ├── Balsamic Vinegar
 ├── Mustard
 └── Soy Sauce

Water & Cooking Liquids
 └── Water

Fruits
 ├── Lemon
 ├── Orange
 └── Apple
```

Aceite, vinagre, agua, leche y yogur son **productos**, no categorías.

La variedad importa: no un único `Oil` o `Yogurt` si cambia la receta. Sustituciones entre productos compatibles, más adelante.

Ingrediente de receta (todavía no se implementa). El jugo de fruta no es un producto aparte: se resuelve con `preparation` sobre la fruta:

```python
{
    "product_id": lemon_id,
    "quantity": 1,
    "unit": "unit",
    "preparation": "juiced",
}
# Jugo de 1 limón

{
    "product_id": lemon_id,
    "quantity": 0.5,
    "unit": "unit",
    "preparation": "juiced",
}
# Jugo de medio limón
```

Jugo de naranja envasado, si algún día hace falta, sí podría ser un producto independiente.

---

## `product_categories`

| Campo | Tipo | Rol |
| --- | --- | --- |
| `_id` | ObjectId | clave |
| `name` | str | nombre visible |
| `description` | str | texto corto |
| `name_id` | str | identificador lógico único (`fish_seafood`) |
| `active` | bool | desactivar sin borrar |

### Las 17 esenciales

Cocina cotidiana, sin categorías demasiado específicas.

| name | name_id | Qué incluye |
| --- | --- | --- |
| Dairy | dairy | Leche, quesos, crema, yogur, manteca |
| Eggs | eggs | Huevos y derivados |
| Meat | meat | Carne vacuna, cerdo, cordero, etc. |
| Poultry | poultry | Pollo, pavo, pato, etc. |
| Fish & Seafood | fish_seafood | Pescados, camarones, calamar, mariscos |
| Vegetables | vegetables | Cebolla, papa, zanahoria, tomate, verduras de hoja |
| Fruits | fruits | Manzana, limón, naranja, banana (no “Lemon Juice”) |
| Grains & Cereals | grains_cereals | Arroz, avena, maíz, quinoa, etc. |
| Flours & Starches | flours_starches | Harinas, fécula, almidón |
| Legumes | legumes | Lentejas, garbanzos, porotos, arvejas secas |
| Nuts & Seeds | nuts_seeds | Nueces, almendras, maní, semillas |
| Herbs & Spices | herbs_spices | Perejil, orégano, pimienta, comino, canela |
| Oils & Fats | oils_fats | Aceites, grasa, margarina |
| Sweeteners | sweeteners | Azúcar, miel, edulcorantes |
| Condiments & Sauces | condiments_sauces | Vinagres, mostaza, salsa de soja |
| Water & Cooking Liquids | water_cooking_liquids | Agua, caldos / bases líquidas |
| Other | other | Productos que todavía no encajen bien |

`Water & Cooking Liquids` en vez de un `Liquids` genérico: deja lugar para Water, Sparkling Water, caldos, etc.

### Qué no va en esta colección

**No son categorías:** aceite, vinagre, agua, leche, yogur. Van en `products`.

**No hay producto Lemon Juice / Orange Juice** cuando la receta pide exprimir la fruta. Eso es `preparation: "juiced"` en el ingrediente. El jugo envasado sí podría ser producto aparte, más adelante.

**Beverages como categoría:** no. Leche → Dairy, agua → Water & Cooking Liquids, jugo de limón → Fruits + preparation.

**Categorías de recetas:** Desserts, Breakfast, Pizza, Pasta, Vegan, Vegetarian. Más adelante: tags o `recipe_categories`.

---

## `products`

| Campo | Tipo | Rol |
| --- | --- | --- |
| `_id` | ObjectId | clave |
| `name` | str | nombre canónico |
| `name_id` | str | identificador lógico único (`olive_oil`) |
| `description` | str | texto corto |
| `aliases` | list[str] | otros nombres para búsqueda |
| `category_id` | ObjectId | referencia a `product_categories._id` |
| `measurement_types` | list[str] | cómo se puede medir |
| `allowed_units` | list[str] | unidades permitidas (códigos) |
| `default_unit` | str | unidad por defecto (código) |
| `active` | bool | desactivar sin borrar |

`category_id` es referencia, no documento embebido.

No van (todavía): `price`, `stock`, `brand`, `expiration_date`.

Todavía no se cargan más products. Primera tanda: 27 esenciales. Se puede ampliar después (más carnes, pescados, etc.).

### Harina

```python
{
    "_id": ObjectId("..."),
    "name": "Flour 000",
    "description": "Refined wheat flour",
    "aliases": ["harina 000", "wheat flour"],
    "category_id": ObjectId("..."),  # Flours & Starches
    "measurement_types": ["mass", "culinary_volume"],
    "allowed_units": ["g", "kg", "cup", "tbsp"],
    "default_unit": "g",
    "active": True,
}
```

### Leche

```python
{
    "_id": ObjectId("..."),
    "name": "Whole Milk",
    "description": "Whole cow milk",
    "aliases": ["whole milk", "leche entera"],
    "category_id": ObjectId("..."),  # Dairy
    "measurement_types": ["volume", "culinary_volume"],
    "allowed_units": ["ml", "l", "cup", "tbsp"],
    "default_unit": "ml",
    "active": True,
}
```

### Huevo

```python
{
    "_id": ObjectId("..."),
    "name": "Egg",
    "description": "Chicken egg",
    "aliases": ["chicken egg"],
    "category_id": ObjectId("..."),  # Eggs
    "measurement_types": ["count", "mass"],
    "allowed_units": ["unit", "dozen", "half_dozen", "yolk", "white", "g"],
    "default_unit": "unit",
    "active": True,
}
```

---

## Unidades: códigos, no texto libre

| código | interfaz (ejemplo) |
| --- | --- |
| `g` | gramos |
| `kg` | kilogramos |
| `ml` | mililitros |
| `l` | litros |
| `unit` | unidad |
| `half_unit` | media unidad |
| `clove` | diente de ajo |
| `dozen` | docena |
| `half_dozen` | media docena |
| `yolk` | yema |
| `white` | clara |
| `tsp` | cucharadita |
| `tbsp` | cucharada |
| `cup` | taza |
| `pinch` | pizca |
| `handful` | puñado |
| `to_taste` | a gusto |

### Tipos de medición

| código | uso |
| --- | --- |
| `mass` | peso (`g`, `kg`) |
| `volume` | volumen líquido (`ml`, `l`) |
| `culinary_volume` | medidas de cocina (`cup`, `tbsp`, `tsp`) |
| `count` | conteo (`unit`, `half_unit`, `clove`, `dozen`, …) |
| `informal` | medidas de cocina imprecisas (`pinch`, `handful`, `to_taste`) |

---

## Siguiente (Paso 2.2)

`product_categories` queda cerrada con estas 17.

Primera carga de `products`: 27 esenciales en `seeds/products.py`, insertados con `seeds/load_products.py`.

El seed usa `category_name_id` solo para leer. El script hace `find_one({"name_id": ...})`, pone `category_id` y `insert_many()`. El documento en MongoDB **no** guarda `"category": "Dairy"`.

Water apunta a `water-cooking-liquids` (no a una categoría llamada Liquids).

Usamos **PyMongo 3.13.0** porque Laragon trae MongoDB 4.0.3; PyMongo 4 exige 4.2+.
