from django.db import models
from django.contrib.auth.models import User


class Fruit(models.Model):
    name = models.CharField(max_length=100)
    description = models.TextField()
    image = models.ImageField(upload_to='fruits/')
    price_per_kg = models.DecimalField(max_digits=8, decimal_places=2)
    discount_percent = models.PositiveIntegerField(default=0)
    stock_kg = models.DecimalField(max_digits=8, decimal_places=2, default=100)
    created = models.DateTimeField(auto_now_add=True)

    @property
    def final_price(self):
        return round(self.price_per_kg * (100 - self.discount_percent) / 100, 2)

    def __str__(self):
        return self.name


class Review(models.Model):
    fruit = models.ForeignKey(Fruit, related_name='reviews', on_delete=models.CASCADE)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    rating = models.PositiveSmallIntegerField()  # 1 to 5
    comment = models.TextField(blank=True)
    created = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('fruit', 'user')


class CartItem(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    fruit = models.ForeignKey(Fruit, on_delete=models.CASCADE)
    quantity_kg = models.DecimalField(max_digits=5, decimal_places=2, default=1)

    class Meta:
        unique_together = ('user', 'fruit')