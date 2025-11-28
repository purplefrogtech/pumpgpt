from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict

from loguru import logger

STATE_PATH = Path("signal_throttle.json")
_last_seen: Dict[str, datetime] = {}


def _load_state() -> None:
    if _last_seen or not STATE_PATH.exists():
        return
    try:
        data = json.loads(STATE_PATH.read_text())
        for sym, ts in data.items():
            _last_seen[sym] = datetime.fromisoformat(ts)
    except Exception as exc:
        logger.warning(f"Throttle state could not be loaded: {exc}")


def _persist_state() -> None:
    try:
        serializable = {k: v.isoformat() for k, v in _last_seen.items()}
        STATE_PATH.write_text(json.dumps(serializable))
    except Exception as exc:
        logger.warning(f"Throttle state could not be saved: {exc}")


def allow_signal(symbol: str, minutes: int = 30) -> bool:
    """
    Returns True if enough time has passed since the last allowed signal for symbol.
    """
    _load_state()
    now = datetime.now(timezone.utc)
    last = _last_seen.get(symbol)
    if last and now - last < timedelta(minutes=minutes):
        remaining = timedelta(minutes=minutes) - (now - last)
        logger.info(f"Throttle block for {symbol}: wait {remaining}.")
        return False

    _last_seen[symbol] = now
    _persist_state()
    return True
