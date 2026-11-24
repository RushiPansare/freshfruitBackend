from django.contrib import admin
from .models import Fruit, Review, CartItem

admin.site.register(Fruit)
admin.site.register(Review)
admin.site.register(CartItem)