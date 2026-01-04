import telebot
from telebot import types
import json
import os
import uuid
import secrets
import string
from datetime import datetime

BOT_TOKEN = '8548659256:AAErmzpCN4i8dMkOEYg4rc6ZqnXc4G_DzEY'
CLIENTS_FILE = 'clients.json'
USERS_FILE = 'bot_users.json'
PANEL_URL = os.environ.get('PANEL_URL', 'http://127.0.0.1:5000')

bot = telebot.TeleBot(BOT_TOKEN)

def generate_sub_code(length=7):
    chars = string.ascii_letters + string.digits
    return ''.join(secrets.choice(chars) for _ in range(length))

def load_clients():
    if os.path.exists(CLIENTS_FILE):
        with open(CLIENTS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return []

def save_clients(clients):
    with open(CLIENTS_FILE, 'w', encoding='utf-8') as f:
        json.dump(clients, f, indent=2, ensure_ascii=False)

def load_users():
    if os.path.exists(USERS_FILE):
        with open(USERS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}

def save_users(users):
    with open(USERS_FILE, 'w', encoding='utf-8') as f:
        json.dump(users, f, indent=2, ensure_ascii=False)

def get_or_create_client(user_id, username, first_name):
    users = load_users()
    clients = load_clients()
    user_id_str = str(user_id)
    
    if user_id_str in users:
        client_id = users[user_id_str]['client_id']
        client = next((c for c in clients if c['id'] == client_id), None)
        if client:
            return client, False
    
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
        'name': first_name or username or f'User_{user_id}',
        'email': '',
        'telegram_id': user_id,
        'telegram_username': username,
        'traffic_limit': 0,
        'traffic_used': 0,
        'expiry_date': '',
        'created_at': datetime.now().isoformat(),
        'enabled': True
    }
    
    clients.append(new_client)
    save_clients(clients)
    
    users[user_id_str] = {
        'client_id': new_client['id'],
        'sub_code': sub_code,
        'username': username,
        'first_name': first_name,
        'registered_at': datetime.now().isoformat()
    }
    save_users(users)
    
    return new_client, True

def main_menu():
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        types.InlineKeyboardButton("🔑 Получить подписку", callback_data="get_sub"),
        types.InlineKeyboardButton("📊 Мой статус", callback_data="status"),
        types.InlineKeyboardButton("📖 Инструкция", callback_data="help"),
        types.InlineKeyboardButton("💬 Поддержка", callback_data="support")
    )
    return markup

@bot.message_handler(commands=['start'])
def start(message):
    user = message.from_user
    
    welcome_text = f"""
⚡ *STEPAN VPN* — Premium VPN Service

Добро пожаловать, *{user.first_name}*! 🎉

🔒 Безлимитный VPN с Reality протоколом
🚀 Скорость до 1 Гбит/с
🛡️ Защита от блокировок и DPI
🌍 Доступ к любым сайтам

Нажмите кнопку ниже, чтобы получить подписку:
"""
    
    bot.send_message(
        message.chat.id,
        welcome_text,
        parse_mode='Markdown',
        reply_markup=main_menu()
    )

@bot.callback_query_handler(func=lambda call: call.data == "get_sub")
def get_subscription(call):
    user = call.from_user
    bot.answer_callback_query(call.id)
    
    client, is_new = get_or_create_client(user.id, user.username, user.first_name)
    sub_code = client.get('sub_code', str(client['id']))
    
    subscription_url = f"{PANEL_URL}/s/{sub_code}"
    
    if is_new:
        text = f"""
🎉 *Подписка создана!*

Ваша персональная страница:
🔗 `{subscription_url}`

На странице вы найдёте:
• Готовую VLESS ссылку с ключами
• QR код — отсканируй и подключайся
• Кнопку быстрого подключения

⚡ Нажмите кнопку ниже!
"""
    else:
        text = f"""
🔑 *Ваша подписка*

Страница подписки:
🔗 `{subscription_url}`

• Готовая VLESS ссылка
• QR код для сканирования
• Статистика использования

⚡ Отсканируй QR или нажми кнопку!
"""
    
    markup = types.InlineKeyboardMarkup(row_width=1)
    webapp = types.WebAppInfo(url=subscription_url)
    markup.add(types.InlineKeyboardButton("⚡ Открыть подписку", web_app=webapp))
    markup.add(types.InlineKeyboardButton("🌐 Открыть в браузере", url=subscription_url))
    markup.add(types.InlineKeyboardButton("🔙 Главное меню", callback_data="menu"))
    
    bot.edit_message_text(
        text,
        call.message.chat.id,
        call.message.message_id,
        parse_mode='Markdown',
        reply_markup=markup
    )

@bot.callback_query_handler(func=lambda call: call.data == "status")
def show_status(call):
    bot.answer_callback_query(call.id)
    
    user = call.from_user
    users = load_users()
    clients = load_clients()
    user_id_str = str(user.id)
    
    if user_id_str not in users:
        text = "❌ У вас ещё нет подписки.\n\nНажмите «Получить подписку» в главном меню."
    else:
        client_id = users[user_id_str]['client_id']
        client = next((c for c in clients if c['id'] == client_id), None)
        
        if client:
            status = "✅ Активна" if client['enabled'] else "❌ Отключена"
            traffic_limit = f"{client['traffic_limit']} GB" if client['traffic_limit'] > 0 else "∞ Безлимит"
            traffic_used = f"{client['traffic_used'] / 1024:.2f} GB"
            sub_code = client.get('sub_code', '---')
            
            text = f"""
📊 *Статус подписки*

👤 Имя: *{client['name']}*
📡 Статус: {status}
📦 Лимит: {traffic_limit}
📈 Использовано: {traffic_used}
📅 Создана: {client['created_at'][:10]}

🔗 Код: `{sub_code}`
"""
        else:
            text = "❌ Подписка не найдена"
    
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("🔙 Главное меню", callback_data="menu"))
    
    bot.edit_message_text(
        text,
        call.message.chat.id,
        call.message.message_id,
        parse_mode='Markdown',
        reply_markup=markup
    )

@bot.callback_query_handler(func=lambda call: call.data == "help")
def show_help(call):
    bot.answer_callback_query(call.id)
    
    text = """
📖 *Инструкция по подключению*

*1️⃣ Скачайте HAPP*
• iOS: App Store
• Android: Google Play

*2️⃣ Получите подписку*
Нажмите «Получить подписку» в боте

*3️⃣ Подключитесь*
• Отсканируйте QR код в HAPP
• Или нажмите «Подключить VPN»
• Или скопируйте VLESS ссылку

*4️⃣ Готово!*
VPN подключится автоматически 🚀

💡 QR код уже содержит все ключи — просто отсканируй и кайфуй!
"""
    
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("🔙 Главное меню", callback_data="menu"))
    
    bot.edit_message_text(
        text,
        call.message.chat.id,
        call.message.message_id,
        parse_mode='Markdown',
        reply_markup=markup
    )

@bot.callback_query_handler(func=lambda call: call.data == "support")
def show_support(call):
    bot.answer_callback_query(call.id)
    
    text = """
💬 *Поддержка*

Если возникли проблемы:

1️⃣ Убедитесь, что HAPP установлен
2️⃣ Обновите подписку в приложении
3️⃣ Перезапустите HAPP

📩 Связь с поддержкой:
@stepan\\_vpn\\_support

⏰ Отвечаем в течение 24 часов
"""
    
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("🔙 Главное меню", callback_data="menu"))
    
    bot.edit_message_text(
        text,
        call.message.chat.id,
        call.message.message_id,
        parse_mode='Markdown',
        reply_markup=markup
    )

@bot.callback_query_handler(func=lambda call: call.data == "menu")
def back_to_menu(call):
    bot.answer_callback_query(call.id)
    
    user = call.from_user
    
    text = f"""
⚡ *STEPAN VPN* — Premium VPN Service

Привет, *{user.first_name}*! 👋

Выберите действие:
"""
    
    bot.edit_message_text(
        text,
        call.message.chat.id,
        call.message.message_id,
        parse_mode='Markdown',
        reply_markup=main_menu()
    )

if __name__ == '__main__':
    print("⚡ STEPAN VPN Bot запущен!")
    print(f"📡 Panel URL: {PANEL_URL}")
    bot.infinity_polling()
