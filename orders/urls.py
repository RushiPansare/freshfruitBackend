from django.urls import path
from . import views

urlpatterns = [
    path('create/', views.create_order),
    path('<int:pk>/', views.order_detail),
]