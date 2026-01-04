from flask import Flask, render_template, jsonify, request, send_file, session, redirect, url_for
from flask_cors import CORS
from functools import wraps
import json
import uuid
import base64
import qrcode
from io import BytesIO
import os
from datetime import datetime
import secrets
import string
import urllib.parse

app = Flask(__name__, template_folder='../templates')
app.secret_key = os.environ.get('SECRET_KEY', 'stepan-vpn-secret-key-2024')
CORS(app)

ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD', 'Artem1522@')

# Настройки для HAPP
HAPP_ICON_URL = "https://i.imgur.com/7QjKsCY.png"
TELEGRAM_BOT = "@stepavpnbot"
SUPPORT_URL = "https://t.me/stepavpnbot"

CONFIG_FILE = '/tmp/server_config.json'
CLIENTS_FILE = '/tmp/clients.json'

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('logged_in'):
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def generate_sub_code(length=7):
    chars = string.ascii_letters + string.digits
    return ''.join(secrets.choice(chars) for _ in range(length))

MASQUERADE_SITES = [
    {'name': 'Tele2', 'domain': 'msk.t2.ru'},
    {'name': 'VK', 'domain': 'eh44.vk.com'},
    {'name': 'Пятёрочка', 'domain': 'ads.x5.ru'},
    {'name': 'Яндекс Карты', 'domain': 'api-maps.yandex.ru'},
    {'name': 'Ozon', 'domain': 'io.ozone.ru'},
]

def load_server_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, 'r') as f:
            return json.load(f)
    return {
        'address': os.environ.get('VPN_SERVER_IP', 'YOUR_SERVER_IP'),
        'port': 443,
        'serverName': os.environ.get('VPN_SERVER_NAME', 'io.ozone.ru'),
        'publicKey': os.environ.get('VPN_PUBLIC_KEY', 'YOUR_PUBLIC_KEY'),
        'shortId': os.environ.get('VPN_SHORT_ID', 'YOUR_SHORT_ID')
    }

def save_server_config(config):
    with open(CONFIG_FILE, 'w') as f:
        json.dump(config, f, indent=2)

def load_clients():
    if os.path.exists(CLIENTS_FILE):
        with open(CLIENTS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return []

def save_clients(clients):
    with open(CLIENTS_FILE, 'w', encoding='utf-8') as f:
        json.dump(clients, f, indent=2, ensure_ascii=False)

def get_client_by_code(sub_code):
    clients = load_clients()
    return next((c for c in clients if c.get('sub_code') == sub_code), None)

def create_vless_link(client, server_config):
    """Создание VLESS ссылки — формат как у Phantom VPN"""
    address = server_config['address']
    port = server_config['port']
    uuid_str = client['uuid']
    sni = server_config['serverName']
    
    params = {
        'encryption': 'none',
        'security': 'reality',
        'sni': sni,
        'fp': 'chrome',
        'pbk': server_config['publicKey'],
        'sid': server_config['shortId'],
        'spx': '/',
        'type': 'tcp',
        'flow': 'xtls-rprx-vision'
    }
    
    param_str = '&'.join([f"{k}={v}" for k, v in params.items()])
    
    traffic_info = f"{client['traffic_limit']}GB" if client['traffic_limit'] > 0 else "∞"
    name = f"⚡STEPAN | {client['name']} | {traffic_info}"
    name_encoded = urllib.parse.quote(name)
    
    vless_link = f"vless://{uuid_str}@{address}:{port}?{param_str}#{name_encoded}"
    return vless_link

@app.route('/')
@login_required
def index():
    return render_template('index.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        password = request.form.get('password')
        if password == ADMIN_PASSWORD:
            session['logged_in'] = True
            return redirect(url_for('index'))
        return render_template('login.html', error=True)
    return render_template('login.html', error=False)

@app.route('/logout')
def logout():
    session.pop('logged_in', None)
    return redirect(url_for('login'))

@app.route('/s/<sub_code>')
def subscription_page(sub_code):
    client = get_client_by_code(sub_code)
    
    if not client:
        return "Подписка не найдена", 404
    
    server_config = load_server_config()
    vless_link = create_vless_link(client, server_config)
    
    return render_template('subscription.html', 
                         client=client, 
                         vless_link=vless_link,
                         sub_code=sub_code)

@app.route('/api/clients', methods=['GET'])
@login_required
def get_clients():
    clients = load_clients()
    return jsonify(clients)

@app.route('/api/clients', methods=['POST'])
@login_required
def add_client():
    data = request.json
    clients = load_clients()
    
    while True:
        sub_code = generate_sub_code()
        if not any(c.get('sub_code') == sub_code for c in clients):
            break
    
    new_id = max([c['id'] for c in clients], default=0) + 1
    
    new_client = {
        'id': new_id,
        'sub_code': sub_code,
        'uuid': str(uuid.uuid4()),
        'name': data.get('name', f'Client {new_id}'),
        'email': data.get('email', ''),
        'traffic_limit': data.get('traffic_limit', 0),
        'traffic_used': 0,
        'expiry_date': data.get('expiry_date', ''),
        'created_at': datetime.now().isoformat(),
        'enabled': True
    }
    
    clients.append(new_client)
    save_clients(clients)
    return jsonify(new_client)

@app.route('/api/clients/<int:client_id>', methods=['DELETE'])
@login_required
def delete_client(client_id):
    clients = load_clients()
    clients = [c for c in clients if c['id'] != client_id]
    save_clients(clients)
    return jsonify({'success': True})

@app.route('/api/clients/<int:client_id>/toggle', methods=['POST'])
@login_required
def toggle_client(client_id):
    clients = load_clients()
    for client in clients:
        if client['id'] == client_id:
            client['enabled'] = not client['enabled']
            break
    save_clients(clients)
    return jsonify({'success': True})

@app.route('/api/sub/<sub_code>')
def get_subscription(sub_code):
    """Генерация подписки для HAPP — простой base64 VLESS"""
    client = get_client_by_code(sub_code)
    
    if not client:
        return jsonify({'error': 'Client not found'}), 404
    
    server_config = load_server_config()
    vless_link = create_vless_link(client, server_config)
    
    # HAPP использует простой base64 encoded VLESS link
    subscription = base64.b64encode(vless_link.encode()).decode()
    
    return subscription, 200, {
        'Content-Type': 'text/plain; charset=utf-8',
        'Profile-Update-Interval': '1',
        'Subscription-Userinfo': f'upload=0; download={client["traffic_used"]}; total={client["traffic_limit"] * 1024 * 1024 * 1024 if client["traffic_limit"] > 0 else 0}; expire=0',
        'Profile-Title': 'STEPAN VPN',
        'Support-Url': SUPPORT_URL
    }

@app.route('/api/qr/<sub_code>')
def get_qrcode(sub_code):
    client = get_client_by_code(sub_code)
    
    if not client:
        return jsonify({'error': 'Client not found'}), 404
    
    server_config = load_server_config()
    vless_link = create_vless_link(client, server_config)
    
    qr = qrcode.QRCode(version=1, box_size=10, border=4)
    qr.add_data(vless_link)
    qr.make(fit=True)
    
    img = qr.make_image(fill_color="#a855f7", back_color="#0a0a0a")
    
    buf = BytesIO()
    img.save(buf, format='PNG')
    buf.seek(0)
    
    return send_file(buf, mimetype='image/png')

@app.route('/api/vless/<sub_code>')
def get_vless_link(sub_code):
    client = get_client_by_code(sub_code)
    
    if not client:
        return jsonify({'error': 'Client not found'}), 404
    
    server_config = load_server_config()
    vless_link = create_vless_link(client, server_config)
    
    return vless_link, 200, {'Content-Type': 'text/plain'}

@app.route('/api/icon.png')
def get_icon():
    """Иконка STEPAN VPN для HAPP"""
    from PIL import Image, ImageDraw
    
    size = 512
    img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    
    # Фиолетовый фон со скруглёнными углами
    radius = 100
    draw.rounded_rectangle([0, 0, size-1, size-1], radius=radius, fill=(168, 85, 247, 255))
    
    # Молния
    bolt_color = (255, 255, 255, 255)
    bolt_points = [
        (280, 80), (180, 240), (240, 240), (160, 432),
        (320, 260), (260, 260), (340, 80),
    ]
    draw.polygon(bolt_points, fill=bolt_color)
    
    buf = BytesIO()
    img.save(buf, format='PNG')
    buf.seek(0)
    
    return send_file(buf, mimetype='image/png')

@app.route('/api/masquerade-sites')
@login_required
def get_masquerade_sites():
    return jsonify(MASQUERADE_SITES)

@app.route('/api/server/config', methods=['GET'])
@login_required
def get_server_config():
    return jsonify(load_server_config())

@app.route('/api/server/config', methods=['POST'])
@login_required
def update_server_config():
    data = request.json
    config = {
        'address': data.get('address', ''),
        'port': data.get('port', 443),
        'serverName': data.get('serverName', 'io.ozone.ru'),
        'publicKey': data.get('publicKey', ''),
        'shortId': data.get('shortId', '')
    }
    save_server_config(config)
    return jsonify({'success': True})

app = app
