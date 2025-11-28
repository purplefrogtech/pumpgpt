from __future__ import annotations

import asyncio
import os
from datetime import datetime, timezone
from typing import List, Optional, Tuple

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import talib
from loguru import logger

from pumpbot.core.database import save_signal

ALLOWED_INTERVALS = {"5m", "15m", "30m", "1h"}
DEFAULT_INTERVAL = os.getenv("TIMEFRAME", "15m")
HIGHER_INTERVAL = os.getenv("HIGHER_TIMEFRAME", "30m")
COOLDOWN_MINUTES = int(os.getenv("COOLDOWN_MINUTES", "5"))
DEFAULT_LEVERAGE = int(os.getenv("DEFAULT_LEVERAGE", "20"))
STRATEGY_NAME = os.getenv("STRATEGY_NAME", "PUMP-GPT v2.0")
VOLUME_SPIKE_RATIO = 1.5


def normalize_interval(interval: str) -> str:
    if not interval:
        return "15m"
    interval = interval.lower()
    if interval == "1m":
        logger.warning("1m timeframe is not allowed. Falling back to 15m.")
        return "15m"
    if interval not in ALLOWED_INTERVALS:
        logger.warning(f"Interval {interval} is not allowed. Falling back to 15m.")
        return "15m"
    return interval


async def fetch_klines(client, symbol: str, interval: str, limit: int = 240) -> pd.DataFrame:
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


async def fetch_with_fallback(
    client, symbol: str, primary: str, fallback: str = "5m", limit: int = 240
) -> Optional[pd.DataFrame]:
    primary = normalize_interval(primary)
    fallback = normalize_interval(fallback)
    try:
        df = await fetch_klines(client, symbol, primary, limit=limit)
        if len(df) >= 60:
            return df
        logger.warning(f"{symbol} {primary} has insufficient data; trying {fallback}")
    except Exception as exc:
        logger.warning(f"{symbol} {primary} fetch failed: {exc}; trying {fallback}")
    try:
        df_fb = await fetch_klines(client, symbol, fallback, limit=limit)
        return df_fb
    except Exception as exc:
        logger.error(f"{symbol} fallback fetch failed: {exc}")
        return None


def volume_spike_ratio(volumes: pd.Series, window: int = 20) -> float:
    if len(volumes) < window + 1:
        return 0.0
    mean_vol = volumes.tail(window).mean()
    if mean_vol == 0:
        return 0.0
    return float(volumes.iloc[-1] / mean_vol)


def detect_market_structure(df: pd.DataFrame, lookback: int = 8) -> str:
    recent_highs = df["high"].tail(lookback)
    recent_lows = df["low"].tail(lookback)
    hh_hl = all(
        recent_highs.iloc[i] > recent_highs.iloc[i - 1] and recent_lows.iloc[i] > recent_lows.iloc[i - 1]
        for i in range(1, len(recent_highs))
    )
    lh_ll = all(
        recent_highs.iloc[i] < recent_highs.iloc[i - 1] and recent_lows.iloc[i] < recent_lows.iloc[i - 1]
        for i in range(1, len(recent_highs))
    )
    if hh_hl:
        return "HH-HL"
    if lh_ll:
        return "LH-LL"

    closes = df["close"].tail(lookback)
    slope = np.polyfit(range(len(closes)), closes, 1)[0] if len(closes) >= 2 else 0
    if slope > 0:
        return "HH-HL"
    if slope < 0:
        return "LH-LL"
    return "CHOP"


def detect_candle_pattern(df: pd.DataFrame) -> Tuple[bool, str, Optional[str]]:
    if len(df) < 2:
        return False, "NONE", None
    prev = df.iloc[-2]
    last = df.iloc[-1]
    prev_body = abs(prev["close"] - prev["open"])
    last_body = abs(last["close"] - last["open"])
    upper_wick = last["high"] - max(last["open"], last["close"])
    lower_wick = min(last["open"], last["close"]) - last["low"]

    bullish_engulf = (
        last["close"] > last["open"]
        and prev["close"] < prev["open"]
        and last["close"] >= prev["open"]
        and last["open"] <= prev["close"]
    )
    bearish_engulf = (
        last["close"] < last["open"]
        and prev["close"] > prev["open"]
        and last["close"] <= prev["open"]
        and last["open"] >= prev["close"]
    )
    hammer = last_body > 0 and lower_wick > last_body * 2 and last["close"] > last["open"]
    shooting_star = last_body > 0 and upper_wick > last_body * 2 and last["close"] < last["open"]

    if bullish_engulf:
        return True, "Bullish Engulfing", "LONG"
    if bearish_engulf:
        return True, "Bearish Engulfing", "SHORT"
    if hammer:
        return True, "Hammer", "LONG"
    if shooting_star:
        return True, "Shooting Star", "SHORT"
    return False, "NONE", None


def calculate_volatility_status(atr_val: float, price: float) -> Tuple[str, float]:
    ratio = (atr_val / price) if price else 0.0
    if ratio >= 0.01:
        return "⚡ Çok yüksek", ratio
    if ratio >= 0.005:
        return "⚡ Yüksek", ratio
    if ratio >= 0.002:
        return "🌀 Orta", ratio
    return "💤 Düşük", ratio


def calculate_momentum(df: pd.DataFrame, bars: int = 5) -> float:
    if len(df) < bars + 1:
        return 0.0
    p0 = df["close"].iloc[-bars - 1]
    p1 = df["close"].iloc[-1]
    return float((p1 - p0) / p0)


def calc_volume_change_pct(df: pd.DataFrame, window: int = 20) -> float:
    vols = df["volume"]
    if len(vols) < window:
        return 0.0
    mean_vol = vols.tail(window).mean()
    if mean_vol == 0:
        return 0.0
    return float((vols.iloc[-1] - mean_vol) / mean_vol * 100.0)


def calc_liquidity_blocked(price: float, df: pd.DataFrame, atr_val: float, side: str) -> bool:
    recent_high = df["high"].tail(12).max()
    recent_low = df["low"].tail(12).min()
    buffer = atr_val * 0.4
    if side == "LONG":
        return price + buffer >= recent_high
    return price - buffer <= recent_low


def calc_entry_targets(price: float, atr_val: float, side: str, df: pd.DataFrame):
    swing_low = float(df["low"].tail(12).min())
    swing_high = float(df["high"].tail(12).max())

    if side == "LONG":
        entry_low = price - 0.30 * atr_val
        entry_high = price - 0.05 * atr_val
        sl = min(price - 1.2 * atr_val, swing_low)
        tp1 = price + 1.6 * atr_val
        tp2 = price + 2.4 * atr_val
    else:
        entry_low = price + 0.05 * atr_val
        entry_high = price + 0.30 * atr_val
        sl = max(price + 1.2 * atr_val, swing_high)
        tp1 = price - 1.6 * atr_val
        tp2 = price - 2.4 * atr_val

    entry_range = sorted([entry_low, entry_high])
    avg_entry = sum(entry_range) / len(entry_range)
    stop_distance = abs(avg_entry - sl)
    reward_distance = abs(tp1 - avg_entry)
    risk_reward = reward_distance / stop_distance if stop_distance else 0.0

    tp_levels = [tp1, tp2]
    return entry_range, tp_levels, sl, risk_reward, stop_distance


def calculate_spread_pct(df: pd.DataFrame, price: float) -> float:
    candle_range = df["high"].iloc[-1] - df["low"].iloc[-1]
    return float(candle_range / price) if price else 0.0


def infer_trend_from_ema(ema50, ema200) -> str:
    if len(ema50) == 0 or len(ema200) == 0 or np.isnan(ema50[-1]) or np.isnan(ema200[-1]):
        return "NEUTRAL"
    if ema50[-1] > ema200[-1]:
        return "UP"
    if ema50[-1] < ema200[-1]:
        return "DOWN"
    return "NEUTRAL"


def generate_chart(symbol: str, df: pd.DataFrame, side: str, tp1: float, tp2: float, sl: float) -> str:
    fig, ax = plt.subplots(figsize=(8, 4))
    tail = df.tail(120)
    t = tail["open_time"]
    o, h, l, c = tail["open"], tail["high"], tail["low"], tail["close"]

    for i in range(len(tail)):
        color = "lime" if c.iloc[i] >= o.iloc[i] else "red"
        ax.plot([t.iloc[i], t.iloc[i]], [l.iloc[i], h.iloc[i]], color=color, linewidth=1)
        ax.plot([t.iloc[i], t.iloc[i]], [o.iloc[i], c.iloc[i]], color=color, linewidth=3)

    if side == "LONG":
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
    ax.set_title(f"{symbol} ({side})")
    ax.grid(True, alpha=0.15)
    fig.autofmt_xdate()
    plt.tight_layout()

    fname = f"chart_{symbol}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
    plt.savefig(fname, dpi=150)
    plt.close(fig)
    return fname


async def scan_symbols(client, symbols, interval, period_seconds, on_alert):
    """
    Mid-term scanner:
      - Enforces min timeframe 5m (default 15m)
      - Requires EMA trend alignment, RSI rebound, volume spike, structure, candle pattern
      - Builds ATR-based entry/TP/SL and forwards payload to on_alert
    """
    interval = normalize_interval(interval)
    higher_interval = normalize_interval(HIGHER_INTERVAL)
    logger.info(f"🔍 Mid-term scan starting | interval={interval}, htf={higher_interval} | symbols={symbols}")
    last_alert_time: dict[str, datetime] = {}

    while True:
        for sym in symbols:
            try:
                df_main = await fetch_with_fallback(client, sym, interval)
                if df_main is None or len(df_main) < 60:
                    continue
                df_htf = await fetch_with_fallback(client, sym, higher_interval, fallback="30m")

                price = float(df_main["close"].iloc[-1])
                rsi = talib.RSI(df_main["close"].values, timeperiod=14)
                atr = talib.ATR(df_main["high"].values, df_main["low"].values, df_main["close"].values, timeperiod=14)
                if len(rsi) == 0 or len(atr) == 0:
                    continue
                ema50 = talib.EMA(df_main["close"].values, timeperiod=50)
                ema200 = talib.EMA(df_main["close"].values, timeperiod=200)
                macd, macd_signal, _ = talib.MACD(
                    df_main["close"].values, fastperiod=12, slowperiod=26, signalperiod=9
                )
                vol_ratio = volume_spike_ratio(df_main["volume"])
                volume_spike_ok = vol_ratio >= VOLUME_SPIKE_RATIO

                trend_main = infer_trend_from_ema(ema50, ema200)
                trend_htf = "NEUTRAL"
                if df_htf is not None:
                    ema50_htf = talib.EMA(df_htf["close"].values, timeperiod=50)
                    ema200_htf = talib.EMA(df_htf["close"].values, timeperiod=200)
                    trend_htf = infer_trend_from_ema(ema50_htf, ema200_htf)

                structure = detect_market_structure(df_main)
                pattern_ok, pattern_name, pattern_side = detect_candle_pattern(df_main)
                momentum = calculate_momentum(df_main, bars=5)
                volatility_state, volatility_score = calculate_volatility_status(float(atr[-1]), price)
                volume_change_pct = calc_volume_change_pct(df_main)
                returns_std = df_main["close"].pct_change().tail(6).std()
                low_volatility = returns_std < 0.001

                rsi_rebound_long = len(rsi) >= 2 and rsi[-2] < 32 and rsi[-1] > 35
                rsi_rebound_short = len(rsi) >= 2 and rsi[-2] > 68 and rsi[-1] < 65

                side: Optional[str] = None
                if (
                    trend_main == "UP"
                    and trend_htf in ("UP", "NEUTRAL")
                    and structure == "HH-HL"
                    and rsi_rebound_long
                ):
                    side = "LONG"
                elif (
                    trend_main == "DOWN"
                    and trend_htf in ("DOWN", "NEUTRAL")
                    and structure == "LH-LL"
                    and rsi_rebound_short
                ):
                    side = "SHORT"

                if not side or not volume_spike_ok:
                    continue
                if not pattern_ok or (pattern_side and pattern_side != side):
                    continue

                entry_range, tp_levels, sl, risk_reward, stop_distance = calc_entry_targets(
                    price, float(atr[-1]), side, df_main
                )

                # Extra guards
                if risk_reward < 1.5:
                    continue
                if stop_distance <= 0:
                    continue
                liquidity_blocked = calc_liquidity_blocked(price, df_main, float(atr[-1]), side)
                spread_pct = calculate_spread_pct(df_main, price)

                now = datetime.now(timezone.utc)
                # cooldown safety (shorter than throttle)
                if sym in last_alert_time and (now - last_alert_time[sym]).total_seconds() < COOLDOWN_MINUTES * 60:
                    continue

                chart_file = generate_chart(sym, df_main, side, tp_levels[0], tp_levels[1], sl)

                logger.success(
                    f"{sym} {side} aday | R:R {risk_reward:.2f} | Vol {volatility_state} | Hacim {vol_ratio:.2f}"
                )

                payload = {
                    "symbol": sym,
                    "side": side,
                    "timeframe": interval,
                    "entry": [round(entry_range[0], 6), round(entry_range[1], 6)],
                    "tp_levels": [round(tp, 6) for tp in tp_levels],
                    "sl": round(sl, 6),
                    "leverage": DEFAULT_LEVERAGE,
                    "chart_path": chart_file,
                    "strategy": STRATEGY_NAME,
                    "created_at": now.isoformat(),
                    "trend_direction": "UPTREND" if side == "LONG" else "DOWNTREND",
                    "trend_label": "🔼 Uptrend" if side == "LONG" else "🔽 Downtrend",
                    "rsi": float(rsi[-1]),
                    "volatility_state": volatility_state,
                    "volume_change_pct": volume_change_pct,
                    "risk_reward": risk_reward,
                    "market_structure": structure,
                    "candle_pattern": pattern_name,
                    "price": round(price, 6),
                    # compatibility fields
                    "tp1": round(tp_levels[0], 6),
                    "tp2": round(tp_levels[1], 6),
                    "chart": chart_file,
                }

                market_data = {
                    "price": price,
                    "trend_ok": (side == "LONG" and trend_main == "UP") or (side == "SHORT" and trend_main == "DOWN"),
                    "rsi_rebound": rsi_rebound_long if side == "LONG" else rsi_rebound_short,
                    "volume_spike": volume_spike_ok,
                    "market_structure": structure,
                    "candle_pattern_ok": pattern_ok,
                    "stop_distance": stop_distance,
                    "atr": float(atr[-1]),
                    "risk_reward": risk_reward,
                    "volatility_score": volatility_score,
                    "volatility_state": volatility_state,
                    "momentum_score": momentum,
                    "spread": spread_pct,
                    "liquidity_blocked": liquidity_blocked,
                    "low_volatility": low_volatility,
                    "volume_change_pct": volume_change_pct,
                }

                save_signal(
                    sym,
                    price,
                    0.0,
                    risk_reward,
                    float(rsi[-1]),
                    float(macd[-1]) if len(macd) else 0.0,
                    float(macd_signal[-1]) if len(macd_signal) else 0.0,
                    vol_ratio,
                    now.strftime("%Y-%m-%d %H:%M:%S"),
                )
                last_alert_time[sym] = now

                if on_alert:
                    try:
                        await on_alert(payload, market_data)
                    except Exception as exc:
                        logger.error(f"on_alert failed for {sym}: {exc}")

            except Exception as exc:
                logger.error(f"{sym} scan error: {exc}")

        await asyncio.sleep(max(period_seconds, 15))
