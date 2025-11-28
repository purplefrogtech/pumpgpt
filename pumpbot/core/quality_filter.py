from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Dict, Optional

from loguru import logger

DB_PATH = Path("signals.db")
MIN_RISK_REWARD = 1.5
MIN_SUCCESS_RATE = 70.0
MIN_VOLATILITY_SCORE = 0.0008  # ~0.08% ATR/price
MIN_MOMENTUM_SCORE = 0.15
MAX_SPREAD_PCT = 0.002  # 0.2%
MIN_STOP_ATR_FACTOR = 0.6


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
    """
    price = float(payload.get("price") or market_data.get("price", 0) or 0)
    trend_ok = bool(market_data.get("trend_ok"))
    rsi_rebound = bool(market_data.get("rsi_rebound"))
    volume_spike = bool(market_data.get("volume_spike"))
    market_structure = market_data.get("market_structure", "CHOP")
    candle_ok = bool(market_data.get("candle_pattern_ok"))
    stop_distance = float(market_data.get("stop_distance") or 0.0)
    atr_val = float(market_data.get("atr") or 0.0)
    risk_reward = float(market_data.get("risk_reward") or 0.0)
    volatility_score = float(market_data.get("volatility_score") or 0.0)
    momentum_score = float(market_data.get("momentum_score") or 0.0)
    spread_pct = float(market_data.get("spread") or 0.0)
    liquidity_blocked = bool(market_data.get("liquidity_blocked"))
    low_volatility = bool(market_data.get("low_volatility"))

    success_rate = market_data.get("success_rate")
    if success_rate is None:
        success_rate = get_recent_success_rate()
        market_data["success_rate"] = success_rate

    if not trend_ok:
        logger.debug("Quality filter: trend misalignment.")
        return False
    if not rsi_rebound:
        logger.debug("Quality filter: RSI rebound missing.")
        return False
    if not volume_spike:
        logger.debug("Quality filter: volume spike missing.")
        return False
    if market_structure == "CHOP":
        logger.debug("Quality filter: market structure is chop.")
        return False
    if not candle_ok:
        logger.debug("Quality filter: candle confirmation missing.")
        return False
    if atr_val > 0 and stop_distance < atr_val * MIN_STOP_ATR_FACTOR:
        logger.debug("Quality filter: stop distance too small.")
        return False
    if risk_reward < MIN_RISK_REWARD:
        logger.debug("Quality filter: insufficient risk/reward.")
        return False
    if liquidity_blocked:
        logger.debug("Quality filter: liquidity cluster opposite side.")
        return False
    if low_volatility:
        logger.debug("Quality filter: low volatility regime.")
        return False
    if volatility_score < MIN_VOLATILITY_SCORE:
        logger.debug("Quality filter: volatility score below threshold.")
        return False
    if momentum_score < MIN_MOMENTUM_SCORE:
        logger.debug("Quality filter: momentum too weak.")
        return False
    if spread_pct > MAX_SPREAD_PCT:
        logger.debug("Quality filter: spread too wide.")
        return False
    if success_rate < MIN_SUCCESS_RATE:
        logger.debug("Quality filter: historical success rate too low.")
        return False

    return True
