# PumpGPT Quick Run Guide

## 1) Install
```bash
python -m venv venv
venv\Scripts\activate  # on Windows
# source venv/bin/activate on Linux/macOS
pip install -r requirements.txt
```

## 2) Configure
```bash
copy .env.example .env  # or cp on Linux/macOS
# edit .env and set:
# BOT_TOKEN, TELEGRAM_CHAT_IDS, VIP_USER_IDS
# BINANCE_API_KEY / BINANCE_API_SECRET (read-only is fine)
# SYMBOLS, TIMEFRAME, HTF_TIMEFRAME, SCAN_INTERVAL_SECONDS, THROTTLE_MINUTES
```

Defaults are relaxed so the bot produces regular signals while still filtering obvious noise. Daily report time is controlled by `DAILY_REPORT_HOUR` / `DAILY_REPORT_MINUTE`.

## 3) Run
```bash
python pumpbot/main.py
```

Logs should show the scanner starting and Binance/Telegram connections. Charts are saved to `./charts/`.

## 4) Verify in Telegram
- `/health` to check Binance connectivity
- `/testsignal` to confirm formatting
- `/symbols`, `/status`, `/pnl`, `/trades` for live data
- `/sethorizon` and `/setrisk` to tune presets

If signals feel too slow, lower `THROTTLE_MINUTES`, `MIN_RISK_REWARD`, or choose `/setrisk high`. If too noisy, raise `MIN_RISK_REWARD` or set `/setrisk low`.
