import logging
import requests
from django.conf import settings
from django.core.cache import cache
from django.db.models import Avg, Count
from rest_framework.decorators import api_view, permission_classes, authentication_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework_simplejwt.authentication import JWTAuthentication
from orders.models import Order
from shop.models import Fruit
from .knowledge import APP_GUIDE, RULES, OFFLINE_FAQ, OFFLINE_DEFAULT

logger = logging.getLogger(__name__)

MAX_MESSAGE = 300     # characters per message
MAX_HISTORY = 10      # earlier messages sent along
PER_MINUTE = 8        # messages allowed per minute for one person
GEMINI_URL = 'https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent'
ORDER_WORDS = ('order', 'track', 'deliver', 'status', 'ship', 'receipt', 'cancel', 'parcel')


def get_user(request):
    """Logged-in user from the token, or None. A bad token never breaks the chat."""
    try:
        result = JWTAuthentication().authenticate(request)
        return result[0] if result else None
    except Exception:
        return None


def client_id(request, user):
    if user:
        return 'u' + str(user.id)
    ip = request.META.get('HTTP_X_FORWARDED_FOR', request.META.get('REMOTE_ADDR', 'unknown'))
    return 'ip' + ip.split(',')[0].strip()


def too_many(identity):
    key = 'chat_rate:' + identity
    if cache.add(key, 1, 60):
        return False
    try:
        return cache.incr(key) > PER_MINUTE
    except ValueError:
        cache.set(key, 1, 60)
        return False


def fruit_lines():
    fruits = Fruit.objects.annotate(avg=Avg('reviews__rating'), n=Count('reviews')).order_by('name')[:80]
    lines = []
    for f in fruits:
        stock = float(f.stock_kg)
        if stock <= 0:
            stock_text = 'OUT OF STOCK'
        elif stock <= 10:
            stock_text = 'low stock, only ' + str(stock) + ' kg left'
        else:
            stock_text = 'in stock'
        if f.discount_percent > 0:
            price = 'Rs.' + str(f.final_price) + ' per kg after ' + str(f.discount_percent) + '% discount (old price Rs.' + str(f.price_per_kg) + ')'
        else:
            price = 'Rs.' + str(f.price_per_kg) + ' per kg'
        rating = ', rated ' + str(round(f.avg, 1)) + '/5 by ' + str(f.n) + ' customers' if f.n else ''
        about = f.description.strip().replace('\n', ' ')[:100]
        lines.append('- ' + f.name + ': ' + price + ', ' + stock_text + rating + '. About: ' + about)
    return '\n'.join(lines) or '- No fruits are listed right now.'


def order_lines(user):
    lines = []
    for o in Order.objects.filter(user=user).order_by('-created')[:5]:
        items = ', '.join(i.fruit.name + ' ' + str(float(i.quantity_kg)) + ' kg' for i in o.items.select_related('fruit'))
        lines.append('- Order #' + str(o.id) + ' placed on ' + o.created.strftime('%d %b %Y') +
                     ', status ' + o.status + ', total Rs.' + str(o.total) + ', items: ' + items)
    return '\n'.join(lines) or '- This customer has no orders yet.'


def build_system_text(user, message):
    parts = [RULES, 'WEBSITE GUIDE\n' + APP_GUIDE, 'FRUITS IN THE STORE RIGHT NOW (live data)\n' + fruit_lines()]
    wants_orders = any(w in message.lower() for w in ORDER_WORDS)
    if user and wants_orders:
        parts.append("THIS LOGGED-IN CUSTOMER'S RECENT ORDERS (discuss only these)\n" + order_lines(user))
    elif user:
        parts.append('The customer is logged in. If they ask about their orders, answer from their order list on the next message.')
    else:
        parts.append('The visitor is NOT logged in. If they ask about their orders, tell them to login first.')
    return '\n\n'.join(parts)


def build_contents(raw_history, message):
    items = []
    history = raw_history[-MAX_HISTORY:] if isinstance(raw_history, list) else []
    for m in history:
        if not isinstance(m, dict):
            continue
        text = str(m.get('text', '')).strip()[:500]
        if text:
            items.append({'role': 'user' if m.get('role') == 'user' else 'model', 'text': text})
    items.append({'role': 'user', 'text': message})

    while items and items[0]['role'] != 'user':   # a chat must start with the user
        items.pop(0)

    merged = []                                    # join messages with the same role
    for it in items:
        if merged and merged[-1]['role'] == it['role']:
            merged[-1]['text'] += '\n' + it['text']
        else:
            merged.append(dict(it))
    return [{'role': m['role'], 'parts': [{'text': m['text']}]} for m in merged]


def ask_gemini(system_text, contents):
    """Returns the reply text, or None if Gemini could not answer."""
    if not settings.GEMINI_API_KEY:
        logger.warning('GEMINI_API_KEY is missing. Check backend/.env')
        return None
    try:
        r = requests.post(
            GEMINI_URL.format(model=settings.GEMINI_MODEL),
            headers={'x-goog-api-key': settings.GEMINI_API_KEY, 'Content-Type': 'application/json'},
            json={
                'system_instruction': {'parts': [{'text': system_text}]},
                'contents': contents,
                'generationConfig': {'temperature': 0.4, 'maxOutputTokens': 1024},
            },
            timeout=25,
        )
        if r.status_code != 200:
            logger.warning('Gemini error %s: %s', r.status_code, r.text[:300])
            return None
        parts = r.json()['candidates'][0]['content']['parts']
        text = ''.join(p.get('text', '') for p in parts).strip()
        return text or None
    except Exception as e:
        logger.warning('Gemini request failed: %s', e)
        return None


def offline_answer(message):
    m = message.lower()
    for words, answer in OFFLINE_FAQ:
        if any(w in m for w in words):
            return answer
    return OFFLINE_DEFAULT


@api_view(['POST'])
@authentication_classes([])
@permission_classes([AllowAny])
def chat(request):
    message = str(request.data.get('message', '')).strip()
    if not message:
        return Response({'error': 'Please type a message'}, status=400)
    if len(message) > MAX_MESSAGE:
        return Response({'error': 'Message is too long (maximum ' + str(MAX_MESSAGE) + ' characters)'}, status=400)

    user = get_user(request)
    if too_many(client_id(request, user)):
        return Response({'error': 'You are sending messages too fast. Please wait a minute and try again.'}, status=429)

    reply = ask_gemini(build_system_text(user, message), build_contents(request.data.get('history'), message))
    if reply is None:
        return Response({'reply': offline_answer(message), 'fallback': True})
    return Response({'reply': reply, 'fallback': False})