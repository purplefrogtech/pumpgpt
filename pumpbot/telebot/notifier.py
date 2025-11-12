import logging
from telegram.constants import ParseMode

logger = logging.getLogger("PumpGPT.Notifier")

async def send_alert(app, chat_ids, signal):
    """
    Telegram’a sinyal mesajı gönderir.
    """
    text = (
        f"🚨 *Yeni Pump Sinyali Tespit Edildi!*\n\n"
        f"💰 Coin: `{signal.get('symbol', 'Bilinmiyor')}`\n"
        f"📈 Fiyat: `{signal.get('price', '---')}`\n"
        f"📊 Hacim Artışı: `{signal.get('volume_change', '---')}%`\n"
        f"🕒 Zaman: `{signal.get('timestamp', '')}`"
    )

    for chat_id in chat_ids:
        try:
            await app.bot.send_message(
                chat_id=chat_id,
                text=text,
                parse_mode=ParseMode.MARKDOWN
            )
            logger.info(f"📤 Sinyal gönderildi → Chat {chat_id}")
        except Exception as e:
            logger.error(f"⚠️ Telegram gönderim hatası ({chat_id}): {e}")
