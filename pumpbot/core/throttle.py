from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict

from loguru import logger

from pumpbot.core.debugger import debug_throttle

STATE_PATH = Path("signal_throttle.json")
_last_seen: Dict[str, datetime] = {}
DEFAULT_THROTTLE_MINUTES = int(os.getenv("THROTTLE_MINUTES", "5"))


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


def allow_signal(symbol: str, minutes: int | None = None) -> bool:
    """
    Returns True if enough time has passed since the last allowed signal for the symbol.
    Default cooldown can be configured via THROTTLE_MINUTES (env).
    """
    _load_state()
    minutes = minutes if minutes is not None else DEFAULT_THROTTLE_MINUTES
    cooldown = timedelta(minutes=minutes)
    now = datetime.now(timezone.utc)

    last = _last_seen.get(symbol)
    if last:
        next_allowed = last + cooldown
        if now < next_allowed:
            # Store as naive UTC for simpler logging
            debug_throttle(symbol, next_allowed.astimezone(timezone.utc).replace(tzinfo=None))
            return False

    _last_seen[symbol] = now
    _persist_state()
    logger.debug(f"[THROTTLE] {symbol} allowed. Cooldown set to {minutes} min.")
    return True
