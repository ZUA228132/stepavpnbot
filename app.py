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
import time

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'stepan-vpn-secret-key-2024')
CORS(app)

# Пароль для админки
ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD', 'Artem1522@')

CONFIG_FILE = 'server_config.json'
CLIENTS_FILE = 'clients.json'

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('logged_in'):
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

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
        'address': 'YOUR_SERVER_IP',
        'port': 443,
        'serverName': 'io.ozone.ru',
        'publicKey': 'YOUR_PUBLIC_KEY',
        'shortId': 'YOUR_SHORT_ID'
    }

def load_clients():
    if os.path.exists(CLIENTS_FILE):
        with open(CLIENTS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return []

def save_clients(clients):
    with open(CLIENTS_FILE, 'w', encoding='utf-8') as f:
        json.dump(clients, f, indent=2, ensure_ascii=False)

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
    """Создание VLESS ссылки для импорта"""
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
    traffic_info = f"{client['traffic_limit']}GB" if client['traffic_limit'] > 0 else "Unlimited"
    name = f"STEPAN VPN | {client['name']} | {traffic_info}"
    
    # URL encode имени
    import urllib.parse
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

@app.route('/subscription/<int:client_id>')
def subscription_page(client_id):
    """Страница подписки с инструкциями"""
    clients = load_clients()
    client = next((c for c in clients if c['id'] == client_id), None)
    
    if not client:
        return "Клиент не найден", 404
    
    subscription_url = f"{request.host_url}api/subscription/{client_id}"
    
    return render_template('subscription.html', 
                         client=client, 
                         subscription_url=subscription_url)

@app.route('/api/clients', methods=['GET'])
def get_clients():
    clients = load_clients()
    return jsonify(clients)

@app.route('/api/clients', methods=['POST'])
def add_client():
    data = request.json
    clients = load_clients()
    
    new_client = {
        'id': len(clients) + 1,
        'uuid': str(uuid.uuid4()),
        'name': data.get('name', f'Client {len(clients) + 1}'),
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
def delete_client(client_id):
    clients = load_clients()
    clients = [c for c in clients if c['id'] != client_id]
    save_clients(clients)
    return jsonify({'success': True})

@app.route('/api/clients/<int:client_id>/toggle', methods=['POST'])
def toggle_client(client_id):
    clients = load_clients()
    for client in clients:
        if client['id'] == client_id:
            client['enabled'] = not client['enabled']
            break
    save_clients(clients)
    return jsonify({'success': True})

@app.route('/api/subscription/<int:client_id>')
def get_subscription(client_id):
    """Генерация подписки для HAPP"""
    clients = load_clients()
    client = next((c for c in clients if c['id'] == client_id), None)
    
    if not client:
        return jsonify({'error': 'Client not found'}), 404
    
    server_config = load_server_config()
    
    vless_link = create_vless_link(client, server_config)
    
    # Кодируем в base64 для подписки
    subscription = base64.b64encode(vless_link.encode()).decode()
    
    return subscription, 200, {'Content-Type': 'text/plain'}

@app.route('/api/qrcode/<int:client_id>')
def get_qrcode(client_id):
    """Генерация QR кода"""
    clients = load_clients()
    client = next((c for c in clients if c['id'] == client_id), None)
    
    if not client:
        return jsonify({'error': 'Client not found'}), 404
    
    server_config = load_server_config()
    
    vless_link = create_vless_link(client, server_config)
    
    qr = qrcode.QRCode(version=1, box_size=10, border=5)
    qr.add_data(vless_link)
    qr.make(fit=True)
    
    img = qr.make_image(fill_color="black", back_color="white")
    
    buf = BytesIO()
    img.save(buf, format='PNG')
    buf.seek(0)
    
    return send_file(buf, mimetype='image/png')

@app.route('/api/config/generate', methods=['POST'])
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
def get_masquerade_sites():
    """Получить список сайтов для маскировки"""
    return jsonify(MASQUERADE_SITES)

@app.route('/api/server/setup', methods=['POST'])
def setup_server():
    """Автоматическая настройка сервера через SSH"""
    data = request.json
    ip = data.get('ip')
    port = data.get('port', 22)
    user = data.get('user', 'root')
    password = data.get('password')
    masquerade = data.get('masquerade', 'io.ozone.ru')
    
    try:
        # Подключение к серверу
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect(ip, port=port, username=user, password=password, timeout=30)
        
        # Установка Xray
        commands = [
            'apt update -y',
            'apt install -y curl wget',
            'bash -c "$(curl -L https://github.com/XTLS/Xray-install/raw/main/install-release.sh)" @ install',
        ]
        
        for cmd in commands:
            stdin, stdout, stderr = ssh.exec_command(cmd, timeout=300)
            stdout.channel.recv_exit_status()
        
        # Генерация ключей на сервере
        stdin, stdout, stderr = ssh.exec_command('xray x25519')
        keys_output = stdout.read().decode()
        
        private_key = ''
        public_key = ''
        for line in keys_output.split('\n'):
            if 'Private key' in line:
                private_key = line.split(': ')[1].strip()
            elif 'Public key' in line:
                public_key = line.split(': ')[1].strip()
        
        # Генерация shortId
        stdin, stdout, stderr = ssh.exec_command('openssl rand -hex 8')
        short_id = stdout.read().decode().strip()
        
        # Создание конфигурации Xray с выбранной маскировкой
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
        
        # Сохранение конфигурации на сервере
        config_json = json.dumps(xray_config, indent=2)
        ssh.exec_command(f"echo '{config_json}' > /usr/local/etc/xray/config.json")
        
        # Открытие порта 443
        ssh.exec_command('ufw allow 443/tcp 2>/dev/null || true')
        
        # Запуск Xray
        ssh.exec_command('systemctl enable xray')
        ssh.exec_command('systemctl restart xray')
        
        # Сохранение конфигурации локально
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
