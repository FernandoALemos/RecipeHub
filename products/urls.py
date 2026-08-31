from django.urls import path

from . import views

urlpatterns = [
    path("", views.product_list, name="product_list"),
    path("create/", views.product_create, name="product_create"),
    path("<str:name_id>/edit/", views.product_edit, name="product_edit"),
    path("<str:name_id>/active/", views.product_set_active, name="product_set_active"),
]
