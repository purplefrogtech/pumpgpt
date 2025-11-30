import asyncio
import os
import signal
from datetime import datetime, timedelta
from typing import List

from binance import AsyncClient
from dotenv import load_dotenv
from loguru import logger
from telegram.constants import ParseMode
from telegram.ext import ApplicationBuilder, CommandHandler

from pumpbot.bot.handlers import (
    cmd_config,
    cmd_pnl,
    cmd_report,
    cmd_start,
    cmd_status,
    cmd_symbols,
    cmd_testsignal,
    cmd_health,
    cmd_trades,
    notify_all,
)
from pumpbot.core.daily_report import generate_daily_report
from pumpbot.core.database import init_db
from pumpbot.core.detector import scan_symbols
from pumpbot.core.quality_filter import get_recent_success_rate, should_emit_signal
from pumpbot.core.sim import SimEngine
from pumpbot.core.throttle import allow_signal
from pumpbot.telebot.notifier import format_daily_report_caption, send_vip_signal


ALLOWED_INTERVALS = {"15m", "30m", "1h"}
MAJORS = ["BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT", "ADAUSDT"]
MID_CAPS = ["AVAXUSDT", "MATICUSDT", "LINKUSDT", "DOTUSDT", "ATOMUSDT"]
HIGH_BETA = ["APTUSDT", "OPUSDT", "NEARUSDT", "FTMUSDT", "ARBUSDT"]


# -------------------- Logging --------------------
def setup_logging():
    logger.remove()
    env_level = os.getenv("DEBUG_LEVEL", "").strip().upper()
    debug_mode = os.getenv("DEBUG_MODE", "0") == "1"
    level = env_level if env_level else ("DEBUG" if debug_mode else "INFO")
    logger.add(
        lambda m: print(m, end=""),
        level=level,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{message}</level>",
    )
    logger.info(f"Logging initialized at level {level}")


def _parse_chat_ids(chat_ids_csv: str) -> List[int]:
    ids = []
    for raw in chat_ids_csv.split(","):
        token = raw.strip()
        if not token:
            continue
        try:
            ids.append(int(token))
        except ValueError:
            logger.warning(f"Geçersiz chat_id atlandı: {token}")
    return ids


def _build_symbols(env_symbols_csv: str) -> List[str]:
    env_symbols = [s.strip().upper() for s in env_symbols_csv.split(",") if s.strip()]
    combined: List[str] = []
    for sym in env_symbols + MAJORS + MID_CAPS + HIGH_BETA:
        if sym and sym not in combined:
            combined.append(sym)
    return combined


def _normalize_timeframe(tf: str) -> str:
    tf = (tf or "15m").lower()
    if tf not in ALLOWED_INTERVALS:
        logger.warning(f"Timeframe {tf} not allowed. Using 15m.")
        return "15m"
    return tf


# -------------------- Gün sonu raporu --------------------
async def schedule_daily_report(app, chat_ids_csv: str, hour: int = 23, minute: int = 59):
    """Simple scheduler: send daily VIP report once per day."""
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
                    logger.error(f"Gün sonu raporu gönderilemedi ({cid}): {exc}")
        except Exception as exc:
            logger.error(f"Gün sonu raporu oluşturulamadı: {exc}")


# -------------------- Main --------------------
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
    throttle_minutes = int(os.getenv("THROTTLE_MINUTES", "30"))

    symbols = _build_symbols(env_symbols_csv)

    logger.info(
        f"Config | timeframe={timeframe} scan_interval={scan_interval}s throttle={throttle_minutes}m symbols={len(symbols)}"
    )

    # Telegram app
    app = ApplicationBuilder().token(bot_token).build()
    app.bot_data["symbols"] = symbols

    # Komutlar
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("symbols", cmd_symbols))
    app.add_handler(CommandHandler("pnl", cmd_pnl))
    app.add_handler(CommandHandler("trades", cmd_trades))
    app.add_handler(CommandHandler("config", cmd_config))
    app.add_handler(CommandHandler("report", cmd_report))
    app.add_handler(CommandHandler("testsignal", cmd_testsignal))
    app.add_handler(CommandHandler("health", cmd_health))

    # Binance client + Sim
    client = await AsyncClient.create(api_key=api_key, api_secret=api_secret)
    logger.info("📡 Binance API bağlantısı başarılı.")
    app.bot_data["binance_client"] = client

    sim = SimEngine(notifier=lambda text: notify_all(app, chat_ids, text))

    async def on_alert(payload: dict, market_data: dict):
        """
        Central signal gating logic.
        Returns True if signal was successfully sent, False if blocked.
        """
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

            try:
                await send_vip_signal(app, chat_ids, payload)
                logger.success(f"[{symbol}] VIP signal sent ({side})")
            except Exception as exc:
                logger.error(f"[{symbol}] VIP sinyal gönderimi başarısız: {exc}")
                return False

            try:
                await sim.on_signal_open(payload)
                logger.success(f"[{symbol}] Trade opened in simulator")
            except Exception as exc:
                logger.error(f"[{symbol}] SimEngine open hatası: {exc}")
                # Don't fail the entire signal for sim error

            return True

        except Exception as exc:
            logger.error(f"[{symbol}] on_alert unexpected error: {exc}", exc_info=True)
            return False

    # Paralel görevler
    task_scan = asyncio.create_task(
        scan_symbols(
            client,
            symbols,
            timeframe,
            scan_interval,
            on_alert,
        )
    )
    task_report = asyncio.create_task(schedule_daily_report(app, chat_ids))

    task_scan.add_done_callback(lambda t: logger.error(f"scan_symbols stopped: {t.exception()}") if t.exception() else None)
    task_report.add_done_callback(
        lambda t: logger.error(f"schedule_daily_report stopped: {t.exception()}") if t.exception() else None
    )

    # Telegram polling
    await app.initialize()
    await app.start()
    await app.updater.start_polling(drop_pending_updates=True)

    # Graceful shutdown için sinyal yakalama
    stop_event = asyncio.Event()

    def _shutdown():
        logger.warning("⛔ Kapanış sinyali alındı, durduruluyor...")
        stop_event.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            asyncio.get_running_loop().add_signal_handler(sig, _shutdown)
        except NotImplementedError:
            # Windows: add_signal_handler may not be available
            pass

    await stop_event.wait()

    # Temizlik
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
    await app.stop()
    await app.shutdown()
    await client.close_connection()


if __name__ == "__main__":
    asyncio.run(main())
