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
                image_resp = requests.get(photo_url, stream=True)
                image_resp.raise_for_status()
                files = {'photo': ('image.png', image_resp.raw, 'image/png')}
                data_payload = {
                    'chat_id': (None, chat_id),
                    'caption': (None, caption or ''),
                    'parse_mode': (None, parse_mode),
                }
                if reply_markup:
                    data_payload['reply_markup'] = (None, json.dumps(reply_markup))

                resp = requests.post(f"{TG_API_URL}/sendPhoto", files=files, data=data_payload)
            except Exception as e:
                return jsonify({'status': 'error', 'message': f'Failed to download photo: {e}'}), 500
        else:
            payload['photo'] = photo
            payload['caption'] = caption or ''
            resp = requests.post(f"{TG_API_URL}/sendPhoto", json=payload)

    else:
        return jsonify({'status': 'error', 'message': f'Unsupported method: {method}'}), 400

    return jsonify(resp.json()), resp.status_code
