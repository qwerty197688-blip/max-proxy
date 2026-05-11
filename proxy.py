from flask import Flask, request, jsonify
import requests
import json

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
# 2. УНИВЕРСАЛЬНЫЙ ПРОКСИ ДЛЯ TELEGRAM (автоопределение метода, сырые фото)
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
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
