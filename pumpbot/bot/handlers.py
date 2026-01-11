from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Optional, Sequence

from loguru import logger
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from pumpbot.core.daily_report import generate_daily_report
from pumpbot.core.database import get_open_trades, last_signals, pnl_summary, recent_trades
from pumpbot.telebot.auth import PAYWALL_MESSAGE, contact_keyboard, is_vip, vip_required
from pumpbot.telebot.notifier import format_daily_report_caption, send_vip_signal
from pumpbot.telebot.user_settings import get_horizon_name, get_risk_name, get_user_settings, update_user_settings

BOT_COMMANDS = (
    ("start", "Start the bot"),
    ("help", "Show command menu"),
    ("status", "Recent signals"),
    ("symbols", "Tracked symbols"),
    ("pnl", "PnL summary"),
    ("trades", "Recent trades"),
    ("config", "Show bot config"),
    ("report", "Generate daily report"),
    ("testsignal", "Send a mock signal"),
    ("health", "Connectivity check"),
    ("sethorizon", "Set horizon: short|medium|long"),
    ("setrisk", "Set risk: low|medium|high"),
    ("profile", "Show active settings"),
    ("id", "Show your user/chat IDs"),
)


def _get_control_user_id(context: ContextTypes.DEFAULT_TYPE) -> int:
    raw = context.application.bot_data.get("control_user_id")
    try:
        return int(raw)
    except (TypeError, ValueError):
        return 0


def _is_control_user(context: ContextTypes.DEFAULT_TYPE, user_id: int) -> bool:
    control_id = _get_control_user_id(context)
    return control_id == 0 or control_id == user_id


def _admin_only_notice(user_id: Optional[int], control_id: int) -> str:
    lines = [
        "<b>Admin Only</b>",
        "This command changes global scanner settings.",
    ]
    if user_id is not None:
        lines.append(f"Your user id: <code>{user_id}</code>")
    if control_id:
        lines.append(f"Control user id: <code>{control_id}</code>")
    lines.append("Ask the bot owner or set CONTROL_USER_ID in .env.")
    return "\n".join(lines)


def _build_help_text(is_admin: bool) -> str:
    lines = [
        "<b>PumpGPT Commands</b>",
        "",
        "<b>Signals</b>",
        "/status - Recent signals",
        "/symbols - Tracked symbols",
        "/report - Daily report now",
        "",
        "<b>Performance</b>",
        "/pnl - PnL summary",
        "/trades - Recent trades",
        "",
        "<b>Settings</b>",
        "/profile - Active scanner settings",
        "/sethorizon <short|medium|long> - Set horizon",
        "/setrisk <low|medium|high> - Set risk",
        "",
        "<b>Diagnostics</b>",
        "/health - Connectivity check",
        "/config - Show bot config",
        "/testsignal [here] - Send a mock signal",
        "/id - Show your user/chat IDs",
    ]
    if not is_admin:
        lines.extend(
            [
                "",
                "<i>Admin-only: /sethorizon /setrisk /testsignal</i>",
            ]
        )
    return "\n".join(lines)


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
            logger.warning(f"Invalid chat_id ignored: {val}")
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
    is_admin = _is_control_user(context, user.id)
    msg = (
        "<b>PumpGPT VIP</b>\n"
        f"Welcome, {first}!\n"
        "Signals are monitored and sent to VIP chats.\n"
        "Use /help to see all commands.\n\n"
        "<b>Quick start</b>\n"
        "/status - Recent signals\n"
        "/profile - Active settings\n"
        "/health - Connectivity check"
    )
    if not is_admin:
        msg += "\n\n<i>Admin-only: /sethorizon /setrisk /testsignal</i>"
    await context.bot.send_message(chat_id=chat.id, text=msg, parse_mode=ParseMode.HTML)


@vip_required
async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.effective_message
    if not message:
        return
    user = update.effective_user
    is_admin = _is_control_user(context, user.id) if user else False
    await message.reply_text(_build_help_text(is_admin), parse_mode=ParseMode.HTML, disable_web_page_preview=True)


@vip_required
async def cmd_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.effective_message
    if not message:
        return
    user = update.effective_user
    chat = update.effective_chat
    if not user and not chat:
        return
    lines = ["<b>IDs</b>"]
    if user:
        lines.append(f"User ID: <code>{user.id}</code>")
    if chat:
        lines.append(f"Chat ID: <code>{chat.id}</code>")
    await message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML)


@vip_required
async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.effective_message
    if not message:
        return
    rows = last_signals(limit=5)
    if not rows:
        await message.reply_text("No signals recorded yet.", parse_mode=ParseMode.HTML)
        return

    lines = ["<b>Recent signals</b>"]
    for sym, price, vol, score, ts in rows:
        score_txt = f"{float(score):.2f}" if score is not None else "-"
        price_txt = f"{float(price):.4f}" if price is not None else "-"
        vol_txt = f"{float(vol):.2f}" if vol is not None else "-"
        lines.append(f"- {sym}: score {score_txt} | price {price_txt} | volume {vol_txt} | {ts}")
    await message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML)


@vip_required
async def cmd_symbols(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.effective_message
    if not message:
        return
    symbols = context.bot_data.get("symbols", [])
    if not symbols:
        await message.reply_text("Tracked symbols: -", parse_mode=ParseMode.HTML)
        return
    max_show = 30
    preview = ", ".join(symbols[:max_show])
    suffix = " ..." if len(symbols) > max_show else ""
    await message.reply_text(
        f"Tracked symbols ({len(symbols)}): {preview}{suffix}",
        parse_mode=ParseMode.HTML,
    )


@vip_required
async def cmd_pnl(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.effective_message
    if not message:
        return
    s = pnl_summary()
    opens = get_open_trades()
    txt = (
        "<b>PnL Summary</b>\n"
        f"Closed trades: {s['closed']}\n"
        f"Wins/Losses: {s['wins']}/{s['losses']} (Winrate {s['winrate']:.1f}%)\n"
        f"Total PnL: ${s['pnl_usd']:.2f}\n"
        f"Open positions: {len(opens)}"
    )
    await message.reply_text(txt, parse_mode=ParseMode.HTML)


@vip_required
async def cmd_trades(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.effective_message
    if not message:
        return
    rows = recent_trades(limit=10)
    if not rows:
        await message.reply_text("No trades logged yet.", parse_mode=ParseMode.HTML)
        return

    lines = ["<b>Recent trades</b>"]
    for sym, side, entry, tp1, tp2, sl, status, opened_at, closed_at, pnl_usd, pnl_pct in rows:
        tail = f" | PnL ${pnl_usd:.2f} ({pnl_pct:.2f}%)" if closed_at else ""
        closed_info = f" -> {closed_at}" if closed_at else ""
        lines.append(f"- {sym} {side} @ {entry} [{status}] {opened_at}{closed_info}{tail}")
    await message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML)


@vip_required
async def cmd_config(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.effective_message
    if not message:
        return
    symbols = context.application.bot_data.get("symbols") or []
    control_id = _get_control_user_id(context)
    vip_ids = _ids_from_env(os.getenv("VIP_USER_IDS", ""))
    chat_ids = _ids_from_env(os.getenv("TELEGRAM_CHAT_IDS", ""))
    txt = (
        "<b>Config</b>\n"
        f"TIMEFRAME={os.getenv('TIMEFRAME','15m')}\n"
        f"HTF_TIMEFRAME={os.getenv('HTF_TIMEFRAME','1h')}\n"
        f"SCAN_INTERVAL_SECONDS={os.getenv('SCAN_INTERVAL_SECONDS','60')}\n"
        f"SCAN_CONCURRENCY={os.getenv('SCAN_CONCURRENCY','3')}\n"
        f"THROTTLE_MINUTES={os.getenv('THROTTLE_MINUTES','5')}\n"
        f"MIN_RISK_REWARD={os.getenv('MIN_RISK_REWARD','1.2')}\n"
        f"MIN_ATR_PCT={os.getenv('MIN_ATR_PCT','0.000075')}\n"
        f"MIN_VOLUME_RATIO={os.getenv('MIN_VOLUME_RATIO','1.2')}\n"
        f"DEBUG_LEVEL={os.getenv('DEBUG_LEVEL','INFO')}\n"
        f"SYMBOLS_COUNT={len(symbols)}\n"
        f"VIP_USER_IDS={len(vip_ids)}\n"
        f"TELEGRAM_CHAT_IDS={len(chat_ids)}\n"
        f"CONTROL_USER_ID={control_id if control_id else 'not set'}"
    )
    await message.reply_text(txt, parse_mode=ParseMode.HTML)


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
    user = update.effective_user
    app = context.application
    symbol = os.getenv("TEST_SIGNAL_SYMBOL", "BTCUSDT").upper()
    timeframe = os.getenv("TEST_SIGNAL_TIMEFRAME", "15m")
    chat_ids_csv = os.getenv("TELEGRAM_CHAT_IDS", "")

    control_id = _get_control_user_id(context)
    if user and not _is_control_user(context, user.id):
        if chat_id:
            await context.bot.send_message(
                chat_id=chat_id,
                text=_admin_only_notice(user.id, control_id),
                parse_mode=ParseMode.HTML,
            )
        return

    send_scope = "VIP list"
    if context.args and context.args[0].lower() in {"here", "local", "me", "self"}:
        if chat_id:
            chat_ids_csv = str(chat_id)
            send_scope = "this chat"
        else:
            send_scope = "VIP list (no chat id available)"

    status_lines = ["<b>PumpGPT Test Mode</b>", f"Target: {send_scope}", "Sending a mock signal..."]

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
        status_lines.append("VIP notification: OK")
    except Exception as exc:
        status_lines.append(f"VIP notification error: {exc}")
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
    lines = ["<b>Health Check</b>"]
    if not client:
        lines.append("Binance client missing")
    else:
        try:
            server_time = await client.get_server_time()
            ts = datetime.fromtimestamp(server_time["serverTime"] / 1000, tz=timezone.utc)
            lines.append(f"Binance OK | Server Time: {ts.strftime('%Y-%m-%d %H:%M:%S UTC')}")
        except Exception as exc:
            lines.append(f"Binance server time error: {exc}")
        try:
            klines = await client.get_klines(symbol=symbol, interval="15m", limit=50)
            lines.append(f"{symbol} 15m candles fetched: {len(klines)}")
        except Exception as exc:
            lines.append(f"Kline fetch error ({symbol}): {exc}")
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
            f"ALERT\n"
            f"{p.get('symbol','?')}\n"
            f"Price: {p.get('price','-')}\n"
            f"TP1: {p.get('tp1','-')} | TP2: {p.get('tp2','-')} | SL: {p.get('sl','-')}\n"
            f"Score: {score_str} | {p.get('trend','-')}"
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
            logger.error(f"Message send failed {cid}: {exc}")


@vip_required
async def cmd_sethorizon(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Set time horizon for user: short, medium, long"""
    user = update.effective_user
    chat = update.effective_chat

    if not user or not chat:
        return

    control_id = _get_control_user_id(context)
    if not _is_control_user(context, user.id):
        await context.bot.send_message(
            chat_id=chat.id,
            text=_admin_only_notice(user.id, control_id),
            parse_mode=ParseMode.HTML,
        )
        return

    if not context.args or len(context.args) < 1:
        await context.bot.send_message(
            chat_id=chat.id,
            text="Usage: /sethorizon short|medium|long",
            parse_mode=ParseMode.HTML,
        )
        return

    horizon = context.args[0].lower()
    if horizon not in ["short", "medium", "long"]:
        await context.bot.send_message(
            chat_id=chat.id,
            text="Invalid horizon. Use: short, medium, long",
            parse_mode=ParseMode.HTML,
        )
        return

    success = update_user_settings(control_id, "horizon", horizon)
    if success:
        horizon_name = get_horizon_name(horizon)
        msg = (
            "<b>Horizon Updated</b>\n"
            f"New horizon: <b>{horizon_name}</b>\n"
            "Applies to the global scanner."
        )
        await context.bot.send_message(chat_id=chat.id, text=msg, parse_mode=ParseMode.HTML)
        logger.info(f"User {user.id} set global horizon to {horizon} (control_id={control_id})")
    else:
        await context.bot.send_message(
            chat_id=chat.id,
            text="Could not save the setting.",
            parse_mode=ParseMode.HTML,
        )


@vip_required
async def cmd_setrisk(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Set risk level for user: low, medium, high"""
    user = update.effective_user
    chat = update.effective_chat

    if not user or not chat:
        return

    control_id = _get_control_user_id(context)
    if not _is_control_user(context, user.id):
        await context.bot.send_message(
            chat_id=chat.id,
            text=_admin_only_notice(user.id, control_id),
            parse_mode=ParseMode.HTML,
        )
        return

    if not context.args or len(context.args) < 1:
        await context.bot.send_message(
            chat_id=chat.id,
            text="Usage: /setrisk low|medium|high",
            parse_mode=ParseMode.HTML,
        )
        return

    risk = context.args[0].lower()
    if risk not in ["low", "medium", "high"]:
        await context.bot.send_message(
            chat_id=chat.id,
            text="Invalid risk. Use: low, medium, high",
            parse_mode=ParseMode.HTML,
        )
        return

    success = update_user_settings(control_id, "risk", risk)
    if success:
        descriptions = {
            "low": "Fewer signals, higher reliability.",
            "medium": "Balanced frequency and quality.",
            "high": "More signals, looser filters.",
        }
        risk_name = get_risk_name(risk)
        msg = (
            "<b>Risk Updated</b>\n"
            f"New risk: <b>{risk_name}</b>\n"
            f"{descriptions.get(risk, '')}"
        )
        await context.bot.send_message(chat_id=chat.id, text=msg, parse_mode=ParseMode.HTML)
        logger.info(f"User {user.id} set global risk to {risk} (control_id={control_id})")
    else:
        await context.bot.send_message(
            chat_id=chat.id,
            text="Could not save the setting.",
            parse_mode=ParseMode.HTML,
        )


@vip_required
async def cmd_profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show user's profile and settings"""
    user = update.effective_user
    chat = update.effective_chat

    if not user or not chat:
        return

    control_id = _get_control_user_id(context)
    settings = get_user_settings(control_id)
    horizon = settings.get("horizon", "medium")
    risk = settings.get("risk", "medium")

    horizon_name = get_horizon_name(horizon)
    risk_name = get_risk_name(risk)
    base_tf = os.getenv("TIMEFRAME", "15m")
    htf_tf = os.getenv("HTF_TIMEFRAME", "1h")
    tf_str = f"{base_tf} (base), {htf_tf} (HTF)"

    signal_intensity = {
        ("short", "low"): ("Very Low", "High"),
        ("short", "medium"): ("Low", "High"),
        ("short", "high"): ("High", "Medium"),
        ("medium", "low"): ("Low", "High"),
        ("medium", "medium"): ("Medium", "Medium"),
        ("medium", "high"): ("High", "Medium"),
        ("long", "low"): ("Very Low", "High"),
        ("long", "medium"): ("Low", "Medium"),
        ("long", "high"): ("Medium", "Medium"),
    }
    intensity, reliability = signal_intensity.get((horizon, risk), ("?", "?"))

    msg = (
        "<b>User Profile</b>\n"
        f"Horizon: <b>{horizon_name}</b>\n"
        f"Risk: <b>{risk_name}</b>\n"
        "Scope: global scanner\n\n"
        f"Timeframes: {tf_str}\n"
        f"Signal intensity: {intensity}\n"
        f"Reliability: {reliability}\n\n"
        "Update with:\n"
        "/sethorizon <short|medium|long>\n"
        "/setrisk <low|medium|high>"
    )
    if not _is_control_user(context, user.id):
        msg += "\n\n<i>Only the bot owner can change these settings.</i>"

    await context.bot.send_message(
        chat_id=chat.id,
        text=msg,
        parse_mode=ParseMode.HTML,
    )
