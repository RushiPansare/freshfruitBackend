from django.db import models
from django.contrib.auth.models import User
from shop.models import Fruit


class Order(models.Model):
    # SET_NULL keeps the order (and your revenue) even if the customer is deleted
    user = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL)
    customer_email = models.CharField(max_length=254, blank=True, default='')
    full_name = models.CharField(max_length=100)
    phone = models.CharField(max_length=15)
    address = models.TextField()
    city = models.CharField(max_length=60)
    pincode = models.CharField(max_length=10)
    total = models.DecimalField(max_digits=10, decimal_places=2)
    razorpay_order_id = models.CharField(max_length=100, blank=True)
    razorpay_payment_id = models.CharField(max_length=100, blank=True)
    status = models.CharField(max_length=20, default='PENDING')  # PAID / PACKED / SHIPPED / DELIVERED / CANCELLED
    created = models.DateTimeField(auto_now_add=True)


class OrderItem(models.Model):
    order = models.ForeignKey(Order, related_name='items', on_delete=models.CASCADE)
    fruit = models.ForeignKey(Fruit, on_delete=models.PROTECT)
    quantity_kg = models.DecimalField(max_digits=5, decimal_places=2)
    price_per_kg = models.DecimalField(max_digits=8, decimal_places=2)  # price after discount
    original_price_per_kg = models.DecimalField(max_digits=8, decimal_places=2, default=0)  # price before discount