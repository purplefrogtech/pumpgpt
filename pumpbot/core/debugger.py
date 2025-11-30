from __future__ import annotations

import os
from datetime import datetime
from typing import Any, Iterable, Optional

from loguru import logger

# Logging detail level is controlled by DEBUG_LEVEL (INFO/DEBUG/TRACE).
# We keep the helper functions lightweight; the configured loguru level
# will decide what is actually emitted.


def _log_level() -> str:
    level = os.getenv("DEBUG_LEVEL", "").strip().upper()
    if level in {"TRACE", "DEBUG", "INFO"}:
        return level
    # Fallback: DEBUG_MODE=1 implies DEBUG
    return "DEBUG" if os.getenv("DEBUG_MODE", "0") == "1" else "INFO"


def debug_signal_decision(
    symbol: str,
    timeframe: str,
    candle_data: dict[str, Any],
    rsi: Optional[float],
    trend: str,
    atr_pct: Optional[float],
    volatility_label: str,
    volume_ratio: Optional[float],
    decision: str,
    reason: str,
) -> None:
    """
    Emit a structured log describing how a signal decision was made.
    """
    level = _log_level()
    close_price = candle_data.get("close")
    msg = (
        f"[DECISION] {symbol} @{timeframe} | close={close_price} "
        f"RSI={_fmt_float(rsi)} trend={trend} ATR%={_fmt_pct(atr_pct)} "
        f"volatility={volatility_label} vol_ratio={_fmt_float(volume_ratio)} "
        f"-> {decision.upper()} ({reason})"
    )
    logger.log(level, msg)


def debug_api_response(symbol: str, raw_binance_data: Iterable[Any]) -> None:
    """
    Log the size/preview of raw Binance data for diagnostics.
    """
    data_list = list(raw_binance_data)
    preview = data_list[:2]
    level = _log_level()
    logger.log(level, f"[API] {symbol} klines fetched: {len(data_list)} rows | preview={preview}")


def debug_filter_reject(filter_name: str, reason: str) -> None:
    logger.debug(f"[REJECT] {filter_name}: {reason}")


def debug_throttle(symbol: str, limited_until: datetime) -> None:
    remaining = (limited_until - datetime.utcnow()).total_seconds()
    remaining_min = max(0, remaining / 60)
    logger.debug(f"[THROTTLE] {symbol} blocked for {remaining_min:.1f} more minutes (until {limited_until.isoformat()} UTC)")


def _fmt_float(val: Optional[float]) -> str:
    if val is None:
        return "-"
    try:
        return f"{float(val):.3f}"
    except Exception:
        return str(val)


def _fmt_pct(val: Optional[float]) -> str:
    if val is None:
        return "-"
    try:
        return f"{float(val)*100:.2f}%"
    except Exception:
        return str(val)
