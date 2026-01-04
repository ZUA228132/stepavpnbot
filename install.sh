#!/bin/bash

echo "🚀 Установка Xray Panel..."

# Обновление системы
apt update && apt upgrade -y

# Установка зависимостей
apt install -y python3 python3-pip python3-venv curl wget

# Установка Xray
bash -c "$(curl -L https://github.com/XTLS/Xray-install/raw/main/install-release.sh)" @ install

# Создание виртуального окружения
python3 -m venv venv
source venv/bin/activate

# Установка Python зависимостей
pip install -r requirements.txt

# Генерация ключей
echo "🔑 Генерация ключей Reality..."
KEYS=$(xray x25519)
PRIVATE_KEY=$(echo "$KEYS" | grep "Private key" | awk '{print $3}')
PUBLIC_KEY=$(echo "$KEYS" | grep "Public key" | awk '{print $3}')
SHORT_ID=$(openssl rand -hex 8)

echo "Приватный ключ: $PRIVATE_KEY"
echo "Публичный ключ: $PUBLIC_KEY"
echo "Short ID: $SHORT_ID"

# Создание конфигурации Xray сервера
cat > /usr/local/etc/xray/config.json << EOF
{
  "log": {
    "loglevel": "warning"
  },
  "inbounds": [
    {
      "port": 443,
      "protocol": "vless",
      "settings": {
        "clients": [],
        "decryption": "none"
      },
      "streamSettings": {
        "network": "xhttp",
        "security": "reality",
        "realitySettings": {
          "dest": "io.ozone.ru:443",
          "serverNames": ["io.ozone.ru"],
          "privateKey": "$PRIVATE_KEY",
          "shortIds": ["$SHORT_ID"]
        },
        "xhttpSettings": {
          "mode": "auto",
          "path": "/"
        }
      }
    }
  ],
  "outbounds": [
    {
      "protocol": "freedom",
      "tag": "direct"
    }
  ]
}
EOF

# Запуск Xray
systemctl enable xray
systemctl restart xray

echo "✅ Xray установлен и запущен!"
echo ""
echo "📝 Сохраните эти данные:"
echo "Публичный ключ: $PUBLIC_KEY"
echo "Short ID: $SHORT_ID"
echo ""
echo "Теперь обновите app.py, заменив YOUR_PUBLIC_KEY и YOUR_SHORT_ID"
echo ""
echo "Запустите панель: python3 app.py"
