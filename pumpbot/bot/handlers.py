from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Sequence

from loguru import logger
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from pumpbot.core.daily_report import generate_daily_report
from pumpbot.core.database import get_open_trades, last_signals, pnl_summary, recent_trades
from pumpbot.telebot.auth import PAYWALL_MESSAGE, contact_keyboard, is_vip, vip_required
from pumpbot.telebot.notifier import format_daily_report_caption, send_vip_signal


def _ids_from_env(raw: str) -> Sequence[int]:
    if not raw:
        return []
    ids = []
    for token in str(raw).split(","):
        val = token.strip()
        if not val:
            continue
        try:
            ids.append(int(val))
        except ValueError:
            logger.warning(f"Geçersiz chat_id atlandı: {val}")
    return ids


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat = update.effective_chat

    if not user or not chat:
        logger.warning("Start command without user/chat info; cannot respond.")
        return

    if not is_vip(user.id):
        try:
            await context.bot.send_message(
                chat_id=chat.id,
                text=PAYWALL_MESSAGE,
                parse_mode=ParseMode.HTML,
                reply_markup=contact_keyboard(),
            )
        except Exception as exc:
            logger.error(f"/start paywall message failed for chat {chat.id}: {exc}")
        return

    first = user.first_name or "VIP"
    msg = (
        "💎 <b>PUMP•GPT VIP PANEL</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"Hoş geldin {first}!\n"
        "VIP durumun: <b>AKTİF</b>\n\n"
        "Komutlar:\n"
        "• /status  – Son sinyaller\n"
        "• /symbols – İzlenen semboller\n"
        "• /pnl     – PnL özeti\n"
        "• /trades  – Son işlemler\n"
        "• /config  – Konfigürasyon\n"
        "• /report  – Gün sonu raporu\n"
        "• /testsignal – Sistem sağlığı testi\n"
        "• /health – Binance bağlantı sağlığı\n\n"
        "Bol kazançlar!"
    )
    await context.bot.send_message(chat_id=chat.id, text=msg, parse_mode=ParseMode.HTML)


@vip_required
async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = last_signals(limit=5)
    if not rows:
        await update.message.reply_text("Henüz kayıtlı sinyal yok.", parse_mode=ParseMode.HTML)
        return

    lines = ["🧭 <b>Son sinyaller</b>"]
    for sym, price, vol, score, ts in rows:
        lines.append(f"• {sym}: skor <b>{score:.2f}</b> | fiyat {price:.4f} | hacim {vol:.2f} | {ts}")
    await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML)


@vip_required
async def cmd_symbols(update: Update, context: ContextTypes.DEFAULT_TYPE):
    symbols = context.bot_data.get("symbols", [])
    await update.message.reply_text(
        "Takip edilen semboller: " + (", ".join(symbols) if symbols else "-"),
        parse_mode=ParseMode.HTML,
    )


@vip_required
async def cmd_pnl(update: Update, context: ContextTypes.DEFAULT_TYPE):
    s = pnl_summary()
    opens = get_open_trades()
    txt = (
        "🧭 <b>PnL Özeti</b>\n"
        f"KapalI işlem: {s['closed']}\n"
        f"Kazanan/Kaybeden: {s['wins']}/{s['losses']} (Winrate {s['winrate']:.1f}%)\n"
        f"Toplam PnL: ${s['pnl_usd']:.2f}\n"
        f"Açık pozisyon: {len(opens)}"
    )
    await update.message.reply_text(txt, parse_mode=ParseMode.HTML)


@vip_required
async def cmd_trades(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = recent_trades(limit=10)
    if not rows:
        await update.message.reply_text("İşlem kaydı yok.", parse_mode=ParseMode.HTML)
        return

    lines = ["🧭 <b>Son işlemler</b>"]
    for sym, side, entry, tp1, tp2, sl, status, opened_at, closed_at, pnl_usd, pnl_pct in rows:
        tail = f" | PnL ${pnl_usd:.2f} ({pnl_pct:.2f}%)" if closed_at else ""
        closed_info = f" → {closed_at}" if closed_at else ""
        lines.append(f"• {sym} {side} @{entry} [{status}] {opened_at}{closed_info}{tail}")
    await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML)


@vip_required
async def cmd_config(update: Update, context: ContextTypes.DEFAULT_TYPE):
    txt = (
        "🧭 <b>Ayarlar</b>\n"
        f"MIN_SCORE={os.getenv('MIN_SCORE','40')}\n"
        f"COOLDOWN_MINUTES={os.getenv('COOLDOWN_MINUTES','5')}\n"
        f"ATR_MIN={os.getenv('ATR_MIN','0.0005')}\n"
        f"MOM_MIN={os.getenv('MOM_MIN','0.10')}\n"
        f"SIM_EQUITY_USD={os.getenv('SIM_EQUITY_USD','10000')}\n"
        f"SIM_RISK_PER_TRADE_PCT={os.getenv('SIM_RISK_PER_TRADE_PCT','1.0')}\n"
        f"THROTTLE_MINUTES={os.getenv('THROTTLE_MINUTES','10')}\n"
        f"DEBUG_LEVEL={os.getenv('DEBUG_LEVEL','INFO')}"
    )
    await update.message.reply_text(txt, parse_mode=ParseMode.HTML)


@vip_required
async def cmd_report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    summary_text, chart = generate_daily_report()
    chat_id = update.effective_chat.id if update.effective_chat else None
    if not chat_id:
        logger.warning("Report command missing chat_id.")
        return

    caption = format_daily_report_caption(summary_text) if summary_text else None
    try:
        if chart and caption:
            with open(chart, "rb") as f:
                await context.bot.send_photo(
                    chat_id=chat_id,
                    photo=f,
                    caption=caption,
                    parse_mode=ParseMode.HTML,
                )
        elif caption:
            await context.bot.send_message(chat_id=chat_id, text=caption, parse_mode=ParseMode.HTML)
    except Exception as exc:
        logger.error(f"Report send failed for chat {chat_id}: {exc}")


@vip_required
async def cmd_testsignal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    chat_id = chat.id if chat else None
    app = context.application
    symbol = os.getenv("TEST_SIGNAL_SYMBOL", "BTCUSDT").upper()
    timeframe = os.getenv("TEST_SIGNAL_TIMEFRAME", "15m")
    chat_ids_csv = os.getenv("TELEGRAM_CHAT_IDS", "")

    status_lines = ["🧪 <b>PUMP•GPT TEST MODE</b>", "────────────────────────"]

    test_payload = {
        "symbol": symbol,
        "side": "LONG",
        "timeframe": timeframe,
        "entry": [100.0, 101.0],
        "tp_levels": [103.0, 105.0, 108.0],
        "sl": 98.5,
        "leverage": 10,
        "chart_path": None,
        "strategy": "TEST-RUN",
        "created_at": datetime.utcnow().isoformat(),
        "trend_label": "Test",
        "rsi": 55.0,
        "atr_pct": 0.012,
        "volume_change_pct": 25.0,
        "risk_reward": 1.5,
    }
    try:
        await send_vip_signal(app, chat_ids_csv, test_payload)
        status_lines.append("✅ VIP Bildirim Sistemi: OK")
    except Exception as exc:
        status_lines.append(f"❌ VIP bildirim hatası: {exc}")
        logger.error(f"/testsignal notify error: {exc}")

    if chat_id:
        try:
            await context.bot.send_message(
                chat_id=chat_id,
                text="\n".join(status_lines),
                parse_mode=ParseMode.HTML,
                disable_web_page_preview=True,
            )
        except Exception as exc:
            logger.error(f"/testsignal status send failed: {exc}")


@vip_required
async def cmd_health(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id if update.effective_chat else None
    client = context.application.bot_data.get("binance_client")
    symbols = context.application.bot_data.get("symbols") or []
    symbol = symbols[0] if symbols else "BTCUSDT"
    lines = ["🩺 <b>Health Check</b>"]
    if not client:
        lines.append("❌ Binance client yok")
    else:
        try:
            server_time = await client.get_server_time()
            ts = datetime.fromtimestamp(server_time["serverTime"] / 1000, tz=timezone.utc)
            lines.append(f"✅ Binance OK | Server Time: {ts.strftime('%Y-%m-%d %H:%M:%S UTC')}")
        except Exception as exc:
            lines.append(f"❌ Binance server time hatası: {exc}")
        try:
            klines = await client.get_klines(symbol=symbol, interval="15m", limit=50)
            lines.append(f"✅ {symbol} 15m mum sayısı: {len(klines)}")
        except Exception as exc:
            lines.append(f"❌ Kline hatası ({symbol}): {exc}")
    if chat_id:
        await context.bot.send_message(chat_id=chat_id, text="\n".join(lines), parse_mode=ParseMode.HTML)


async def notify_all(app, chat_ids_csv: str, text_or_payload):
    """
    Broadcast helper for generic notifications (simulation, etc.).
    payload dict can include { symbol, price, tp1, tp2, sl, score, trend, chart? }
    """
    chat_ids = _ids_from_env(chat_ids_csv)

    if isinstance(text_or_payload, dict):
        p = text_or_payload
        score_val = p.get("score")
        score_str = f"{float(score_val):.2f}" if score_val is not None else "-"
        msg_text = (
            f"🧭 ALERT\n"
            f"{p['symbol']}\n"
            f"Fiyat: {p.get('price','-')}\n"
            f"TP1: {p.get('tp1','-')} | TP2: {p.get('tp2','-')} | SL: {p.get('sl','-')}\n"
            f"Skor: {score_str} | {p.get('trend','-')}"
        )
    else:
        p = None
        msg_text = str(text_or_payload)

    for cid in chat_ids:
        try:
            await app.bot.send_message(chat_id=cid, text=msg_text, parse_mode=ParseMode.HTML)
            if isinstance(p, dict) and p.get("chart"):
                with open(p["chart"], "rb") as f:
                    await app.bot.send_photo(chat_id=cid, photo=f)
        except Exception as exc:
            logger.error(f"Mesaj gönderilemedi {cid}: {exc}")


def format_alert(p: dict) -> str:
    return (
        f"🧭 PUMP ALERT\n"
        f"{p['symbol']}\n"
        f"Fiyat: {p['price']}\n"
        f"TP1:{p['tp1']} | TP2:{p['tp2']} | SL:{p['sl']}\n"
        f"Skor: {p['score']:.2f} | {p['trend']}"
    )
