from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timezone
from statistics import mean
from typing import List, Literal, Optional, Sequence

from binance import AsyncClient
from loguru import logger

from pumpbot.core.state import hours_since_last_signal, record_signal

Side = Literal["LONG", "SHORT"]


@dataclass
class SignalPayload:
    symbol: str
    side: Side
    timeframe: str  # "15m", "30m", "1h"
    entry: List[float]
    tp_levels: List[float]
    sl: float
    leverage: int
    strategy: str
    created_at: datetime
    chart_path: Optional[str] = None
    # optional context
    rsi: Optional[float] = None
    atr_pct: Optional[float] = None
    volume_spike_ratio: Optional[float] = None
    risk_reward: Optional[float] = None
    swing_high: Optional[float] = None
    swing_low: Optional[float] = None
    trend_label: Optional[str] = None


# --- math helpers (lightweight, no heavy deps) ---
def ema(series: Sequence[float], period: int) -> List[float]:
    if period <= 0:
        raise ValueError("period must be > 0")
    if not series:
        return []
    k = 2 / (period + 1)
    ema_vals: List[float] = []
    prev = series[0]
    ema_vals.append(prev)
    for price in series[1:]:
        prev = price * k + prev * (1 - k)
        ema_vals.append(prev)
    return ema_vals


def atr(highs: Sequence[float], lows: Sequence[float], closes: Sequence[float], period: int = 14) -> List[float]:
    if not (len(highs) == len(lows) == len(closes)):
        raise ValueError("High/Low/Close length mismatch")
    if len(highs) == 0:
        return []
    trs: List[float] = []
    prev_close = closes[0]
    for h, l, c in zip(highs, lows, closes):
        tr = max(h - l, abs(h - prev_close), abs(l - prev_close))
        trs.append(tr)
        prev_close = c
    return ema(trs, period)


def rolling_mean(series: Sequence[float], period: int) -> float:
    if not series or period <= 0:
        return 0.0
    window = series[-period:]
    return mean(window)


def rsi(series: Sequence[float], period: int = 14) -> Optional[float]:
    if len(series) < period + 1:
        return None
    gains = []
    losses = []
    for i in range(1, len(series)):
        delta = series[i] - series[i - 1]
        if delta >= 0:
            gains.append(delta)
            losses.append(0.0)
        else:
            gains.append(0.0)
            losses.append(-delta)
    avg_gain = mean(gains[-period:])
    avg_loss = mean(losses[-period:])
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def _pivot_high(highs: Sequence[float], idx: int) -> bool:
    return (
        idx >= 2
        and idx + 2 < len(highs)
        and highs[idx] > highs[idx - 1]
        and highs[idx] > highs[idx - 2]
        and highs[idx] > highs[idx + 1]
        and highs[idx] > highs[idx + 2]
    )


def _pivot_low(lows: Sequence[float], idx: int) -> bool:
    return (
        idx >= 2
        and idx + 2 < len(lows)
        and lows[idx] < lows[idx - 1]
        and lows[idx] < lows[idx - 2]
        and lows[idx] < lows[idx + 1]
        and lows[idx] < lows[idx + 2]
    )


def find_last_swing(highs: Sequence[float], lows: Sequence[float], lookback: int = 40) -> tuple[Optional[float], Optional[float]]:
    swing_high = None
    swing_low = None
    start = max(2, len(highs) - lookback)
    for i in range(len(highs) - 1, start - 1, -1):
        if swing_high is None and _pivot_high(highs, i):
            swing_high = highs[i]
        if swing_low is None and _pivot_low(lows, i):
            swing_low = lows[i]
        if swing_high is not None and swing_low is not None:
            break
    return swing_high, swing_low


async def _fetch_klines(client: AsyncClient, symbol: str, interval: str, limit: int) -> Optional[list]:
    try:
        return await client.get_klines(symbol=symbol, interval=interval, limit=limit)
    except Exception as exc:
        logger.error(f"{symbol} {interval} klines fetch failed: {exc}")
        return None


def _extract_lists(raw: list) -> tuple[List[float], List[float], List[float], List[float]]:
    closes: List[float] = []
    highs: List[float] = []
    lows: List[float] = []
    volumes: List[float] = []
    for row in raw:
        try:
            opens, high, low, close, vol = float(row[1]), float(row[2]), float(row[3]), float(row[4]), float(row[5])
        except (ValueError, TypeError, IndexError):
            continue
        closes.append(close)
        highs.append(high)
        lows.append(low)
        volumes.append(vol)
    return closes, highs, lows, volumes


def _format_trend_label(trend: str, htf: str) -> str:
    if trend == "UP":
        return f"HTF {htf} Uptrend"
    if trend == "DOWN":
        return f"HTF {htf} Downtrend"
    return f"HTF {htf} Sideways"


async def analyze_symbol_midterm(
    client: AsyncClient,
    symbol: str,
    base_timeframe: str = "15m",
    htf_timeframe: str = "1h",
    leverage: int = 10,
    strategy: str = "PUMP-GPT Midterm",
) -> Optional[SignalPayload]:
    base_tf = base_timeframe
    htf_tf = htf_timeframe
    base_raw = await _fetch_klines(client, symbol, base_tf, limit=150)
    htf_raw = await _fetch_klines(client, symbol, htf_tf, limit=150)

    if not base_raw or not htf_raw:
        return None

    base_close, base_high, base_low, base_vol = _extract_lists(base_raw)
    htf_close, htf_high, htf_low, htf_vol = _extract_lists(htf_raw)

    if len(base_close) < 60 or len(htf_close) < 60:
        logger.debug(f"{symbol} insufficient data base={len(base_close)} htf={len(htf_close)}")
        return None

    # HTF trend
    ema20_htf = ema(htf_close, 20)
    ema50_htf = ema(htf_close, 50)
    ema100_htf = ema(htf_close, 100)
    if len(ema20_htf) < 1 or len(ema100_htf) < 1:
        return None
    trend = None
    if htf_close[-1] > ema20_htf[-1] > ema50_htf[-1] > ema100_htf[-1]:
        trend = "UP"
    elif htf_close[-1] < ema20_htf[-1] < ema50_htf[-1] < ema100_htf[-1]:
        trend = "DOWN"
    else:
        return None

    # Base indicators
    ema20 = ema(base_close, 20)
    ema50 = ema(base_close, 50)
    atr_vals = atr(base_high, base_low, base_close, period=14)
    if len(ema20) < 1 or len(atr_vals) < 100:
        return None

    atr_now = atr_vals[-1]
    atr_mean = mean(atr_vals[-100:])

    hours_gap = hours_since_last_signal(symbol)
    adaptive = hours_gap is not None and hours_gap > 4
    atr_min_factor = 0.5 if adaptive else 0.6
    atr_max_factor = 2.0 if adaptive else 1.8
    if atr_now < atr_min_factor * atr_mean or atr_now > atr_max_factor * atr_mean:
        logger.debug(f"{symbol} ATR filter fail (now {atr_now:.6f}, mean {atr_mean:.6f}) adaptive={adaptive}")
        return None

    vol_ma = rolling_mean(base_vol, 20)
    vol_now = base_vol[-1] if base_vol else 0.0
    vol_ratio = (vol_now / vol_ma) if vol_ma else 0.0
    vol_threshold = 1.2 if adaptive else 1.5
    if vol_ratio < vol_threshold:
        logger.debug(f"{symbol} volume spike missing ratio={vol_ratio:.2f} need>={vol_threshold}")
        return None

    swing_high, swing_low = find_last_swing(base_high, base_low, lookback=40)
    close_now = base_close[-1]
    prev_close = base_close[-2]
    prev_high = base_high[-2]
    prev_low = base_low[-2]
    ema20_now = ema20[-1]
    ema50_now = ema50[-1]

    base_rsi = rsi(base_close, period=14)

    side: Optional[Side] = None
    sl = None
    if trend == "UP":
        # pullback into ema20-50 band then breakout
        pulled_back = min(base_close[-3:]) <= ema20_now or min(base_low[-3:]) <= ema20_now
        if close_now > ema20_now and close_now >= prev_high and pulled_back:
            side = "LONG"
            sl = (swing_low if swing_low is not None else close_now - 1.5 * atr_now) - 0.25 * atr_now
    elif trend == "DOWN":
        pulled_back = max(base_close[-3:]) >= ema20_now or max(base_high[-3:]) >= ema20_now
        if close_now < ema20_now and close_now <= prev_low and pulled_back:
            side = "SHORT"
            sl = (swing_high if swing_high is not None else close_now + 1.5 * atr_now) + 0.25 * atr_now

    if side is None or sl is None:
        return None

    entry_mid = close_now
    entry_range = [entry_mid - 0.25 * atr_now, entry_mid + 0.25 * atr_now]

    if side == "LONG":
        risk = entry_mid - sl
        tp1 = entry_mid + 1.5 * risk
        tp2 = entry_mid + 2.5 * risk
        tp3 = entry_mid + 3.5 * risk
    else:
        risk = sl - entry_mid
        tp1 = entry_mid - 1.5 * risk
        tp2 = entry_mid - 2.5 * risk
        tp3 = entry_mid - 3.5 * risk

    risk_reward = abs((tp1 - entry_mid) / risk) if risk != 0 else None
    payload = SignalPayload(
        symbol=symbol,
        side=side,
        timeframe=base_tf,
        entry=[round(entry_range[0], 6), round(entry_range[1], 6)],
        tp_levels=[round(tp1, 6), round(tp2, 6), round(tp3, 6)],
        sl=round(sl, 6),
        leverage=leverage,
        strategy=strategy,
        created_at=datetime.now(timezone.utc),
        chart_path=None,
        rsi=base_rsi,
        atr_pct=(atr_now / close_now) if close_now else None,
        volume_spike_ratio=vol_ratio,
        risk_reward=risk_reward,
        swing_high=swing_high,
        swing_low=swing_low,
        trend_label=_format_trend_label(trend, htf_tf),
    )

    # adaptive reset
    record_signal(symbol, payload.created_at)
    return payload
