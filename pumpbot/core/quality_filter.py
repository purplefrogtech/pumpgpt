from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from typing import Dict

from loguru import logger

from pumpbot.core.debugger import debug_filter_reject

DB_PATH = Path("signals.db")

# Tunable thresholds (relaxed to avoid over-filtering)
MIN_RISK_REWARD = float(os.getenv("MIN_RISK_REWARD", "1.2"))
MIN_RSI = float(os.getenv("MIN_RSI", "30"))
MAX_RSI = float(os.getenv("MAX_RSI", "70"))
MIN_ATR_PCT = float(os.getenv("MIN_ATR_PCT", "0.00015"))  # 0.015%
MIN_VOLUME_RATIO = float(os.getenv("MIN_VOLUME_RATIO", "1.05"))  # light spike
MAX_SPREAD_PCT = float(os.getenv("MAX_SPREAD_PCT", "0.01"))  # 1%
MIN_SUCCESS_RATE = float(os.getenv("MIN_SUCCESS_RATE", "25"))


def get_recent_success_rate(limit: int = 30) -> float:
    """
    Calculates win rate of last 'limit' closed trades.
    """
    if not DB_PATH.exists():
        return 0.0
    try:
        con = sqlite3.connect(DB_PATH)
        cur = con.execute(
            "SELECT pnl_usd FROM trades WHERE status='CLOSED' ORDER BY id DESC LIMIT ?",
            (limit,),
        )
        rows = [r[0] for r in cur.fetchall() if r and r[0] is not None]
        con.close()
        if not rows:
            return 0.0
        wins = sum(1 for r in rows if r > 0)
        return wins / len(rows) * 100.0
    except Exception as exc:
        logger.warning(f"Success rate calculation failed: {exc}")
        return 0.0


def should_emit_signal(payload: Dict, market_data: Dict) -> bool:
    """
    Centralized quality gate. Returns False to block any outgoing signal.
    Uses relaxed but safer thresholds to avoid full shutdown of signals.
    """
    price = float(market_data.get("price") or payload.get("price") or 0.0)
    rsi_raw = payload.get("rsi") or market_data.get("rsi")
    rsi_val = float(rsi_raw) if rsi_raw is not None else None
    atr_val = float(market_data.get("atr") or 0.0)
    atr_pct = (atr_val / price) if price else 0.0
    risk_reward = float(market_data.get("risk_reward") or payload.get("risk_reward") or 0.0)
    volume_change_pct = float(market_data.get("volume_change_pct") or 0.0)
    spread_pct = float(market_data.get("spread") or 0.0)
    liquidity_blocked = bool(market_data.get("liquidity_blocked"))
    trend_ok = bool(market_data.get("trend_ok")) or bool(market_data.get("trend_neutral"))
    volume_spike = bool(market_data.get("volume_spike"))
    success_rate = market_data.get("success_rate")
    if success_rate is None:
        success_rate = get_recent_success_rate()
        market_data["success_rate"] = success_rate

    if price <= 0:
        debug_filter_reject("price", "Price missing or zero")
        return False

    if not trend_ok:
        debug_filter_reject("trend", "Trend misalignment")
        return False

    if rsi_val is not None and (rsi_val < MIN_RSI or rsi_val > MAX_RSI):
        debug_filter_reject("rsi", f"RSI {rsi_val:.1f} outside {MIN_RSI}-{MAX_RSI}")
        return False

    if risk_reward < MIN_RISK_REWARD:
        debug_filter_reject("risk_reward", f"R:R {risk_reward:.2f} below {MIN_RISK_REWARD}")
        return False

    if atr_pct < MIN_ATR_PCT:
        debug_filter_reject("atr", f"ATR {atr_pct:.4%} too low")
        return False

    if liquidity_blocked:
        debug_filter_reject("liquidity", "Recent liquidity cluster blocks entry")
        return False

    if spread_pct > MAX_SPREAD_PCT:
        debug_filter_reject("spread", f"Spread {spread_pct:.4f} above {MAX_SPREAD_PCT}")
        return False

    # Soft warnings (do not block)
    if not volume_spike:
        logger.debug(f"[WARN] Volume spike weak (change {volume_change_pct:.2f}%)")
    elif volume_change_pct < MIN_VOLUME_RATIO * 100 - 100:
        logger.debug(f"[WARN] Volume change {volume_change_pct:.2f}% below light spike target")

    if success_rate < MIN_SUCCESS_RATE:
        logger.debug(f"[WARN] Success rate {success_rate:.1f}% below {MIN_SUCCESS_RATE}% (informational)")

    logger.debug(
        f"[QUALITY] PASS | R:R={risk_reward:.2f} RSI={rsi_val:.1f} ATR={atr_pct:.3%} "
        f"Spread={spread_pct:.4f} VolChange={volume_change_pct:.2f}% SR={success_rate:.1f}%"
    )
    return True
