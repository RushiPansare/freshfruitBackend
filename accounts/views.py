import math
import time
from django.conf import settings
from django.contrib.auth import authenticate
from django.contrib.auth.models import User, update_last_login
from django.core.cache import cache
from django.core.mail import send_mail
from rest_framework.decorators import api_view, permission_classes, authentication_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework_simplejwt.tokens import RefreshToken
from .validators import check_name, check_email, password_error


def send_welcome_email(user):
    send_mail(
        subject='Welcome to FreshFruits',
        message=(
            'Hi ' + user.first_name + ',\n\n'
            'Your account on the FreshFruits platform has been created successfully.\n'
            'You can now log in and shop fresh fruits at the best prices.\n\n'
            'Happy shopping!\n'
            'Team FreshFruits'
        ),
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[user.email],
        fail_silently=True,
    )


@api_view(['POST'])
@authentication_classes([])
@permission_classes([AllowAny])
def register(request):
    name = str(request.data.get('name', '')).strip()
    email = str(request.data.get('email', '')).strip().lower()
    password = str(request.data.get('password', ''))

    error = check_name(name, 'Full name') or check_email(email) or password_error(password)
    if error:
        return Response({'error': error}, status=400)
    if User.objects.filter(username=email).exists():
        return Response({'error': 'This email is already registered'}, status=400)

    user = User.objects.create_user(username=email, email=email, password=password, first_name=name)
    send_welcome_email(user)
    return Response({'message': 'Registered successfully'}, status=201)


@api_view(['GET', 'PATCH'])
@permission_classes([IsAuthenticated])
def profile(request):
    u = request.user

    if request.method == 'PATCH':
        name = str(request.data.get('name', '')).strip()
        email = str(request.data.get('email', '')).strip().lower()
        error = check_name(name, 'Full name') or check_email(email)
        if error:
            return Response({'error': error}, status=400)
        if User.objects.filter(username=email).exclude(pk=u.pk).exists():
            return Response({'error': 'This email is already used by another account'}, status=400)
        u.first_name = name
        u.email = email
        u.username = email
        u.save()

    return Response({'name': u.first_name, 'email': u.email, 'joined': u.date_joined, 'is_admin': u.is_staff})


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def change_password(request):
    old = str(request.data.get('old_password', ''))
    new = str(request.data.get('new_password', ''))
    confirm = str(request.data.get('confirm_password', ''))

    if not request.user.check_password(old):
        return Response({'error': 'Existing password is incorrect'}, status=400)
    error = password_error(new)
    if error:
        return Response({'error': error}, status=400)
    if new == old:
        return Response({'error': 'New password must be different from the existing password'}, status=400)
    if new != confirm:
        return Response({'error': 'New password and confirm password do not match'}, status=400)

    request.user.set_password(new)
    request.user.save()
    return Response({'message': 'Password changed successfully'})


@api_view(['POST'])
@authentication_classes([])
@permission_classes([AllowAny])
def forgot_password(request):
    email = str(request.data.get('email', '')).strip().lower()
    new = str(request.data.get('new_password', ''))
    confirm = str(request.data.get('confirm_password', ''))

    error = check_email(email) or password_error(new)
    if error:
        return Response({'error': error}, status=400)
    if new != confirm:
        return Response({'error': 'New password and confirm password do not match'}, status=400)

    try:
        user = User.objects.get(username=email)
    except User.DoesNotExist:
        return Response({'error': 'No account found with this email'}, status=404)

    user.set_password(new)
    user.save()
    return Response({'message': 'Password updated successfully'})


MAX_ATTEMPTS = 3
LOCK_SECONDS = 60


@api_view(['POST'])
@authentication_classes([])
@permission_classes([AllowAny])
def login_view(request):
    email = str(request.data.get('username', '')).strip().lower()
    password = str(request.data.get('password', ''))

    fail_key = 'login_fails:' + email
    lock_key = 'login_locked_until:' + email
    now = time.time()

    locked_until = cache.get(lock_key)
    if locked_until and locked_until > now:
        return Response({
            'error': 'Too many wrong attempts. Please try again after 1 minute.',
            'locked': True,
            'retry_after': math.ceil(locked_until - now),
        }, status=429)

    user = authenticate(username=email, password=password)

    if user is None:
        attempts = cache.get(fail_key, 0) + 1
        if attempts >= MAX_ATTEMPTS:
            cache.set(lock_key, now + LOCK_SECONDS, LOCK_SECONDS)
            cache.delete(fail_key)
            return Response({
                'error': 'You have reached the limit of 3 wrong attempts. Please try again after 1 minute.',
                'locked': True,
                'retry_after': LOCK_SECONDS,
            }, status=429)
        cache.set(fail_key, attempts, 15 * 60)
        return Response({
            'error': 'Invalid email or password',
            'attempts_left': MAX_ATTEMPTS - attempts,
        }, status=401)

    cache.delete(fail_key)
    update_last_login(None, user)
    refresh = RefreshToken.for_user(user)
    return Response({'access': str(refresh.access_token), 'refresh': str(refresh), 'is_admin': user.is_staff})