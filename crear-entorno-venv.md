# RecipeHub — Paso 1: entorno Python / Django

## Separación de caminos

Antes, para aprender MongoDB (proyecto `game_library`):

```
mongosh
   ↓
JavaScript
   ↓
MongoDB
```

Ahora, en RecipeHub:

```
Python / Django
   ↓
driver / ODM de MongoDB
   ↓
MongoDB
```

La base no sabe ni le importa si el documento se creó desde JavaScript, Python, Compass o Django. Al final recibe BSON.

`game_library` queda como práctica de MongoDB / mongosh.
RecipeHub es el salto a usar MongoDB desde una aplicación Python real.

---

## Paso 1 (ajustado)

```powershell
mkdir recipe_hub
cd recipe_hub

python -m venv .venv
.\.venv\Scripts\activate
```

En este repo la carpeta ya existe: `C:\Programas\Repos\RecipeHub`.

CMD, si no usás PowerShell:

```cmd
.venv\Scripts\activate
```

Cuando está activo, el prompt muestra `(.venv)`.

Desactivar:

```powershell
deactivate
```

---

## Django (ya instalado)

Con el entorno activado:

```powershell
pip install django
python -m django --version
pip freeze > requirements.txt
```

Quedó **Django 5.2.17**. `requirements.txt` actual:

```
asgiref==3.12.1
Django==5.2.17
sqlparse==0.6.0
typing_extensions==4.16.0
tzdata==2026.3
```

Recrear en otra máquina:

```powershell
cd C:\Programas\Repos\RecipeHub
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
```

---

## No instalar todavía el acceso a MongoDB

No instalar al azar:

- PyMongo
- MongoEngine
- Djongo

No son la misma cosa.

| Capa | Rol |
| --- | --- |
| PyMongo | driver: Python habla BSON con MongoDB |
| MongoEngine | ODM sobre PyMongo |
| Djongo | intenta mapear el ORM de Django a MongoDB |

Si el curso arranca con `Python → MongoDB` vía **PyMongo**, empezamos con PyMongo.
Si después introduce MongoEngine o la integración con Django, avanzamos cuando llegues ahí.

Aprendizaje por capas:

```
Python
   ↓
PyMongo
   ↓
MongoDB

        luego

Django
   ↓
MongoEngine / Djongo / lo que use el curso
   ↓
MongoDB
```

Así se entiende qué está haciendo Django por detrás.

**Antes de instalar cualquier paquete de MongoDB:** pasame qué librería usa esa sección del curso (o una captura / archivo).

A partir de ahí hacemos RecipeHub en Python, incluyendo creación/acceso a `recipe_hub` y sus colecciones desde código, si coincide con lo que estás viendo.

---

## Equivalente conceptual (todavía no es código ejecutable)

En mongosh:

```javascript
db.products.insertOne({
    name: "Harina",
    default_unit: "g"
})
```

En Python, el documento es un dict. El driver que elijamos (cuando el curso lo indique) es quien lo inserta:

```python
product = {
    "name": "Harina",
    "default_unit": "g",
}
```

---

## Qué no se hizo todavía (a propósito)

- No se corrió `django-admin startproject`
- No se conectó Django con MongoDB
- No se instaló PyMongo / MongoEngine / Djongo

Las colecciones ya existen en `recipe_hub` (ver `comandos-mongodb.js` como registro de lo creado en el shell). El desarrollo de RecipeHub sigue en Python, no en mongosh.
