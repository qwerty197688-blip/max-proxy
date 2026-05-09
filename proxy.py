from flask import Flask, request, jsonify
import requests

app = Flask(__name__)

# === КОНФИГУРАЦИЯ ===
MAX_TOKEN = "f9LHodD0cOL6sWUqALeE0TV5VXVb6YSUZoNnbUt0sBRwEbz-36An-XyiP6rC959ZSEpEY7tpmjqrDZBe6ew8"
MAX_API_URL = "https://platform-api.max.ru/messages"

# Токен Telegram-бота (указан второй токен, при необходимости замените)
TG_BOT_TOKEN = "5256656259:AAG1kdCp0eqps84AZLsD1PcrzxmXaDRMg04"
TG_API_URL = f"https://api.telegram.org/bot{TG_BOT_TOKEN}"

REES46_SHOP_ID = "094c1d1542d01e13bf851001c5f814"
REES46_SHOP_SECRET = "79dbfb33e1534843d0a3b0b3730b55a1"
REES46_PROFILE_URL = "https://api.rees46.ru/profile"
CRM_STATUS_URL_TEMPLATE = "https://crm.florcat.ru/ajax/getStatusLinks.php?order_id={order_id}"

# ------------------------------------------------------------
# 1. ПРОКСИ ДЛЯ MAX — принимает запросы от ChatApp и отправляет в MAX API
# ------------------------------------------------------------
@app.route('/', methods=['POST'])
def proxy_to_max():
    body = request.get_json()
    user_id = body.get('user_id')
    if not user_id:
        return jsonify({'status': 'error', 'message': 'user_id is required'}), 400

    # Убираем префикс private- (и group- на всякий случай)
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
# 2. ПРОКСИ ДЛЯ TELEGRAM (новый маршрут)
# ------------------------------------------------------------
@app.route('/send-to-telegram', methods=['POST'])
def proxy_to_telegram():
    data = request.get_json()
    method = data.get('method')
    payload = data.get('payload', {})

    if not method:
        return jsonify({'status': 'error', 'message': 'method is required'}), 400

    url = f"{TG_API_URL}/{method}"
    resp = requests.post(url, json=payload)
    return jsonify(resp.json()), resp.status_code

# ------------------------------------------------------------
# 3. АКТИВНЫЕ ЗАКАЗЫ (статус = 0) — для кнопки «Отследить заказ»
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
        # Получаем статусную страницу из CRM
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
# 4. ИСТОРИЯ ЗАКАЗОВ (любой статус, последние 3) — для «История заказов»
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
# 5. ОЧИСТКА USER_ID — убираем префикс private- для передачи в REES46
# ------------------------------------------------------------
@app.route('/clean-user-id', methods=['POST'])
def clean_user_id():
    data = request.get_json()
    raw_id = data.get('user_id', '')
    clean = raw_id.replace('private-', '').replace('group-', '')
    return jsonify({'user_id': clean})

# ------------------------------------------------------------
# 6. HEALTH‑CHECK — для UptimeRobot, чтобы сервер не «засыпал»
# ------------------------------------------------------------
@app.route('/health', methods=['GET'])
def health():
    return jsonify({'status': 'ok'})

# ------------------------------------------------------------
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
