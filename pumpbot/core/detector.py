from __future__ import annotations

import asyncio
import os
from datetime import datetime, timedelta, timezone
from typing import Callable, Dict, Iterable, Optional

from loguru import logger

from pumpbot.core.analyzer import SignalPayload, analyze_symbol_midterm
from pumpbot.core.state import last_signal_time

ALLOWED_INTERVALS = {"15m", "30m", "1h"}
BASE_TIMEFRAME = os.getenv("TIMEFRAME", "15m")
HTF_TIMEFRAME = os.getenv("HTF_TIMEFRAME", "1h")
SCAN_CONCURRENCY = int(os.getenv("SCAN_CONCURRENCY", "3"))
SYMBOL_INTERVAL_MINUTES = int(os.getenv("SYMBOL_INTERVAL_MINUTES", "30"))  # min gap per symbol inside scanner
LEVERAGE = int(os.getenv("DEFAULT_LEVERAGE", "10"))
STRATEGY_NAME = os.getenv("STRATEGY_NAME", "PUMP-GPT Midterm")


def normalize_interval(interval: str) -> str:
    if not interval:
        return "15m"
    interval = interval.lower()
    if interval not in ALLOWED_INTERVALS:
        logger.warning(f"Interval {interval} not allowed. Falling back to 15m.")
        return "15m"
    return interval


async def scan_symbols(client, symbols: Iterable[str], interval: str, period_seconds: int, on_alert: Callable):
    """
    Mid-term scanner: leverages analyze_symbol_midterm for each symbol.
    """
    base_tf = normalize_interval(interval or BASE_TIMEFRAME)
    htf_tf = normalize_interval(HTF_TIMEFRAME)

    symbols_list = list(symbols)
    logger.info(f"Scanner starting | base_tf={base_tf} htf_tf={htf_tf} symbols={len(symbols_list)}")

    semaphore = asyncio.Semaphore(max(1, SCAN_CONCURRENCY))

    async def process(sym: str):
        async with semaphore:
            await _process_symbol(client, sym, base_tf, htf_tf, on_alert)

    while True:
        loop_start = datetime.now(timezone.utc)
        tasks = [asyncio.create_task(process(sym)) for sym in symbols_list]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for sym, res in zip(symbols_list, results):
            if isinstance(res, Exception):
                logger.error(f"{sym} scan task failed: {res}")
        elapsed = (datetime.now(timezone.utc) - loop_start).total_seconds()
        sleep_for = max(0.0, period_seconds - elapsed)
        logger.debug(f"Scan finished in {elapsed:.2f}s; sleeping {sleep_for:.2f}s")
        if sleep_for > 0:
            await asyncio.sleep(sleep_for)


async def _process_symbol(client, symbol: str, base_tf: str, htf_tf: str, on_alert: Callable):
    last_ts = last_signal_time(symbol)
    if last_ts and datetime.now(timezone.utc) - last_ts < timedelta(minutes=SYMBOL_INTERVAL_MINUTES):
        remaining = timedelta(minutes=SYMBOL_INTERVAL_MINUTES) - (datetime.now(timezone.utc) - last_ts)
        logger.debug(f"{symbol} skipped due to per-symbol cooldown ({remaining}).")
        return

    logger.info(f"Scanning symbol: {symbol} @{base_tf}")
    sig: Optional[SignalPayload] = await analyze_symbol_midterm(
        client=client,
        symbol=symbol,
        base_timeframe=base_tf,
        htf_timeframe=htf_tf,
        leverage=LEVERAGE,
        strategy=STRATEGY_NAME,
    )
    if not sig:
        logger.debug(f"{symbol} no midterm signal.")
        return

    payload = {
        "symbol": sig.symbol,
        "side": sig.side,
        "timeframe": sig.timeframe,
        "entry": sig.entry,
        "tp_levels": sig.tp_levels,
        "sl": sig.sl,
        "leverage": sig.leverage,
        "strategy": sig.strategy,
        "created_at": sig.created_at.isoformat(),
        "chart_path": sig.chart_path,
        "trend_label": sig.trend_label,
        "rsi": sig.rsi,
        "atr_pct": sig.atr_pct,
        "volume_change_pct": (sig.volume_spike_ratio - 1) * 100 if sig.volume_spike_ratio else None,
        "risk_reward": sig.risk_reward,
        "swing_high": sig.swing_high,
        "swing_low": sig.swing_low,
    }

    mid_price = sum(sig.entry) / len(sig.entry) if sig.entry else 0.0
    market_data: Dict = {
        "price": mid_price,
        "atr": (sig.atr_pct or 0.0) * mid_price if mid_price else 0.0,
        "risk_reward": sig.risk_reward or 0.0,
        "volume_spike": bool(sig.volume_spike_ratio and sig.volume_spike_ratio >= 1.0),
        "trend_ok": True,
        "candle_pattern_ok": True,
        "stop_distance": abs(mid_price - payload["sl"]) if payload["entry"] else 0.0,
        "spread": 0.0,
    }

    if on_alert:
        try:
            await on_alert(payload, market_data)
        except Exception as exc:
            logger.error(f"on_alert failed for {symbol}: {exc}")
