# Webhook Mode Deployment Guide

## Overview

Bu rehber, PUMP•GPT botunun **WebHook modunda** Telegram API ile nasıl haberleştiğini ve deployment'ı açıklar. WebHook modu, polling'den farklı olarak bot'un pasif olarak beklemesine gerek yoktur - Telegram doğrudan bot'a HTTP POST istekleri gönderir.

## Webhook vs Polling

| Feature | Polling | WebHook |
|---------|---------|---------|
| **Bağlantı** | Bot → Telegram (her 30s) | Telegram → Bot (on-demand) |
| **Latency** | 30+ saniye | <100ms |
| **Verimlilik** | Düşük (sürekli sorgulama) | Yüksek (event-driven) |
| **Deployment** | Basit (firewall sorun yok) | URL + SSL gerekli |
| **Çatışma** | Evet (multiple instances) | Hayır (tek endpoint) |

## Configuration

### 1. Environment Variables

`.env` dosyasında webhook parametrelerini ayarla:

```bash
# WebHook konfigürasyonu
WEBHOOK_URL=https://your-domain.com:8443/webhook
WEBHOOK_PORT=8443

# Eğer WEBHOOK_URL boş bırakılırsa, sistem otomatik polling moduna döner
```

### 2. Certificate Requirements

Telegram WebHook için **HTTPS + valid certificate** gereklidir.

**Seçenek A: Let's Encrypt (Önerilen)**
```bash
# Ubuntu/Debian üzerinde
sudo apt install certbot python3-certbot-nginx
sudo certbot certonly -d your-domain.com
```

Sertifika yolu: `/etc/letsencrypt/live/your-domain.com/`

**Seçenek B: Self-signed Certificate** (geliştirme amaçlı)
```bash
openssl req -x509 -newkey rsa:2048 -keyout key.pem -out cert.pem -days 365 -nodes
```

### 3. Network Configuration

**Port Forward (Eğer NAT'ın arkasındaysanız)**
- TCP port 8443 dış dünyaya açık olmalı
- Firewall kurallarını kontrol et

**Domain Setup**
- `your-domain.com` → bot sunucusunun IP'sine yönlendir
- DNS A record: `your-domain.com A 1.2.3.4`

## WebHook Mode Operation

### Auto-detection

Bot başlatıldığında:

```python
use_webhook = bool(webhook_url and webhook_url.strip())

if use_webhook:
    logger.info(f"WebHook mode: url={webhook_url} port={webhook_port}")
    await app.run_webhook(
        listen="0.0.0.0",
        port=webhook_port,
        webhook_url=webhook_url,
        drop_pending_updates=True,
    )
else:
    logger.info("Polling mode: WEBHOOK_URL not set, falling back to polling")
    await app.updater.start_polling(drop_pending_updates=True)
```

### Set Webhook to Telegram

Bot başlangıçta otomatik olarak webhook'u Telegram'a kaydeder:

```python
await app.bot.set_webhook(url=webhook_url, drop_pending_updates=True)
logger.success(f"WebHook set: {webhook_url}")
```

### Delete Webhook on Shutdown

Bot kapatılırken webhook silinir:

```python
await app.bot.delete_webhook(drop_pending_updates=True)
```

## Production Deployment (Raspberry Pi)

### 1. SSL Certificate

Raspberry Pi'de Let's Encrypt setup:

```bash
# SSH into Pi
ssh pi@raspberry-pi-ip

# Certbot yükle
sudo apt install certbot python3-certbot-nginx -y

# Sertifika oluştur (DNS validation)
sudo certbot certonly --preferred-challenges dns -d your-domain.com

# Kontrol et
ls -la /etc/letsencrypt/live/your-domain.com/
```

### 2. Bot Service (systemd)

`/etc/systemd/system/pumpgpt.service` oluştur:

```ini
[Unit]
Description=PUMP•GPT Crypto Signal Bot
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=pi
WorkingDirectory=/home/pi/pumpgpt
Environment="PATH=/home/pi/pumpgpt/venv/bin"
ExecStart=/home/pi/pumpgpt/venv/bin/python pumpbot/main.py
Restart=always
RestartSec=10

# SSL sertifikaları
Environment="WEBHOOK_URL=https://your-domain.com:8443/webhook"
Environment="WEBHOOK_PORT=8443"

StandardOutput=append:/var/log/pumpgpt.log
StandardError=append:/var/log/pumpgpt.log

[Install]
WantedBy=multi-user.target
```

Servis'i etkinleştir:

```bash
sudo systemctl daemon-reload
sudo systemctl enable pumpgpt
sudo systemctl start pumpgpt
sudo systemctl status pumpgpt
```

### 3. Port Forward (Router)

- **External Port**: 8443
- **Internal IP**: Raspberry Pi IP
- **Internal Port**: 8443

### 4. Nginx Reverse Proxy (Optional)

`/etc/nginx/sites-available/pumpgpt`:

```nginx
server {
    listen 443 ssl http2;
    server_name your-domain.com;

    ssl_certificate /etc/letsencrypt/live/your-domain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/your-domain.com/privkey.pem;

    location / {
        proxy_pass http://127.0.0.1:8080;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

## Commands in WebHook Mode

Tüm Telegram komutları WebHook modunda çalışır:

```
/start       - Bot paneli
/status      - Son sinyaller
/symbols     - İzlenen semboller
/pnl         - P&L özeti
/trades      - İşlem geçmişi
/testsignal  - Test sinyali gönder
/health      - Binance API sağlığı
/config      - Konfigürasyon
/report      - Gün sonu raporu
```

## Debugging WebHook

### Check webhook status

```bash
curl -s -X GET https://api.telegram.org/bot<BOT_TOKEN>/getWebhookInfo | jq
```

Beklenen sonuç:
```json
{
  "ok": true,
  "result": {
    "url": "https://your-domain.com:8443/webhook",
    "has_custom_certificate": false,
    "pending_update_count": 0
  }
}
```

### View logs

```bash
# Polling modunda
tail -f /var/log/pumpgpt.log

# Real-time follow
journalctl -u pumpgpt -f
```

### Common Issues

| Issue | Solution |
|-------|----------|
| **"WebHook setup failed"** | URL/certificate geçerli olup olmadığını kontrol et |
| **Commands not working** | WebHook endpoint açık mı ve Telegram'a erişebiliyor mu kontrol et |
| **Delayed signals** | Log'ta error var mı kontrol et; network connectivity verify et |
| **Port 8443 in use** | `sudo lsof -i :8443` ile kullanan process'i bul ve kapat |

## Performance Notes

WebHook modunda:
- **Update latency**: <100ms (vs 30s polling)
- **Resource usage**: Daha az (continuous polling yok)
- **Scalability**: Production-ready
- **Reliability**: Telegram auto-retries failed updates

## Fallback to Polling

Webhook setup başarısız olursa, bot otomatik polling moduna döner. Log'ta göreceksin:

```
❌ WebHook setup failed: ...
ℹ️ Polling mode: WEBHOOK_URL not set, falling back to polling
```

## Roslyn Recommendations

✅ **Production için önerilir:**
- Let's Encrypt SSL certificate
- Fixed domain name
- Port 8443 open to internet
- systemd service for auto-restart

✅ **Development için:**
- Polling mode (WEBHOOK_URL boş)
- No certificate required
- Local testing yapabilirsin

## Further Reading

- [python-telegram-bot WebHook Docs](https://python-telegram-bot.readthedocs.io/en/stable/telegram.ext.webhookhandler.html)
- [Telegram Bot API](https://core.telegram.org/bots/api)
- [Let's Encrypt](https://letsencrypt.org/)
