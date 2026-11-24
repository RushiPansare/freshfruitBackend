from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated, IsAuthenticatedOrReadOnly
from rest_framework.response import Response
from .models import Fruit, Review, CartItem
from .serializers import FruitSerializer, CartItemSerializer


class FruitViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Fruit.objects.all().order_by('-created')
    serializer_class = FruitSerializer
    permission_classes = [IsAuthenticatedOrReadOnly]

    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated])
    def review(self, request, pk=None):
        fruit = self.get_object()
        try:
            rating = int(request.data.get('rating', 0))
        except (TypeError, ValueError):
            rating = 0
        comment = str(request.data.get('comment', '')).strip()

        if rating < 1 or rating > 5:
            return Response({'error': 'Rating must be between 1 and 5'}, status=400)
        if len(comment) < 3:
            return Response({'error': 'Please write at least 3 characters in your review'}, status=400)
        if len(comment) > 500:
            return Response({'error': 'Review can be at most 500 characters'}, status=400)

        Review.objects.update_or_create(
            fruit=fruit, user=request.user,
            defaults={'rating': rating, 'comment': comment})
        return Response({'message': 'Review saved'})

class CartViewSet(viewsets.ModelViewSet):
    serializer_class = CartItemSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return CartItem.objects.filter(user=self.request.user).select_related('fruit')

    def create(self, request, *args, **kwargs):
        ser = self.get_serializer(data=request.data)
        ser.is_valid(raise_exception=True)
        fruit = ser.validated_data['fruit']
        qty = ser.validated_data.get('quantity_kg', 1)

        existing = CartItem.objects.filter(user=request.user, fruit=fruit).first()
        total_qty = qty + (existing.quantity_kg if existing else 0)

        if fruit.stock_kg <= 0:
            return Response({'error': fruit.name + ' is out of stock'}, status=400)
        if total_qty > fruit.stock_kg:
            return Response({'error': 'Only ' + str(fruit.stock_kg) + ' kg of ' + fruit.name + ' is available'}, status=400)

        if existing:
            existing.quantity_kg = total_qty
            existing.save()
            item = existing
        else:
            item = CartItem.objects.create(user=request.user, fruit=fruit, quantity_kg=qty)

        data = CartItemSerializer(item, context={'request': request}).data
        return Response(data, status=201)

    def perform_update(self, serializer):
        item = serializer.instance
        qty = serializer.validated_data.get('quantity_kg', item.quantity_kg)
        if qty > item.fruit.stock_kg:
            raise ValidationError({'error': 'Only ' + str(item.fruit.stock_kg) + ' kg of ' + item.fruit.name + ' is available'})
        serializer.save()