// ============================================================
// RECIPEHUB — registro de la base y las colecciones
// ============================================================
//
// Este archivo documenta lo que YA existe en MongoDB.
// Se creó una vez desde el shell de Laragon (mongo.exe / mongosh).
//
// NO es el camino de desarrollo de RecipeHub.
//
//   game_library  →  práctica MongoDB / mongosh / JavaScript
//   RecipeHub     →  aplicación Python / Django → driver/ODM → MongoDB
//
// La base no distingue el origen del documento. Recibe BSON igual
// si vino de JavaScript, Python, Compass o Django.
//
// El acceso cotidiano a recipe_hub (crear, leer, insertar) se hará
// desde Python cuando el curso indique la librería:
// PyMongo, MongoEngine o Djongo. No instalar ninguna al azar.
//
// En Laragon (MongoDB 4.0.3) el shell es:
//   C:\laragon\bin\mongodb\mongodb-4.0.3\mongo.exe
//
// Si MongoDB no está corriendo:
//   C:\laragon\bin\mongodb\mongodb-4.0.3\mongod.exe --config C:\laragon\bin\mongodb\mongodb-4.0.3\mongod.conf
//
// MongoDB no crea la base solo con `use recipe_hub`.
// Aparece al crear una colección o guardar un documento.
// ============================================================


use recipe_hub


// ETAPA 1
db.createCollection("users")
db.createCollection("products")
db.createCollection("product_categories")
db.createCollection("recipes")

// ETAPA 2
db.createCollection("meal_plans")

// ETAPA 3
db.createCollection("shopping_lists")

// ETAPA 4
db.createCollection("reviews")
db.createCollection("favorites")


show collections

// favorites
// meal_plans
// product_categories
// products
// recipes
// reviews
// shopping_lists
// users
//
// Crearlas no implica implementarlas ahora.
// Si favorites termina mejor como array de ObjectId en users:
//   db.favorites.drop()
