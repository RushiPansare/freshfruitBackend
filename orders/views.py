from decimal import Decimal
from django.db import transaction
from django.shortcuts import get_object_or_404
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from accounts.validators import check_name, check_phone, check_city, check_pincode
from shop.models import CartItem, Fruit
from .models import Order, OrderItem


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def create_order(request):
    cart = list(CartItem.objects.filter(user=request.user))
    if not cart:
        return Response({'error': 'Your cart is empty'}, status=400)

    d = request.data
    full_name = str(d.get('full_name', '')).strip()
    phone = str(d.get('phone', '')).strip()
    address = str(d.get('address', '')).strip()
    city = str(d.get('city', '')).strip()
    pincode = str(d.get('pincode', '')).strip()

    error = check_name(full_name, 'Full name') or check_phone(phone)
    if not error and not (10 <= len(address) <= 250):
        error = 'Address must be 10 to 250 characters'
    error = error or check_city(city) or check_pincode(pincode)
    if error:
        return Response({'error': error}, status=400)

    with transaction.atomic():
        fruits = {f.id: f for f in Fruit.objects.select_for_update().filter(id__in=[c.fruit_id for c in cart])}

        for c in cart:
            f = fruits[c.fruit_id]
            if f.stock_kg <= 0:
                return Response({'error': f.name + ' is out of stock. Please remove it from your cart.'}, status=400)
            if f.stock_kg < c.quantity_kg:
                return Response({'error': 'Only ' + str(f.stock_kg) + ' kg of ' + f.name + ' left. Please reduce the quantity in your cart.'}, status=400)

        total = sum(fruits[c.fruit_id].final_price * c.quantity_kg for c in cart)
        order = Order.objects.create(
            user=request.user, customer_email=request.user.email, total=total, status='PAID',
            full_name=full_name, phone=phone, address=address, city=city, pincode=pincode)

        for c in cart:
            f = fruits[c.fruit_id]
            OrderItem.objects.create(
                order=order, fruit=f, quantity_kg=c.quantity_kg,
                price_per_kg=f.final_price, original_price_per_kg=f.price_per_kg)
            f.stock_kg = f.stock_kg - c.quantity_kg
            f.save(update_fields=['stock_kg'])

        CartItem.objects.filter(user=request.user).delete()

    return Response({'order_id': order.id})


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def order_detail(request, pk):
    order = get_object_or_404(Order, pk=pk, user=request.user)
    items = []
    subtotal = Decimal('0')
    for i in order.items.select_related('fruit'):
        mrp = i.original_price_per_kg or i.price_per_kg
        subtotal += mrp * i.quantity_kg
        items.append({
            'name': i.fruit.name,
            'quantity_kg': float(i.quantity_kg),
            'mrp_per_kg': float(mrp),
            'price_per_kg': float(i.price_per_kg),
            'amount': float(i.price_per_kg * i.quantity_kg),
        })
    return Response({
        'id': order.id,
        'created': order.created,
        'status': order.status,
        'full_name': order.full_name,
        'phone': order.phone,
        'address': order.address,
        'city': order.city,
        'pincode': order.pincode,
        'items': items,
        'subtotal': float(round(subtotal, 2)),
        'total_discount': float(round(subtotal - order.total, 2)),
        'total': float(order.total),
    })