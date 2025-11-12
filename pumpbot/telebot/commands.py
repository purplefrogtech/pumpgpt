from telegram import Update
from telegram.ext import ContextTypes

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 *PumpGPT aktif!*\n\n"
        "Binance sinyalleri dinleniyor ve anlık olarak Telegram’a gönderiliyor.",
        parse_mode="Markdown"
    )

async def help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📜 *Komutlar:*\n"
        "/start - Botu başlatır\n"
        "/status - Durum bilgisi\n"
        "/help - Bu mesajı gösterir",
        parse_mode="Markdown"
    )

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "✅ Bot şu anda çalışıyor, Binance API bağlantısı aktif.",
        parse_mode="Markdown"
    )
