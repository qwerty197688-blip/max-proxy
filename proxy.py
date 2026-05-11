from flask import Flask, request, jsonify
import requests
import json
import re

app = Flask(__name__)

# === КОНФИГУРАЦИЯ ===
MAX_TOKEN = "f9LHodD0cOL6sWUqALeE0TV5VXVb6YSUZoNnbUt0sBRwEbz-36An-XyiP6rC959ZSEpEY7tpmjqrDZBe6ew8"
MAX_API_URL = "https://platform-api.max.ru/messages"

# Токен Telegram-бота (FlorcatBot)
TG_BOT_TOKEN = "5256656259:AAG1kdCp0eqps84AZLsD1PcrzxmXaDRMg04"
TG_API_URL = f"https://api.telegram.org/bot{TG_BOT_TOKEN}"

REES46_SHOP_ID = "094c1d1542d01e13bf851001c5f814"
REES46_SHOP_SECRET = "79dbfb33e1534843d0a3b0b3730b55a1"
REES46_PROFILE_URL = "https://api.rees46.ru/profile"
CRM_STATUS_URL_TEMPLATE = "https://crm.florcat.ru/ajax/getStatusLinks.php?order_id={order_id}"

# Токен приложения Битрикс24 и CLIENT_ID бота-фильтра
BITRIX_APP_TOKEN = "sza7gi6khrvx18cr0eipcb0z6puepwob"
BITRIX_CLIENT_ID = "q4s0wy624a1p99qwlta98lu3ih0fjgq7"
BITRIX_REST_URL = "https://crm.florcat.ru/rest"

# ------------------------------------------------------------
# 1. ПРОКСИ ДЛЯ MAX
# ------------------------------------------------------------
@app.route('/', methods=['POST'])
def proxy_to_max():
    body = request.get_json()
    user_id = body.get('user_id')
    if not user_id:
        return jsonify({'status': 'error', 'message': 'user_id is required'}), 400

    if user_id.startswith('private-') or user_id.startswith('group-'):
        user_id = user_id.split('-', 1)[1]

    headers = {
        "Authorization": MAX_TOKEN,
        "Content-Type": "application/json"
    }
    payload = body.copy()
    payload['user_id'] = user_id
    resp = requests.post(MAX_API_URL, headers=headers, json=payload)
    return jsonify(resp.json()), resp.status_code

# ------------------------------------------------------------
# 2. УНИВЕРСАЛЬНЫЙ ПРОКСИ ДЛЯ TELEGRAM
# ------------------------------------------------------------
@app.route('/telegram', methods=['POST'])
def proxy_telegram_auto():
    data = request.get_json()
    method = data.get('method')
    photo_url = data.get('photo_url')
    photo = data.get('photo')
    text = data.get('text')
    caption = data.get('caption')
    chat_id = data.get('chat_id')
    reply_markup = data.get('reply_markup')
    parse_mode = data.get('parse_mode', 'Markdown')

    if not chat_id:
        return jsonify({'status': 'error', 'message': 'chat_id is required'}), 400

    if not method:
        if photo_url or photo:
            method = 'sendPhoto'
        else:
            method = 'sendMessage'

    payload = {
        'chat_id': chat_id,
        'parse_mode': parse_mode,
    }
    if reply_markup:
        payload['reply_markup'] = json.dumps(reply_markup)

    if method == 'sendMessage':
        payload['text'] = text or caption or ''
        resp = requests.post(f"{TG_API_URL}/sendMessage", json=payload)

    elif method == 'sendPhoto':
        if photo_url:
            try:
                image_resp = requests.get(photo_url)
                image_resp.raise_for_status()
                content_type = image_resp.headers.get('Content-Type', 'application/octet-stream')
                files = {'photo': ('image.png', image_resp.content, content_type)}
                data_payload = {
                    'chat_id': (None, chat_id),
                    'caption': (None, caption or ''),
                    'parse_mode': (None, parse_mode),
                }
                if reply_markup:
                    data_payload['reply_markup'] = (None, json.dumps(reply_markup))
                resp = requests.post(f"{TG_API_URL}/sendPhoto", files=files, data=data_payload)
            except Exception as e:
                return jsonify({'status': 'error', 'message': f'Failed to download or send photo: {e}'}), 500
        else:
            payload['photo'] = photo
            payload['caption'] = caption or ''
            resp = requests.post(f"{TG_API_URL}/sendPhoto", json=payload)

    else:
        return jsonify({'status': 'error', 'message': f'Unsupported method: {method}'}), 400

    return jsonify(resp.json()), resp.status_code

# ------------------------------------------------------------
# 3. АКТИВНЫЕ ЗАКАЗЫ (статус = 0)
# ------------------------------------------------------------
@app.route('/get-orders', methods=['POST'])
def get_orders():
    data = request.get_json()
    phone = data.get('phone')
    if not phone:
        return jsonify({'error': 'phone is required'}), 400

    params = {
        'shop_id': REES46_SHOP_ID,
        'shop_secret': REES46_SHOP_SECRET,
        'phone': phone
    }
    resp = requests.get(REES46_PROFILE_URL, params=params)
    if resp.status_code != 200:
        return jsonify({'error': 'REES46 API error'}), 500

    orders = resp.json().get('orders', [])
    active_orders = [o for o in orders if o.get('status') == 0]
    last_orders = active_orders[-3:] if len(active_orders) >= 3 else active_orders

    result = {}
    for i, order in enumerate(last_orders):
        idx = i + 1
        order_id = order.get('id')
        result[f'order{idx}_id'] = order_id
        result[f'order{idx}_status'] = order.get('status')
        result[f'order{idx}_value'] = order.get('value')
        try:
            crm_resp = requests.get(CRM_STATUS_URL_TEMPLATE.format(order_id=order_id))
            if crm_resp.status_code == 200:
                result[f'status_url_{idx}'] = crm_resp.text.strip()
            else:
                result[f'status_url_{idx}'] = ''
        except Exception:
            result[f'status_url_{idx}'] = ''

    return jsonify(result)

# ------------------------------------------------------------
# 4. ИСТОРИЯ ЗАКАЗОВ (любой статус, последние 3)
# ------------------------------------------------------------
@app.route('/get-order-history', methods=['POST'])
def get_order_history():
    data = request.get_json()
    phone = data.get('phone')
    if not phone:
        return jsonify({'error': 'phone is required'}), 400

    params = {
        'shop_id': REES46_SHOP_ID,
        'shop_secret': REES46_SHOP_SECRET,
        'phone': phone
    }
    resp = requests.get(REES46_PROFILE_URL, params=params)
    if resp.status_code != 200:
        return jsonify({'error': 'REES46 API error'}), 500

    orders = resp.json().get('orders', [])
    last_orders = orders[-3:] if len(orders) >= 3 else orders

    result = {}
    for i, order in enumerate(last_orders):
        idx = i + 1
        result[f'hist_order{idx}_id'] = order.get('id')
        result[f'hist_order{idx}_status'] = order.get('status')
        result[f'hist_order{idx}_value'] = order.get('value')

    return jsonify(result)

# ------------------------------------------------------------
# 5. ОЧИСТКА USER_ID
# ------------------------------------------------------------
@app.route('/clean-user-id', methods=['POST'])
def clean_user_id():
    data = request.get_json()
    raw_id = data.get('user_id', '')
    clean = raw_id.replace('private-', '').replace('group-', '')
    return jsonify({'user_id': clean})

# ------------------------------------------------------------
# 6. ПАРСИНГ DEEP LINK (извлечение start-параметра)
# ------------------------------------------------------------
@app.route('/parse-start', methods=['POST'])
def parse_start():
    data = request.get_json()
    text = data.get('message', '')
    source = 'organic'
    if text.startswith('/start '):
        source = text[7:].strip() or 'organic'
    return jsonify({'lead_source': source})

# ------------------------------------------------------------
# 7. HEALTH‑CHECK
# ------------------------------------------------------------
@app.route('/health', methods=['GET'])
def health():
    return jsonify({'status': 'ok'})

# ------------------------------------------------------------
# 8. ФИЛЬТР СООБЩЕНИЙ ДЛЯ БИТРИКС24 (БОТ-ФИЛЬТР) – ФИНАЛЬНАЯ ВЕРСИЯ
# ------------------------------------------------------------
def call_bitrix(method, params={}):
    """Вызов REST API Битрикс24 с токеном приложения и CLIENT_ID бота"""
    url = f"{BITRIX_REST_URL}/{method}?auth={BITRIX_APP_TOKEN}"
    if "CLIENT_ID" not in params:
        params["CLIENT_ID"] = BITRIX_CLIENT_ID
    resp = requests.post(url, json=params)
    return resp.json()

def normalize_phone(phone):
    if not phone:
        return ''
    digits = re.sub(r'[^\d]', '', phone)
    if len(digits) == 11 and digits.startswith(('7', '8')):
        return '7' + digits[1:]
    elif len(digits) == 10:
        return '7' + digits
    return digits

def get_contact_by_phone(phone):
    clean = normalize_phone(phone)
    if not clean:
        return None
    search_tail = clean[-10:]
    result = call_bitrix("crm.contact.list", {
        "filter": {"%=PHONE": search_tail},
        "select": ["ID"]
    })
    contacts = result.get("result", [])
    return contacts[0]["ID"] if contacts else None

def has_active_deals_or_leads(contact_id):
    deals = call_bitrix("crm.deal.list", {
        "filter": {"CONTACT_ID": contact_id, "!STAGE_SEMANTIC_ID": "F"},
        "select": ["ID"]
    })
    if deals.get("result"):
        return True

    leads = call_bitrix("crm.lead.list", {
        "filter": {"CONTACT_ID": contact_id, "!STATUS_SEMANTIC_ID": "F"},
        "select": ["ID"]
    })
    return len(leads.get("result", [])) > 0

def finish_session(chat_id):
    return call_bitrix("imopenlines.bot.session.finish", {
        "CHAT_ID": chat_id,
        "BOT_ID": BITRIX_CLIENT_ID
    })

def transfer_to_operator(chat_id):
    return call_bitrix("imopenlines.bot.session.operator", {
        "CHAT_ID": chat_id,
        "BOT_ID": BITRIX_CLIENT_ID
    })

def create_lead_and_attach(contact_id, phone, source="Telegram"):
    lead = call_bitrix("crm.lead.add", {
        "fields": {
            "TITLE": f"Обращение из {source}",
            "CONTACT_ID": contact_id,
            "SOURCE_ID": source,
            "COMMENTS": f"Телефон: {phone}"
        }
    })
    return lead.get("result")

def is_technical_message(text):
    if not text:
        return False
    tech_phrases = [
        "/start",
        "📱 Меню",
        "📍 Отследить заказ",
        "💐 Каталог",
        "👤 Личный кабинет",
        "❓ Соединить с оператором",
        "🔙 Назад",
        "💰 Баланс бонусов",
        "📋 История заказов"
    ]
    text_clean = text.strip()
    for phrase in tech_phrases:
        if text_clean == phrase:
            return True
    return False

@app.route('/bitrix-filter', methods=['POST'])
def bitrix_filter():
    # Сохраняем сырое тело для диагностики
    raw_body = request.get_data(as_text=True)
    with open('/tmp/bitrix_body.log', 'a') as f:
        f.write(f"=== {request.content_type} ===\n{raw_body}\n\n")

    # Пробуем JSON
    data = request.get_json(silent=True)
    if data is None:
        data = request.form.to_dict()

    # Логируем в консоль
    app.logger.info("=== BITRIX FILTER RECEIVED ===")
    app.logger.info("Content-Type: %s", request.content_type)
    app.logger.info("Data: %s", json.dumps(data, ensure_ascii=False))

    # Если данные не получены, возвращаем ошибку с превью сырого тела
    if not data:
        return jsonify({
            "status": "error",
            "message": "No parseable data",
            "content_type": request.content_type,
            "raw_preview": raw_body[:200]
        }), 400

    # Извлекаем текст сообщения
    text = ''
    if 'data[message][text]' in data:
        text = data['data[message][text]']
    elif isinstance(data, dict):
        message = data.get('message', {})
        if isinstance(message, dict):
            text = message.get('text', '')
        else:
            text = data.get('text', '')

    # Извлекаем chat_id (внутренний ID открытой линии, если есть)
    chat_id = ''
    if isinstance(data, dict) and 'chat_id' in data:
        chat_id = data['chat_id']
    elif 'data[chat][id]' in data:
        chat_id = data['data[chat][id]']
    elif isinstance(data, dict) and 'chat' in data and isinstance(data['chat'], dict):
        chat_id = data['chat'].get('id', '')
    elif isinstance(data, dict) and 'data' in data and isinstance(data['data'], dict):
        chat = data['data'].get('chat', {})
        if isinstance(chat, dict):
            chat_id = chat.get('id', '')

    # Извлекаем user_id (альтернативный идентификатор для ChatApp)
    user_id = ''
    if isinstance(data, dict):
        user_id = data.get('user_id', data.get('id_chat', ''))

    # Извлекаем телефон (если передан)
    phone = ''
    if 'data[phone]' in data:
        phone = data['data[phone]']
    elif isinstance(data, dict):
        phone = data.get('phone', data.get('client', {}).get('phone', ''))

    # Если нет ни chat_id, ни user_id – возвращаем ошибку
    if not chat_id and not user_id:
        return jsonify({"status": "error", "message": "chat_id or user_id missing"}), 400

    clean_phone = normalize_phone(phone)
    contact_id = get_contact_by_phone(clean_phone) if clean_phone else None

    active = False
    if contact_id:
        active = has_active_deals_or_leads(contact_id)

    is_tech = is_technical_message(text)

    # --- Логика для вебхука Битрикс24 (управляем сессией) ---
    if chat_id:
        if contact_id and active:
            transfer_to_operator(chat_id)
            return jsonify({"status": "ok", "action": "open", "reason": "active_deals"})

        if contact_id and not active:
            if is_tech:
                finish_session(chat_id)
                return jsonify({"status": "ok", "action": "finish", "reason": "tech_no_active"})
            else:
                create_lead_and_attach(contact_id, clean_phone)
                transfer_to_operator(chat_id)
                return jsonify({"status": "ok", "action": "open", "lead_created": True})

        # Нет контакта
        if is_tech:
            finish_session(chat_id)
            return jsonify({"status": "ok", "action": "finish", "reason": "tech_no_contact"})
        else:
            transfer_to_operator(chat_id)
            return jsonify({"status": "ok", "action": "open", "reason": "no_contact"})

    # --- Логика для вызова из ChatApp (только анализируем) ---
    if is_tech:
        return jsonify({"status": "ok", "action": "finish", "reason": "tech"})
    else:
        return jsonify({"status": "ok", "action": "open", "reason": "normal"})

# ------------------------------------------------------------
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
