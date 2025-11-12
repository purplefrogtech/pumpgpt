#!/usr/bin/env bash
set -e

echo "🚀 PumpGPT Installer (Raspberry Pi)"

# 1️⃣ Gereklilikler
sudo apt update -y
sudo apt install -y python3 python3-venv python3-pip git curl

# 2️⃣ Klasör ve venv
sudo mkdir -p /opt/pumpgpt
sudo chown $USER:$USER /opt/pumpgpt
cd /opt/pumpgpt

if [ ! -d "venv" ]; then
  python3 -m venv venv
fi
source venv/bin/activate

# 3️⃣ Kaynak dosyalar kopyalanmış olmalı (veya git clone)
if [ ! -f "requirements.txt" ]; then
  echo "❗ Lütfen kaynak dosyaları bu klasöre yükleyin (pumpbot diziniyle birlikte)"
  exit 1
fi

pip install --upgrade pip wheel setuptools
pip install -r requirements.txt

# 4️⃣ .env dosyası oluştur
if [ ! -f ".env" ]; then
  cp .env.example .env
  echo "⚙️  .env oluşturuldu. Lütfen düzenleyin: /opt/pumpgpt/.env"
fi

# 5️⃣ Systemd service
SERVICE_FILE=/etc/systemd/system/pumpgpt.service
sudo tee $SERVICE_FILE >/dev/null <<EOF
[Unit]
Description=PumpGPT Auto Service
After=network.target

[Service]
Type=simple
WorkingDirectory=/opt/pumpgpt
ExecStart=/opt/pumpgpt/venv/bin/python -m pumpbot.main
Restart=always
User=$USER
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
EOF

# 6️⃣ Servis etkinleştir
sudo systemctl daemon-reload
sudo systemctl enable pumpgpt.service
sudo systemctl restart pumpgpt.service

sleep 2
sudo systemctl status pumpgpt.service --no-pager
echo "✅ PumpGPT kuruldu ve çalışıyor! Logları görmek için:"
echo "  journalctl -u pumpgpt -f"
