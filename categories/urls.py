from django.urls import path

from . import views

urlpatterns = [
    path("", views.category_hub, name="category_hub"),
    path("<str:kind>/", views.category_list, name="category_list"),
    path("<str:kind>/create/", views.category_create, name="category_create"),
    path("<str:kind>/<str:name_id>/edit/", views.category_edit, name="category_edit"),
    path("<str:kind>/<str:name_id>/active/", views.category_set_active, name="category_set_active"),
]
