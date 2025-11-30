from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, Optional

_last_signal: Dict[str, datetime] = {}


def record_signal(symbol: str, ts: Optional[datetime] = None) -> None:
    _last_signal[symbol] = ts or datetime.now(timezone.utc)


def last_signal_time(symbol: str) -> Optional[datetime]:
    return _last_signal.get(symbol)


def hours_since_last_signal(symbol: str) -> Optional[float]:
    last = _last_signal.get(symbol)
    if not last:
        return None
    delta = datetime.now(timezone.utc) - last
    return delta.total_seconds() / 3600.0
