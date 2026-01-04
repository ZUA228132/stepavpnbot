from flask import Flask, render_template, jsonify, request, send_file, session, redirect, url_for
from flask_cors import CORS
from functools import wraps
import json
import uuid
import base64
import qrcode
from io import BytesIO
import subprocess
import os
from datetime import datetime
import paramiko
import secrets
import string
import urllib.parse

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'stepan-vpn-secret-key-2024')
CORS(app)

# Пароль для админки
ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD', 'Artem1522@')

# Настройки для HAPP
# Иконка — используем публичный URL с молнией/щитом
HAPP_ICON_URL = "https://raw.githubusercontent.com/nicepkg/vscode-iconify/main/icons/noto/high-voltage.svg"
TELEGRAM_BOT = "@stepavpnbot"
SUPPORT_URL = "https://t.me/stepavpnbot"

CONFIG_FILE = 'server_config.json'
CLIENTS_FILE = 'clients.json'

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('logged_in'):
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def generate_sub_code(length=7):
    """Генерация случайного кода для подписки (a-z, A-Z, 0-9)"""
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

def load_clients():
    if os.path.exists(CLIENTS_FILE):
        with open(CLIENTS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return []

def save_clients(clients):
    with open(CLIENTS_FILE, 'w', encoding='utf-8') as f:
        json.dump(clients, f, indent=2, ensure_ascii=False)

def get_client_by_code(sub_code):
    """Найти клиента по коду подписки"""
    clients = load_clients()
    return next((c for c in clients if c.get('sub_code') == sub_code), None)

def generate_keys():
    """Генерация ключей Reality"""
    try:
        result = subprocess.run(['xray', 'x25519'], capture_output=True, text=True)
        lines = result.stdout.strip().split('\n')
        private_key = lines[0].split(': ')[1]
        public_key = lines[1].split(': ')[1]
        return private_key, public_key
    except:
        return "fake_private_key", "fake_public_key"

def generate_short_id():
    """Генерация shortId"""
    return os.urandom(8).hex()

def create_vless_link(client, server_config):
    """Создание VLESS ссылки для импорта с иконкой"""
    address = server_config['address']
    port = server_config['port']
    uuid_str = client['uuid']
    
    params = {
        'encryption': 'none',
        'security': 'reality',
        'sni': server_config['serverName'],
        'fp': 'chrome',
        'pbk': server_config['publicKey'],
        'sid': server_config['shortId'],
        'type': 'tcp',
        'flow': 'xtls-rprx-vision'
    }
    
    param_str = '&'.join([f"{k}={v}" for k, v in params.items()])
    
    # Название с информацией о подписке
    traffic_info = f"{client['traffic_limit']}GB" if client['traffic_limit'] > 0 else "∞"
    name = f"⚡ STEPAN VPN | {client['name']} | {traffic_info}"
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
    """Страница подписки по коду"""
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
    
    # Генерируем уникальный код подписки
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
    """Генерация подписки для HAPP по коду — расширенный формат"""
    client = get_client_by_code(sub_code)
    
    if not client:
        return jsonify({'error': 'Client not found'}), 404
    
    server_config = load_server_config()
    vless_link = create_vless_link(client, server_config)
    
    # Расширенный формат подписки для HAPP с метаданными
    traffic_info = f"{client['traffic_limit']}GB" if client['traffic_limit'] > 0 else "∞"
    days_left = ""
    if client.get('expiry_date'):
        try:
            from datetime import datetime
            exp = datetime.fromisoformat(client['expiry_date'])
            days = (exp - datetime.now()).days
            days_left = f"Дней осталось: {days}" if days > 0 else "Истекла"
        except:
            days_left = ""
    
    # Формируем описание
    description_lines = [
        f"🔗 Подписка: {sub_code}",
        f"📊 Статус: {'✅ Active' if client['enabled'] else '❌ Disabled'}",
    ]
    if days_left:
        description_lines.append(f"📅 {days_left}")
    description_lines.append(f"🛡️ Reality Protocol")
    
    # Динамический URL иконки
    icon_url = f"{request.host_url}api/icon.png"
    
    subscription_info = {
        "name": "STEPAN VPN",
        "icon": icon_url,
        "description": "\n".join(description_lines),
        "support": SUPPORT_URL,
        "servers": [vless_link]
    }
    
    # HAPP принимает base64 encoded JSON или просто base64 VLESS
    # Пробуем JSON формат
    sub_json = json.dumps(subscription_info, ensure_ascii=False)
    subscription = base64.b64encode(sub_json.encode()).decode()
    
    return subscription, 200, {'Content-Type': 'text/plain'}

@app.route('/api/qr/<sub_code>')
def get_qrcode(sub_code):
    """Генерация QR кода по коду подписки"""
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
    """Получить готовую VLESS ссылку"""
    client = get_client_by_code(sub_code)
    
    if not client:
        return jsonify({'error': 'Client not found'}), 404
    
    server_config = load_server_config()
    vless_link = create_vless_link(client, server_config)
    
    return vless_link, 200, {'Content-Type': 'text/plain'}

@app.route('/api/icon.png')
def get_icon():
    """Иконка STEPAN VPN для HAPP — молния на фиолетовом фоне"""
    from PIL import Image, ImageDraw
    
    # Создаём 512x512 иконку
    size = 512
    img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    
    # Фиолетовый градиентный фон (упрощённо — сплошной)
    # Рисуем скруглённый квадрат
    radius = 100
    draw.rounded_rectangle([0, 0, size-1, size-1], radius=radius, fill=(168, 85, 247, 255))
    
    # Рисуем молнию (⚡) — упрощённая форма
    bolt_color = (255, 255, 255, 255)
    # Координаты молнии
    bolt_points = [
        (280, 80),   # верх
        (180, 240),  # левый угол верхней части
        (240, 240),  # внутренний угол
        (160, 432),  # низ
        (320, 260),  # правый угол нижней части
        (260, 260),  # внутренний угол
        (340, 80),   # обратно к верху
    ]
    draw.polygon(bolt_points, fill=bolt_color)
    
    buf = BytesIO()
    img.save(buf, format='PNG')
    buf.seek(0)
    
    return send_file(buf, mimetype='image/png')

@app.route('/api/config/generate', methods=['POST'])
@login_required
def generate_config():
    """Генерация конфигурации сервера"""
    private_key, public_key = generate_keys()
    short_id = generate_short_id()
    
    config = {
        'privateKey': private_key,
        'publicKey': public_key,
        'shortId': short_id
    }
    
    return jsonify(config)

@app.route('/api/masquerade-sites')
@login_required
def get_masquerade_sites():
    """Получить список сайтов для маскировки"""
    return jsonify(MASQUERADE_SITES)

@app.route('/api/server/setup', methods=['POST'])
@login_required
def setup_server():
    """Автоматическая настройка сервера через SSH"""
    data = request.json
    ip = data.get('ip')
    port = data.get('port', 22)
    user = data.get('user', 'root')
    password = data.get('password')
    masquerade = data.get('masquerade', 'io.ozone.ru')
    
    try:
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect(ip, port=port, username=user, password=password, timeout=30)
        
        commands = [
            'apt update -y',
            'apt install -y curl wget',
            'bash -c "$(curl -L https://github.com/XTLS/Xray-install/raw/main/install-release.sh)" @ install',
        ]
        
        for cmd in commands:
            stdin, stdout, stderr = ssh.exec_command(cmd, timeout=300)
            stdout.channel.recv_exit_status()
        
        stdin, stdout, stderr = ssh.exec_command('xray x25519')
        keys_output = stdout.read().decode()
        
        private_key = ''
        public_key = ''
        for line in keys_output.split('\n'):
            if 'Private key' in line:
                private_key = line.split(': ')[1].strip()
            elif 'Public key' in line:
                public_key = line.split(': ')[1].strip()
        
        stdin, stdout, stderr = ssh.exec_command('openssl rand -hex 8')
        short_id = stdout.read().decode().strip()
        
        xray_config = {
            "log": {"loglevel": "warning"},
            "inbounds": [{
                "port": 443,
                "protocol": "vless",
                "settings": {
                    "clients": [],
                    "decryption": "none"
                },
                "streamSettings": {
                    "network": "tcp",
                    "security": "reality",
                    "realitySettings": {
                        "dest": f"{masquerade}:443",
                        "serverNames": [masquerade],
                        "privateKey": private_key,
                        "shortIds": [short_id]
                    }
                }
            }],
            "outbounds": [{
                "protocol": "freedom",
                "tag": "direct"
            }]
        }
        
        config_json = json.dumps(xray_config, indent=2)
        ssh.exec_command(f"echo '{config_json}' > /usr/local/etc/xray/config.json")
        ssh.exec_command('ufw allow 443/tcp 2>/dev/null || true')
        ssh.exec_command('systemctl enable xray')
        ssh.exec_command('systemctl restart xray')
        
        server_config = {
            'address': ip,
            'port': 443,
            'serverName': masquerade,
            'publicKey': public_key,
            'shortId': short_id,
            'privateKey': private_key
        }
        
        with open(CONFIG_FILE, 'w') as f:
            json.dump(server_config, f, indent=2)
        
        ssh.close()
        
        return jsonify({
            'success': True,
            'publicKey': public_key,
            'shortId': short_id,
            'masquerade': masquerade,
            'message': 'Сервер успешно настроен!'
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
