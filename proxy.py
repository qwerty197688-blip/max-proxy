from flask import Flask, request, jsonify
import requests

app = Flask(__name__)

MAX_TOKEN = "f9LHodD0cOL6sWUqALeE0TV5VXVb6YSUZoNnbUt0sBRwEbz-36An-XyiP6rC959ZSEpEY7tpmjqrDZBe6ew8"
MAX_API_URL = "https://platform-api.max.ru/messages"

REES46_SHOP_ID = "094c1d1542d01e13bf851001c5f814"
REES46_SHOP_SECRET = "79dbfb33e1534843d0a3b0b3730b55a1"
REES46_PROFILE_URL = "https://api.rees46.ru/profile"
CRM_STATUS_URL_TEMPLATE = "https://crm.florcat.ru/ajax/getStatusLinks.php?order_id={order_id}"

# 1. Прокси для MAX — принимает запросы от ChatApp и перенаправляет в MAX API
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

# 2. Получение активных заказов (только статус 0, последние три)
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

# 3. Очистка user_id от префикса private-
@app.route('/clean-user-id', methods=['POST'])
def clean_user_id():
    data = request.get_json()
    raw_id = data.get('user_id', '')
    clean = raw_id.replace('private-', '').replace('group-', '')
    return jsonify({'user_id': clean})

# 4. Health-check для UptimeRobot
@app.route('/health', methods=['GET'])
def health():
    return jsonify({'status': 'ok'})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
