import asyncio
import os
import signal
from datetime import datetime, timedelta

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
    cmd_trades,
    notify_all,
)
from pumpbot.core.daily_report import generate_daily_report
from pumpbot.core.database import init_db
from pumpbot.core.detector import scan_symbols
from pumpbot.core.sim import SimEngine
from pumpbot.telebot.notifier import format_daily_report_caption, send_vip_signal


# -------------------- Logging --------------------
def setup_logging(debug: bool):
    logger.remove()
    level = "DEBUG" if debug else "INFO"
    logger.add(
        lambda m: print(m, end=""),
        level=level,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{message}</level>",
    )


def _parse_chat_ids(chat_ids_csv: str):
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


# -------------------- Gün sonu raporu --------------------
async def schedule_daily_report(app, chat_ids_csv: str, hour: int = 23, minute: int = 59):
    """Simple scheduler: send daily VIP report once per day."""
    while True:
        now = datetime.now()
        target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if target <= now:
            target = target + timedelta(days=1)
        await asyncio.sleep((target - now).total_seconds())

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


# -------------------- Main --------------------
async def main():
    load_dotenv()
    debug_mode = os.getenv("DEBUG_MODE", "0") == "1"
    setup_logging(debug_mode)

    init_db()

    bot_token = os.getenv("BOT_TOKEN", "").strip()
    chat_ids = os.getenv("TELEGRAM_CHAT_IDS", "").strip()
    api_key = os.getenv("BINANCE_API_KEY", "").strip()
    api_secret = os.getenv("BINANCE_API_SECRET", "").strip()
    symbols = os.getenv(
        "SYMBOLS", "BTCUSDT,ETHUSDT,SOLUSDT,DOGEUSDT,BNBUSDT"
    ).replace(" ", "").split(",")

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

    # Binance client + Sim
    client = await AsyncClient.create(api_key=api_key, api_secret=api_secret)
    logger.info("📡 Binance API bağlantısı başarılı.")
    sim = SimEngine(notifier=lambda text: notify_all(app, chat_ids, text))

    async def on_alert(payload: dict):
        await send_vip_signal(app, chat_ids, payload)

    # Paralel görevler
    task_scan = asyncio.create_task(
        scan_symbols(
            client,
            symbols,
            "1m",
            int(os.getenv("SCAN_INTERVAL_SECONDS", "30")),
            on_alert,
            sim,
        )
    )
    task_report = asyncio.create_task(schedule_daily_report(app, chat_ids))

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
