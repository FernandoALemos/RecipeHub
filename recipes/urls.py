from django.urls import path

from . import views

urlpatterns = [
    path("", views.recipe_list, name="recipe_list"),
    path("create/", views.recipe_create, name="recipe_create"),
    path("<str:name_id>/", views.recipe_detail, name="recipe_detail"),
    path("<str:name_id>/edit/", views.recipe_edit, name="recipe_edit"),
    path("<str:name_id>/active/", views.recipe_set_active, name="recipe_set_active"),
]
