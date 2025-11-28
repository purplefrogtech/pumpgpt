from __future__ import annotations

import asyncio
import math
import os
from datetime import datetime, timezone
from typing import List, Tuple

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import talib
from loguru import logger

from pumpbot.core.database import save_signal

# --- Thresholds & defaults ---
ENV_MIN_SCORE = float(os.getenv("MIN_SCORE", "40"))
COOLDOWN_MINUTES = int(os.getenv("COOLDOWN_MINUTES", "5"))
ATR_MIN = float(os.getenv("ATR_MIN", "0.0005"))
MOM_MIN = float(os.getenv("MOM_MIN", "0.10"))
DEFAULT_LEVERAGE = int(os.getenv("DEFAULT_LEVERAGE", "20"))
STRATEGY_NAME = os.getenv("STRATEGY_NAME", "PUMP-GPT v2.0")

TREND_UP = "YUKSELIS"
TREND_DOWN = "DUSUS"
TREND_NEUTRAL = "NOTR"


# -------------------- Binance Kline --------------------
async def fetch_klines(client, symbol: str, interval: str = "1m", limit: int = 200) -> pd.DataFrame:
    raw = await client.get_klines(symbol=symbol, interval=interval, limit=limit)
    cols = [
        "open_time",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "close_time",
        "qav",
        "num_trades",
        "taker_base",
        "taker_quote",
        "ignore",
    ]
    df = pd.DataFrame(raw, columns=cols)
    df["open_time"] = pd.to_datetime(df["open_time"], unit="ms", utc=True)
    for c in ["open", "high", "low", "close", "volume"]:
        df[c] = df[c].astype(float)
    return df


async def fetch_multi_klines(client, symbol: str) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """Return 1m and 5m klines together."""
    d1 = await fetch_klines(client, symbol, "1m", 200)
    d5 = await fetch_klines(client, symbol, "5m", 200)
    return d1, d5


# -------------------- Features --------------------
def compute_features(df: pd.DataFrame):
    close = df["close"].values
    high = df["high"].values
    low = df["low"].values
    vol = df["volume"].values

    rsi = talib.RSI(close, timeperiod=14)
    macd, macd_sig, _ = talib.MACD(close, fastperiod=12, slowperiod=26, signalperiod=9)
    atr = talib.ATR(high, low, close, timeperiod=14)
    ema50 = talib.EMA(close, timeperiod=50)
    ema200 = talib.EMA(close, timeperiod=200)

    vol_ma = pd.Series(vol, copy=False).rolling(20).mean().values
    volume_spike = np.where(vol_ma > 0, vol / vol_ma, 0.0)
    return rsi, macd, macd_sig, volume_spike, atr, ema50, ema200


def momentum_strength(df: pd.DataFrame, bars: int = 10) -> float:
    """Percent change over last N bars (1m)."""
    if len(df) < bars + 1:
        return 0.0
    p0 = df["close"].iloc[-bars - 1]
    p1 = df["close"].iloc[-1]
    return float((p1 - p0) / p0 * 100.0)


def infer_trend(rsi, macd, macd_sig, ema50, ema200, price: float) -> str:
    if rsi[-1] > 55 and macd[-1] > macd_sig[-1] and price > ema200[-1] and ema50[-1] > ema200[-1]:
        return TREND_UP
    if rsi[-1] < 45 and macd[-1] < macd_sig[-1] and price < ema200[-1] and ema50[-1] < ema200[-1]:
        return TREND_DOWN
    return TREND_NEUTRAL


def score_signal(rsi, macd, macd_sig, volume_spike) -> float:
    """Simple and fast scorer."""
    rsi_score = float(np.clip((rsi[-1] - 50) * 1.2, -30, 50))
    macd_score = float((macd[-1] - macd_sig[-1]) * 800.0)
    vol_score = float(np.clip((volume_spike[-1] - 1.0) * 25.0, -10, 80))
    return rsi_score + macd_score + vol_score


# -------------------- Chart --------------------
def generate_chart(symbol: str, df: pd.DataFrame, trend: str, tp1: float, tp2: float, sl: float) -> str:
    """Basic OHLC bars + TP/SL lines."""
    fig, ax = plt.subplots(figsize=(8, 4))
    tail = df.tail(60)
    t = tail["open_time"]
    o, h, l, c = tail["open"], tail["high"], tail["low"], tail["close"]

    for i in range(len(tail)):
        color = "lime" if c.iloc[i] >= o.iloc[i] else "red"
        ax.plot([t.iloc[i], t.iloc[i]], [l.iloc[i], h.iloc[i]], color=color, linewidth=1)
        ax.plot([t.iloc[i], t.iloc[i]], [o.iloc[i], c.iloc[i]], color=color, linewidth=3)

    if trend == TREND_UP:
        ax.axhline(tp1, color="green", linestyle="--", label="TP1")
        ax.axhline(tp2, color="lime", linestyle="--", label="TP2")
        ax.axhline(sl, color="red", linestyle="--", label="SL")
        ax.set_facecolor("#071a07")
    else:
        ax.axhline(tp1, color="red", linestyle="--", label="TP1")
        ax.axhline(tp2, color="darkred", linestyle="--", label="TP2")
        ax.axhline(sl, color="gray", linestyle="--", label="SL")
        ax.set_facecolor("#1a0707")

    ax.legend(loc="upper left")
    ax.set_title(f"{symbol} ({trend})")
    ax.grid(True, alpha=0.15)
    fig.autofmt_xdate()
    plt.tight_layout()

    fname = f"chart_{symbol}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
    plt.savefig(fname, dpi=150)
    plt.close(fig)
    return fname


# -------------------- Scanner loop --------------------
async def scan_symbols(client, symbols, interval, period_seconds, on_alert, sim_engine=None):
    """
    - Produce 1m signals
    - Confirm with 5m EMA(20)
    - Apply ATR & momentum filters + cooldown
    - Build TP/SL, chart and notify
    """
    logger.info(f"🔍 Tarama başlıyor: {symbols} | interval={interval} | her {period_seconds}s")
    last_alert_time: dict[str, datetime] = {}

    while True:
        for sym in symbols:
            try:
                df1, df5 = await fetch_multi_klines(client, sym)
                rsi, macd, macd_sig, vol_spike, atr, ema50, ema200 = compute_features(df1)
                ema20_5m = talib.EMA(df5["close"].values, timeperiod=20)
                price = float(df1["close"].iloc[-1])

                s = score_signal(rsi, macd, macd_sig, vol_spike)
                trend = infer_trend(rsi, macd, macd_sig, ema50, ema200, price)
                mom = momentum_strength(df1, bars=10)
                atr_v = float(atr[-1]) if not math.isnan(atr[-1]) else 0.0

                if atr_v < ATR_MIN or abs(mom) < MOM_MIN or trend == TREND_NEUTRAL:
                    continue

                tf_ok = (trend == TREND_UP and price > float(ema20_5m[-1])) or (
                    trend == TREND_DOWN and price < float(ema20_5m[-1])
                )
                if not tf_ok:
                    continue

                now = datetime.now(timezone.utc)
                cooldown_ok = sym not in last_alert_time or (
                    now - last_alert_time[sym]
                ).total_seconds() > COOLDOWN_MINUTES * 60
                if s < ENV_MIN_SCORE or not cooldown_ok:
                    continue

                if trend == TREND_UP:
                    tp1, tp2, sl = price + atr_v, price + 2 * atr_v, price - atr_v
                    side = "LONG"
                else:
                    tp1, tp2, sl = price - atr_v, price - 2 * atr_v, price + atr_v
                    side = "SHORT"

                entry_low = price * 0.999
                entry_high = price * 1.001
                entry_range: List[float] = [round(entry_low, 6), round(entry_high, 6)]

                chart_file = generate_chart(sym, df1, trend, tp1, tp2, sl)

                payload = {
                    "symbol": sym,
                    "side": side,
                    "timeframe": interval,
                    "entry": entry_range,
                    "tp_levels": [round(tp1, 6), round(tp2, 6)],
                    "sl": round(sl, 6),
                    "leverage": DEFAULT_LEVERAGE,
                    "chart_path": chart_file,
                    "strategy": STRATEGY_NAME,
                    "created_at": now.isoformat(),
                    # compatibility keys
                    "price": round(price, 6),
                    "tp1": round(tp1, 6),
                    "tp2": round(tp2, 6),
                    "score": float(s),
                    "trend": trend,
                    "chart": chart_file,
                }

                logger.success(
                    f"✅ {sym} {side} | skor={s:.2f} | mom={mom:.2f}% | atr={atr_v:.6f}"
                )
                save_signal(
                    sym,
                    price,
                    0.0,
                    s,
                    float(rsi[-1]),
                    float(macd[-1]),
                    float(macd_sig[-1]),
                    float(vol_spike[-1]),
                    now.strftime("%Y-%m-%d %H:%M:%S"),
                )
                last_alert_time[sym] = now

                if on_alert:
                    await on_alert(payload)
                if sim_engine:
                    await sim_engine.on_signal_open(payload)

            except Exception as exc:
                logger.error(f"{sym} taranırken hata: {exc}")

        await asyncio.sleep(period_seconds)
