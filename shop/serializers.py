from django.db.models import Avg
from rest_framework import serializers
from .models import Fruit, Review, CartItem


class ReviewSerializer(serializers.ModelSerializer):
    user_name = serializers.CharField(source='user.first_name', read_only=True)

    class Meta:
        model = Review
        fields = ['id', 'user_name', 'rating', 'comment', 'created']


class FruitSerializer(serializers.ModelSerializer):
    final_price = serializers.ReadOnlyField()
    avg_rating = serializers.SerializerMethodField()
    review_count = serializers.SerializerMethodField()
    reviews = ReviewSerializer(many=True, read_only=True)

    class Meta:
        model = Fruit
        fields = ['id', 'name', 'description', 'image', 'price_per_kg',
                  'discount_percent', 'final_price', 'stock_kg',
                  'avg_rating', 'review_count', 'reviews']

    def get_avg_rating(self, obj):
        avg = obj.reviews.aggregate(a=Avg('rating'))['a']
        return round(avg, 1) if avg else 0

    def get_review_count(self, obj):
        return obj.reviews.count()


class CartItemSerializer(serializers.ModelSerializer):
    fruit = FruitSerializer(read_only=True)
    fruit_id = serializers.PrimaryKeyRelatedField(
        queryset=Fruit.objects.all(), source='fruit', write_only=True)

    class Meta:
        model = CartItem
        fields = ['id', 'fruit', 'fruit_id', 'quantity_kg']