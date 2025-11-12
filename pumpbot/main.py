# pumpbot/main.py
import os
import asyncio
import signal
from loguru import logger
from dotenv import load_dotenv
from binance import AsyncClient
from telegram.ext import ApplicationBuilder, CommandHandler

from pumpbot.core.database import init_db
from pumpbot.core.detector import scan_symbols
from pumpbot.core.sim import SimEngine
from pumpbot.bot.handlers import (
    cmd_start, cmd_status, cmd_symbols, cmd_pnl, cmd_trades,
    cmd_config, cmd_report, notify_all
)
from pumpbot.core.daily_report import generate_daily_report

# -------------------- Logging --------------------
def setup_logging(debug: bool):
    logger.remove()
    level = "DEBUG" if debug else "INFO"
    logger.add(lambda m: print(m, end=""), level=level,
               format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{message}</level>")

# -------------------- Gün sonu raporu --------------------
async def schedule_daily_report(app, chat_ids_csv: str, hour: int = 23, minute: int = 59):
    """Basit zamanlayıcı: her gece rapor yollar."""
    while True:
        # bir sonraki HH:MM'a kadar uyku
        now = asyncio.get_event_loop().time()
        # 24 saatlik döngü (saniye bazında kabaca)
        delay = 86400 - (now % 86400)
        await asyncio.sleep(delay)
        txt, chart = generate_daily_report()
        if txt:
            await notify_all(app, chat_ids_csv, txt)
            if chart:
                for cid in [int(x.strip()) for x in chat_ids_csv.split(",") if x.strip()]:
                    with open(chart, "rb") as f:
                        await app.bot.send_photo(chat_id=cid, photo=f)

# -------------------- Main --------------------
async def main():
    load_dotenv()
    DEBUG = os.getenv("DEBUG_MODE", "0") == "1"
    setup_logging(DEBUG)

    init_db()

    BOT_TOKEN  = os.getenv("BOT_TOKEN", "").strip()
    CHAT_IDS   = os.getenv("TELEGRAM_CHAT_IDS", "").strip()
    API_KEY    = os.getenv("BINANCE_API_KEY", "").strip()
    API_SECRET = os.getenv("BINANCE_API_SECRET", "").strip()
    SYMBOLS    = os.getenv("SYMBOLS", "BTCUSDT,ETHUSDT,SOLUSDT,DOGEUSDT,BNBUSDT").replace(" ", "").split(",")

    # Telegram app
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.bot_data["symbols"] = SYMBOLS

    # Komutlar
    app.add_handler(CommandHandler("start",   cmd_start))
    app.add_handler(CommandHandler("status",  cmd_status))
    app.add_handler(CommandHandler("symbols", cmd_symbols))
    app.add_handler(CommandHandler("pnl",     cmd_pnl))
    app.add_handler(CommandHandler("trades",  cmd_trades))
    app.add_handler(CommandHandler("config",  cmd_config))
    app.add_handler(CommandHandler("report",  cmd_report))

    # Binance client + Sim
    client = await AsyncClient.create(api_key=API_KEY, api_secret=API_SECRET)
    logger.info("📡 Binance API bağlantısı başarılı.")
    sim = SimEngine(notifier=lambda text: notify_all(app, CHAT_IDS, text))

    async def on_alert(payload: dict):
        await notify_all(app, CHAT_IDS, payload)

    # Paralel görevler
    task_scan   = asyncio.create_task(scan_symbols(client, SYMBOLS, "1m", int(os.getenv("SCAN_INTERVAL_SECONDS", "30")), on_alert, sim))
    task_report = asyncio.create_task(schedule_daily_report(app, CHAT_IDS))

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
            # Windows için: add_signal_handler her zaman yok
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
