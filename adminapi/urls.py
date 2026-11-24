from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

router = DefaultRouter()
router.register('fruits', views.AdminFruitViewSet, basename='admin-fruits')

urlpatterns = [
    path('dashboard/', views.admin_dashboard),
    path('orders/', views.admin_orders),
    path('orders/<int:pk>/', views.admin_order_detail),
    path('customers/', views.admin_customers),
    path('customers/<int:pk>/', views.admin_customer_toggle),
    path('reviews/', views.admin_reviews),
    path('reviews/<int:pk>/', views.admin_review_delete),
    path('revenue/', views.admin_revenue),
    path('', include(router.urls)),
]