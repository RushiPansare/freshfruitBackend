from django.urls import path
from . import views

urlpatterns = [
    path('register/', views.register),
    path('login/', views.login_view),
    path('profile/', views.profile),
    path('change-password/', views.change_password),
    path('forgot-password/', views.forgot_password),
]