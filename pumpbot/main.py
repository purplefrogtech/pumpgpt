import asyncio
import csv
import os
import signal
from datetime import datetime, timedelta, timezone
from typing import List

from binance import AsyncClient
from dotenv import load_dotenv
from loguru import logger
from telegram.constants import ParseMode
from telegram.ext import ApplicationBuilder, CommandHandler

from pumpbot.bot.handlers import (
    cmd_config,
    cmd_health,
    cmd_pnl,
    cmd_profile,
    cmd_report,
    cmd_sethorizon,
    cmd_setrisk,
    cmd_start,
    cmd_status,
    cmd_symbols,
    cmd_testsignal,
    cmd_trades,
    notify_all,
)
from pumpbot.core.daily_report import generate_daily_report
from pumpbot.core.database import init_db, save_signal
from pumpbot.core.detector import scan_symbols
from pumpbot.core.quality_filter import get_recent_success_rate, should_emit_signal
from pumpbot.core.sim import SimEngine
from pumpbot.core.throttle import allow_signal
from pumpbot.telebot.notifier import format_daily_report_caption, send_vip_signal

ALLOWED_INTERVALS = {"15m", "30m", "1h"}

# Preferred symbols (will fetch valid ones from Binance)
PREFERRED_SYMBOLS = [
    "BTCUSDT",
    "ETHUSDT",
    "BNBUSDT",
    "SOLUSDT",
    "XRPUSDT",
    "ADAUSDT",
    "AVAXUSDT",
    "MATICUSDT",
    "LINKUSDT",
    "DOTUSDT",
    "ATOMUSDT",
    "ARBUSDT",
    "OPUSDT",
    "NEARUSDT",
    "FTMUSDT",
    "SUIUSDT",
    "INJUSDT",
    "ICPUSDT",
    "UNIUSDT",
    "AAVEUSDT",
    "DYDXUSDT",
    "GMXUSDT",
    "JTOUSDT",
    "FILUSDT",
    "GRTUSDT",
    "DOGEUSDT",
    "SHIBUSDT",
    "PEPEUSDT",
]

VALID_SYMBOLS: List[str] = []


def setup_logging() -> None:
    """Configure loguru output."""
    logger.remove()
    env_level = os.getenv("DEBUG_LEVEL", "").strip().upper()
    debug_mode = os.getenv("DEBUG_MODE", "1") == "1"
    level = env_level if env_level else ("DEBUG" if debug_mode else "INFO")
    logger.add(
        lambda m: print(m, end=""),
        level=level,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{message}</level>",
    )
    logger.info(f"Logging initialized at level {level}")


def _parse_chat_ids(chat_ids_csv: str) -> List[int]:
    ids: List[int] = []
    for raw in chat_ids_csv.split(","):
        token = raw.strip()
        if not token:
            continue
        try:
            ids.append(int(token))
        except ValueError:
            logger.warning(f"Invalid chat_id ignored: {token}")
    return ids


def _build_symbols(env_symbols_csv: str) -> List[str]:
    """Combine env-provided symbols with validated Binance list."""
    env_symbols = [s.strip().upper() for s in env_symbols_csv.split(",") if s.strip()]
    combined: List[str] = []
    source = VALID_SYMBOLS if VALID_SYMBOLS else PREFERRED_SYMBOLS
    for sym in env_symbols + source:
        if sym and sym not in combined:
            combined.append(sym)
    return combined


async def _fetch_valid_symbols_from_binance(client: AsyncClient) -> List[str]:
    """Fetch trading pairs from Binance and filter for USDT spot market."""
    try:
        exchange_info = await client.get_exchange_info()
        valid_symbols = []
        for symbol_info in exchange_info.get("symbols", []):
            symbol = symbol_info.get("symbol")
            if not symbol:
                continue
            if symbol.endswith("USDT") and symbol_info.get("status") == "TRADING":
                valid_symbols.append(symbol)
        logger.info(f"Fetched {len(valid_symbols)} valid USDT symbols from Binance")
        return valid_symbols
    except Exception as exc:
        logger.error(f"Failed to fetch symbols from Binance: {exc}")
        return PREFERRED_SYMBOLS


def _normalize_timeframe(tf: str) -> str:
    tf = (tf or "15m").lower()
    if tf not in ALLOWED_INTERVALS:
        logger.warning(f"Timeframe {tf} not allowed. Using 15m.")
        return "15m"
    return tf


def _append_signal_csv(payload: dict) -> None:
    """Persist minimal signal info to CSV for daily reports."""
    csv_path = os.getenv("SIGNALS_DAILY_CSV", "signals_daily.csv")
    entry_raw = payload.get("entry")
    if isinstance(entry_raw, (list, tuple)) and entry_raw:
        entry_mid = sum(float(x) for x in entry_raw) / len(entry_raw)
    else:
        try:
            entry_mid = float(entry_raw) if entry_raw is not None else None
        except Exception:
            entry_mid = None
    row = [
        datetime.now(timezone.utc).isoformat(),
        payload.get("symbol"),
        entry_mid,
        payload.get("score"),
        payload.get("trend_label"),
        (payload.get("tp_levels") or [None, None])[0],
        (payload.get("tp_levels") or [None, None, None])[1],
        payload.get("sl"),
    ]
    try:
        with open(csv_path, "a", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(row)
    except Exception as exc:
        logger.warning(f"Could not append to {csv_path}: {exc}")


async def schedule_daily_report(app, chat_ids_csv: str, hour: int = 23, minute: int = 59):
    """Send a daily VIP report once per day."""
    while True:
        now = datetime.now()
        target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if target <= now:
            target = target + timedelta(days=1)
        await asyncio.sleep((target - now).total_seconds())

        try:
            summary_text, chart = generate_daily_report()
            caption = format_daily_report_caption(summary_text) if summary_text else None
            for cid in _parse_chat_ids(chat_ids_csv):
                try:
                    if chart and caption:
                        with open(chart, "rb") as f:
                            await app.bot.send_photo(
                                chat_id=cid,
                                photo=f,
                                caption=caption,
                                parse_mode=ParseMode.HTML,
                            )
                    elif caption:
                        await app.bot.send_message(
                            chat_id=cid,
                            text=caption,
                            parse_mode=ParseMode.HTML,
                            disable_web_page_preview=True,
                        )
                except Exception as exc:
                    logger.error(f"Daily report could not be sent to {cid}: {exc}")
        except Exception as exc:
            logger.error(f"Daily report generation failed: {exc}")


async def main():
    load_dotenv()
    setup_logging()
    init_db()

    bot_token = os.getenv("BOT_TOKEN", "").strip()
    chat_ids = os.getenv("TELEGRAM_CHAT_IDS", "").strip()
    api_key = os.getenv("BINANCE_API_KEY", "").strip()
    api_secret = os.getenv("BINANCE_API_SECRET", "").strip()
    env_symbols_csv = os.getenv("SYMBOLS", "")
    timeframe = _normalize_timeframe(os.getenv("TIMEFRAME", "15m"))
    scan_interval = max(int(os.getenv("SCAN_INTERVAL_SECONDS", "60")), 30)
    throttle_minutes = int(os.getenv("THROTTLE_MINUTES", "5"))
    webhook_url = os.getenv("WEBHOOK_URL", "").strip()
    webhook_port = int(os.getenv("WEBHOOK_PORT", "8443"))
    daily_hour = int(os.getenv("DAILY_REPORT_HOUR", "23"))
    daily_minute = int(os.getenv("DAILY_REPORT_MINUTE", "59"))

    if not bot_token:
        logger.error("BOT_TOKEN is required.")
        return

    client = await AsyncClient.create(api_key=api_key or None, api_secret=api_secret or None)
    try:
        VALID_SYMBOLS.clear()
        VALID_SYMBOLS.extend(await _fetch_valid_symbols_from_binance(client))
    except Exception as exc:
        logger.error(f"Could not populate symbols from Binance: {exc}")

    symbols = _build_symbols(env_symbols_csv)
    logger.info(
        f"Config | timeframe={timeframe} scan_interval={scan_interval}s throttle={throttle_minutes}m symbols={len(symbols)}"
    )

    app = ApplicationBuilder().token(bot_token).build()
    app.bot_data["symbols"] = symbols
    app.bot_data["binance_client"] = client

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("symbols", cmd_symbols))
    app.add_handler(CommandHandler("pnl", cmd_pnl))
    app.add_handler(CommandHandler("trades", cmd_trades))
    app.add_handler(CommandHandler("config", cmd_config))
    app.add_handler(CommandHandler("report", cmd_report))
    app.add_handler(CommandHandler("testsignal", cmd_testsignal))
    app.add_handler(CommandHandler("health", cmd_health))
    app.add_handler(CommandHandler("sethorizon", cmd_sethorizon))
    app.add_handler(CommandHandler("setrisk", cmd_setrisk))
    app.add_handler(CommandHandler("profile", cmd_profile))

    async def sim_notifier(text):
        await notify_all(app, chat_ids, text)

    sim = SimEngine(notifier=sim_notifier)

    async def on_alert(payload: dict, market_data: dict):
        """Central signal gate called by scanner."""
        symbol = payload.get("symbol", "UNKNOWN")
        side = payload.get("side", "?")
        try:
            success_rate = get_recent_success_rate()
            payload["success_rate"] = success_rate
            market_data["success_rate"] = success_rate

            if not should_emit_signal(payload, market_data):
                logger.warning(f"[{symbol}] Rejected by quality_filter")
                return False

            if not allow_signal(symbol, minutes=throttle_minutes):
                logger.warning(f"[{symbol}] Rejected by throttle")
                return False

            price_mid = market_data.get("price") or 0.0
            score_val = payload.get("score") or 0.0
            volume_ratio = payload.get("volume_change_pct") or 0.0
            ts_iso = payload.get("created_at") or datetime.now(timezone.utc).isoformat()
            try:
                save_signal(
                    symbol=symbol,
                    price=float(price_mid),
                    volume=float(volume_ratio),
                    score=float(score_val),
                    rsi=payload.get("rsi"),
                    macd=None,
                    macd_sig=None,
                    volume_spike=payload.get("volume_change_pct"),
                    ts_utc=ts_iso,
                )
            except Exception as exc:
                logger.warning(f"[{symbol}] save_signal failed: {exc}")
            _append_signal_csv(payload)

            try:
                await send_vip_signal(app, chat_ids, payload)
                logger.success(f"[{symbol}] VIP signal sent ({side})")
            except Exception as exc:
                logger.error(f"[{symbol}] VIP signal send failed: {exc}")
                return False

            try:
                await sim.on_signal_open(payload)
                logger.success(f"[{symbol}] Trade opened in simulator")
            except Exception as exc:
                logger.error(f"[{symbol}] SimEngine open error: {exc}")

            return True

        except Exception as exc:
            logger.error(f"[{symbol}] on_alert unexpected error: {exc}", exc_info=True)
            return False

    task_scan = asyncio.create_task(
        scan_symbols(
            client,
            symbols,
            timeframe,
            scan_interval,
            on_alert,
            on_tick=sim.on_tick,
            user_id=0,
        )
    )
    task_report = asyncio.create_task(schedule_daily_report(app, chat_ids, hour=daily_hour, minute=daily_minute))

    task_scan.add_done_callback(lambda t: logger.error(f"scan_symbols stopped: {t.exception()}") if t.exception() else None)
    task_report.add_done_callback(
        lambda t: logger.error(f"schedule_daily_report stopped: {t.exception()}") if t.exception() else None
    )

    use_webhook = bool(webhook_url)

    await app.initialize()
    await app.start()
    if use_webhook:
        from urllib.parse import urlparse

        logger.info(f"Webhook mode: url={webhook_url} port={webhook_port}")
        try:
            parsed = urlparse(webhook_url)
            url_path = parsed.path.lstrip("/") or parsed.hostname or ""
            await app.bot.set_webhook(url=webhook_url, drop_pending_updates=True)
            await app.updater.start_webhook(
                listen="0.0.0.0",
                port=webhook_port,
                url_path=url_path,
                webhook_url=webhook_url,
                drop_pending_updates=True,
            )
        except Exception as exc:
            logger.error(f"Webhook setup failed: {exc}")
            use_webhook = False

    if not use_webhook:
        logger.info("Polling mode enabled")
        await app.updater.start_polling(drop_pending_updates=True)

    stop_event = asyncio.Event()

    def _shutdown():
        logger.warning("Shutdown signal received, stopping bot...")
        stop_event.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            asyncio.get_running_loop().add_signal_handler(sig, _shutdown)
        except NotImplementedError:
            pass

    await stop_event.wait()

    task_scan.cancel()
    task_report.cancel()
    try:
        await task_scan
    except asyncio.CancelledError:
        pass
    try:
        await task_report
    except asyncio.CancelledError:
        pass

    await app.updater.stop()

    if use_webhook:
        try:
            await app.bot.delete_webhook(drop_pending_updates=True)
        except Exception as exc:
            logger.warning(f"Webhook delete failed: {exc}")

    await app.stop()
    await app.shutdown()
    await client.close_connection()
    logger.info("Bot shutdown complete.")


if __name__ == "__main__":
    asyncio.run(main())
