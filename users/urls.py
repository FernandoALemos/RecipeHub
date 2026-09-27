from django.urls import path

from . import views

urlpatterns = [
    path("register/", views.register, name="register"),
    path("login/", views.login, name="login"),
    path("logout/", views.logout, name="logout"),
    path("profile/", views.profile, name="profile"),
    path("users/", views.user_list, name="user_list"),
    path("users/create/", views.user_create, name="user_create"),
    path("users/<str:username>/", views.user_detail, name="user_detail"),
    path("users/<str:username>/edit/", views.user_edit, name="user_edit"),
    path("users/<str:username>/active/", views.user_set_active, name="user_set_active"),
]
