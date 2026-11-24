from datetime import timedelta
from django.contrib.auth.models import User
from django.db import transaction
from django.db.models import Count, F, ProtectedError, Q, Sum
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import serializers, viewsets
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import BasePermission
from rest_framework.response import Response
from orders.models import Order, OrderItem
from shop.models import Fruit, Review

LOW_STOCK = 10
STATUSES = ['PAID', 'PACKED', 'SHIPPED', 'DELIVERED', 'CANCELLED']


class IsAdmin(BasePermission):
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.is_staff)


# ---------------- Products ----------------
class AdminFruitSerializer(serializers.ModelSerializer):
    final_price = serializers.ReadOnlyField()

    class Meta:
        model = Fruit
        fields = ['id', 'name', 'description', 'image', 'price_per_kg',
                  'discount_percent', 'final_price', 'stock_kg']

    def validate_price_per_kg(self, v):
        if v <= 0:
            raise serializers.ValidationError('Price must be greater than 0')
        return v

    def validate_discount_percent(self, v):
        if v > 100:
            raise serializers.ValidationError('Discount cannot be more than 100')
        return v

    def validate_stock_kg(self, v):
        if v < 0:
            raise serializers.ValidationError('Stock cannot be negative')
        return v

    def validate_name(self, v):
        v = v.strip()
        if len(v) < 2:
            raise serializers.ValidationError('Name must be at least 2 characters')
        return v


class AdminFruitViewSet(viewsets.ModelViewSet):
    queryset = Fruit.objects.all().order_by('-created')
    serializer_class = AdminFruitSerializer
    permission_classes = [IsAdmin]

    def destroy(self, request, *args, **kwargs):
        try:
            return super().destroy(request, *args, **kwargs)
        except ProtectedError:
            return Response({'error': 'This fruit is part of past orders and cannot be deleted. Set its stock to 0 instead.'}, status=400)


# ---------------- Orders ----------------
def order_summary(o):
    return {
        'id': o.id,
        'user_id': o.user_id,   # empty when the customer was deleted
        'customer': o.full_name,
        'email': o.customer_email or (o.user.email if o.user else ''),
        'phone': o.phone,
        'city': o.city,
        'total': float(o.total),
        'status': o.status,
        'created': o.created,
        'items_count': o.items.count(),
    }

def order_full(o):
    data = order_summary(o)
    items = []
    for i in o.items.select_related('fruit'):
        items.append({
            'name': i.fruit.name,
            'quantity_kg': float(i.quantity_kg),
            'price_per_kg': float(i.price_per_kg),
            'amount': float(i.price_per_kg * i.quantity_kg),
        })
    data.update({'address': o.address, 'pincode': o.pincode, 'items': items})
    return data


@api_view(['GET'])
@permission_classes([IsAdmin])
def admin_orders(request):
    qs = Order.objects.select_related('user').order_by('-created')
    st = request.query_params.get('status')
    q = request.query_params.get('q', '').strip()
    if st:
        qs = qs.filter(status=st)
    if q:
        f = Q(full_name__icontains=q) | Q(customer_email__icontains=q) | Q(user__email__icontains=q) | Q(phone__icontains=q)
        if q.isdigit():
            f |= Q(id=int(q))
        qs = qs.filter(f)
    return Response([order_summary(o) for o in qs[:200]])


@api_view(['GET', 'PATCH'])
@permission_classes([IsAdmin])
def admin_order_detail(request, pk):
    order = get_object_or_404(Order.objects.select_related('user'), pk=pk)

    if request.method == 'PATCH':
        new = request.data.get('status')
        if new not in STATUSES:
            return Response({'error': 'Invalid status'}, status=400)
        if order.status == 'CANCELLED' and new != 'CANCELLED':
            return Response({'error': 'A cancelled order cannot be reopened'}, status=400)
        with transaction.atomic():
            if new == 'CANCELLED' and order.status != 'CANCELLED':
                # put the fruits back into stock
                for it in order.items.all():
                    Fruit.objects.filter(pk=it.fruit_id).update(stock_kg=F('stock_kg') + it.quantity_kg)
            order.status = new
            order.save()

    return Response(order_full(order))


# ---------------- Dashboard ----------------
@api_view(['GET'])
@permission_classes([IsAdmin])
def admin_dashboard(request):
    valid = Order.objects.exclude(status='CANCELLED')
    revenue = valid.aggregate(s=Sum('total'))['s'] or 0

    buckets = {}
    since = timezone.now() - timedelta(days=8)
    for o in valid.filter(created__gte=since):
        k = timezone.localtime(o.created).date()
        buckets[k] = buckets.get(k, 0) + float(o.total)
    today = timezone.localdate()
    days = []
    for n in range(6, -1, -1):
        d = today - timedelta(days=n)
        days.append({'date': d.strftime('%d %b'), 'revenue': buckets.get(d, 0)})

    low = Fruit.objects.filter(stock_kg__lte=LOW_STOCK).order_by('stock_kg')
    recent = Order.objects.select_related('user').order_by('-created')[:5]

    return Response({
        'revenue': float(revenue),
        'orders': Order.objects.count(),
        'pending_orders': Order.objects.filter(status__in=['PAID', 'PACKED']).count(),
        'customers': User.objects.filter(is_staff=False).count(),
        'products': Fruit.objects.count(),
        'low_stock_count': low.count(),
        'last_7_days': days,
        'recent_orders': [order_summary(o) for o in recent],
        'low_stock': [{'id': f.id, 'name': f.name, 'stock_kg': float(f.stock_kg)} for f in low[:8]],
    })


# ---------------- Customers ----------------
@api_view(['GET'])
@permission_classes([IsAdmin])
def admin_customers(request):
    q = request.query_params.get('q', '').strip()
    users = User.objects.filter(is_staff=False)
    if q:
        users = users.filter(Q(first_name__icontains=q) | Q(email__icontains=q))
    users = users.annotate(
        order_count=Count('order', distinct=True),
        spent=Sum('order__total', filter=~Q(order__status='CANCELLED')),
    ).order_by('-date_joined')
    return Response([{
        'id': u.id, 'name': u.first_name, 'email': u.email, 'joined': u.date_joined,
        'last_login': u.last_login,
        'orders': u.order_count, 'spent': float(u.spent or 0), 'is_active': u.is_active,
    } for u in users])


@api_view(['GET', 'PATCH', 'DELETE'])
@permission_classes([IsAdmin])
def admin_customer_toggle(request, pk):
    u = get_object_or_404(User, pk=pk, is_staff=False)

    # DELETE: remove the customer and all their data (orders, cart, reviews) from the database
    if request.method == 'DELETE':
        name = u.first_name or u.email
        u.delete()
        return Response({'message': name + ' deleted successfully'})
    # PATCH: block or unblock the customer
    if request.method == 'PATCH':
        u.is_active = bool(request.data.get('is_active'))
        u.save()
        return Response({'id': u.id, 'is_active': u.is_active})

    # GET: full customer profile
    orders = list(Order.objects.filter(user=u).order_by('-created'))
    valid = [o for o in orders if o.status != 'CANCELLED']
    total_spent = sum(float(o.total) for o in valid)

    order_fruits = {}
    bought = {}
    total_kg = 0.0
    items = OrderItem.objects.filter(order__user=u).select_related('fruit', 'order')
    for it in items:
        qty = float(it.quantity_kg)
        order_fruits.setdefault(it.order_id, []).append(it.fruit.name + ' (' + str(qty) + ' kg)')
        if it.order.status == 'CANCELLED':
            continue
        b = bought.setdefault(it.fruit_id, {
            'id': it.fruit_id,
            'name': it.fruit.name,
            'image': request.build_absolute_uri(it.fruit.image.url) if it.fruit.image else '',
            'kg': 0.0,
            'orders': set(),
            'spent': 0.0,
        })
        b['kg'] += qty
        b['orders'].add(it.order_id)
        b['spent'] += float(it.price_per_kg * it.quantity_kg)
        total_kg += qty

    fruits = sorted(
        [{
            'id': b['id'], 'name': b['name'], 'image': b['image'],
            'kg': round(b['kg'], 2), 'times': len(b['orders']), 'spent': round(b['spent'], 2),
        } for b in bought.values()],
        key=lambda x: x['spent'], reverse=True)

    seen = set()
    addresses = []
    for o in orders:
        key = (o.address, o.city, o.pincode)
        if key in seen:
            continue
        seen.add(key)
        addresses.append({
            'name': o.full_name, 'phone': o.phone, 'address': o.address,
            'city': o.city, 'pincode': o.pincode,
        })

    reviews = list(Review.objects.filter(user=u).select_related('fruit').order_by('-created'))
    avg_rating = round(sum(r.rating for r in reviews) / len(reviews), 1) if reviews else 0

    return Response({
        'id': u.id,
        'name': u.first_name,
        'email': u.email,
        'phone': orders[0].phone if orders else '',
        'joined': u.date_joined,
        'last_login': u.last_login,
        'is_active': u.is_active,
        'stats': {
            'total_orders': len(orders),
            'cancelled': len(orders) - len(valid),
            'total_spent': round(total_spent, 2),
            'avg_order': round(total_spent / len(valid), 2) if valid else 0,
            'total_kg': round(total_kg, 2),
            'reviews': len(reviews),
            'avg_rating': avg_rating,
        },
        'orders': [{
            'id': o.id, 'created': o.created, 'status': o.status, 'total': float(o.total),
            'city': o.city, 'items': order_fruits.get(o.id, []),
        } for o in orders],
        'fruits': fruits,
        'addresses': addresses,
        'reviews': [{
            'id': r.id, 'fruit': r.fruit.name, 'rating': r.rating,
            'comment': r.comment, 'created': r.created,
        } for r in reviews],
    })


# ---------------- Reviews ----------------
@api_view(['GET'])
@permission_classes([IsAdmin])
def admin_reviews(request):
    qs = Review.objects.select_related('user', 'fruit').order_by('-created')
    return Response([{
        'id': r.id, 'fruit': r.fruit.name, 'user': r.user.first_name or r.user.email,
        'rating': r.rating, 'comment': r.comment, 'created': r.created,
    } for r in qs])


@api_view(['DELETE'])
@permission_classes([IsAdmin])
def admin_review_delete(request, pk):
    get_object_or_404(Review, pk=pk).delete()
    return Response(status=204)


# ---------------- Revenue chart ----------------
@api_view(['GET'])
@permission_classes([IsAdmin])
def admin_revenue(request):
    try:
        days = int(request.query_params.get('days', 30))
    except ValueError:
        days = 30
    days = max(1, min(days, 365))

    valid = Order.objects.exclude(status='CANCELLED')
    today = timezone.localdate()
    since = timezone.now() - timedelta(days=days + 2)

    buckets = {}
    for o in valid.filter(created__gte=since):
        k = timezone.localtime(o.created).date()
        b = buckets.setdefault(k, {'revenue': 0, 'orders': 0})
        b['revenue'] += float(o.total)
        b['orders'] += 1

    series = []
    for n in range(days - 1, -1, -1):
        d = today - timedelta(days=n)
        b = buckets.get(d, {'revenue': 0, 'orders': 0})
        series.append({
            'date': d.strftime('%d %b'),
            'full_date': d.strftime('%d %b %Y'),
            'revenue': round(b['revenue'], 2),
            'orders': b['orders'],
        })
    return Response(series)