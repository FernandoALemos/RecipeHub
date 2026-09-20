from django.urls import include, path

urlpatterns = [
    path("", include("core.urls")),
    path("categories/", include("categories.urls")),
    path("products/", include("products.urls")),
    path("recipes/", include("recipes.urls")),
]
