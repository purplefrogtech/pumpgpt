# pumpbot/bot/handlers.py
import os
from typing import Sequence
from loguru import logger
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from pumpbot.core.database import (
    last_signals, recent_trades, pnl_summary, get_open_trades
)
from pumpbot.core.daily_report import generate_daily_report

# -------------------- Yardımcılar --------------------
def _ids_from_env(raw: str) -> Sequence[int]:
    if not raw:
        return []
    return [int(x.strip()) for x in str(raw).split(",") if x.strip()]

# -------------------- Komutlar --------------------
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "✅ PumpGPT aktif.\n"
        "/status, /symbols, /pnl, /trades, /config, /report komutlarına bakabilirsin."
    )

async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = last_signals(limit=5)
    if not rows:
        await update.message.reply_text("Henüz kayıtlı sinyal yok.")
        return
    lines = ["📈 Son sinyaller:"]
    for sym, price, vol, score, ts in rows:
        lines.append(f"• {sym} | s:{score:.2f} | p:{price:.4f} | v:{vol:.2f} | {ts}")
    await update.message.reply_text("\n".join(lines))

async def cmd_symbols(update: Update, context: ContextTypes.DEFAULT_TYPE):
    symbols = context.bot_data.get("symbols", [])
    await update.message.reply_text("Takip edilen semboller: " + ", ".join(symbols))

async def cmd_testalert(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🔔 Test OK")

async def cmd_pnl(update: Update, context: ContextTypes.DEFAULT_TYPE):
    s = pnl_summary()
    opens = get_open_trades()
    txt = (
        f"💼 PnL Özeti\n"
        f"Kapalı İşlem: {s['closed']}\n"
        f"Kazanan/Kaybeden: {s['wins']}/{s['losses']} (Winrate {s['winrate']:.1f}%)\n"
        f"Toplam PnL: ${s['pnl_usd']:.2f}\n"
        f"Açık Pozisyon: {len(opens)}"
    )
    await update.message.reply_text(txt)

async def cmd_trades(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = recent_trades(limit=10)
    if not rows:
        await update.message.reply_text("İşlem kaydı yok.")
        return
    lines = ["🧾 Son İşlemler:"]
    for sym, side, entry, tp1, tp2, sl, status, opened_at, closed_at, pnl_usd, pnl_pct in rows:
        tail = f" | PnL ${pnl_usd:.2f} ({pnl_pct:.2f}%)" if closed_at else ""
        lines.append(f"• {sym} {side} @{entry} [{status}] {opened_at}{' → '+closed_at if closed_at else ''}{tail}")
    await update.message.reply_text("\n".join(lines))

async def cmd_config(update: Update, context: ContextTypes.DEFAULT_TYPE):
    txt = (
        "⚙️ *Ayarlar*\n"
        f"MIN_SCORE={os.getenv('MIN_SCORE','40')}\n"
        f"COOLDOWN_MINUTES={os.getenv('COOLDOWN_MINUTES','5')}\n"
        f"ATR_MIN={os.getenv('ATR_MIN','0.0005')}\n"
        f"MOM_MIN={os.getenv('MOM_MIN','0.10')}\n"
        f"SIM_EQUITY_USD={os.getenv('SIM_EQUITY_USD','10000')}\n"
        f"SIM_RISK_PER_TRADE_PCT={os.getenv('SIM_RISK_PER_TRADE_PCT','1.0')}"
    )
    await update.message.reply_text(txt, parse_mode=ParseMode.MARKDOWN)

async def cmd_report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    txt, chart = generate_daily_report()
    if txt:
        await update.message.reply_text(txt, parse_mode=ParseMode.MARKDOWN)
    if chart:
        with open(chart, "rb") as f:
            await update.message.reply_photo(photo=f)

# -------------------- Bildirim --------------------
async def notify_all(app, chat_ids_csv: str, text_or_payload):
    """
    payload dict ise:
      { symbol, price, tp1, tp2, sl, score, trend, chart? }
    """
    chat_ids = _ids_from_env(chat_ids_csv)

    if isinstance(text_or_payload, dict):
        p = text_or_payload
        msg_text = (
            f"🚨 *PUMP ALERT*\n"
            f"{p['symbol']}\n"
            f"Fiyat: {p['price']}\n"
            f"TP1: {p['tp1']} | TP2: {p['tp2']} | SL: {p['sl']}\n"
            f"Skor: {p['score']:.2f} | {p['trend']}"
        )
    else:
        p = None
        msg_text = str(text_or_payload)

    for cid in chat_ids:
        try:
            await app.bot.send_message(chat_id=cid, text=msg_text, parse_mode=ParseMode.MARKDOWN)
            # Grafik varsa gönder
            if isinstance(p, dict) and p.get("chart"):
                with open(p["chart"], "rb") as f:
                    await app.bot.send_photo(chat_id=cid, photo=f)
        except Exception as e:
            logger.error(f"Mesaj gönderilemedi {cid}: {e}")

def format_alert(p: dict) -> str:
    return (
        f"🚨 PUMP ALERT\n"
        f"{p['symbol']}\n"
        f"Fiyat: {p['price']}\n"
        f"TP1:{p['tp1']} | TP2:{p['tp2']} | SL:{p['sl']}\n"
        f"Skor: {p['score']:.2f} | {p['trend']}"
    )
