"""
User Settings Manager
Manages per-user horizon and risk settings with JSON persistence.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Literal

from loguru import logger

SETTINGS_FILE = Path("telebot/user_settings.json")
SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)

HorizonType = Literal["short", "medium", "long"]
RiskType = Literal["low", "medium", "high"]


def _ensure_file() -> None:
    """Create settings file if it does not exist."""
    if not SETTINGS_FILE.exists():
        SETTINGS_FILE.write_text("{}")
        logger.info(f"Created {SETTINGS_FILE}")


def load_settings() -> Dict[int, Dict]:
    """Load all user settings from JSON."""
    _ensure_file()
    try:
        content = SETTINGS_FILE.read_text()
        data = json.loads(content) if content.strip() else {}
        return {int(k): v for k, v in data.items()}
    except Exception as exc:
        logger.error(f"Failed to load settings: {exc}")
        return {}


def save_settings(data: Dict[int, Dict]) -> bool:
    """Save all user settings to JSON."""
    try:
        _ensure_file()
        json_data = {str(k): v for k, v in data.items()}
        SETTINGS_FILE.write_text(json.dumps(json_data, indent=2))
        return True
    except Exception as exc:
        logger.error(f"Failed to save settings: {exc}")
        return False


def get_user_settings(user_id: int) -> Dict:
    """Get settings for a specific user. Returns defaults if not found."""
    settings = load_settings()
    if user_id in settings:
        return settings[user_id]
    return {
        "horizon": "medium",
        "risk": "medium",
    }


def update_user_settings(user_id: int, key: str, value) -> bool:
    """Update a single setting for a user."""
    if key not in ["horizon", "risk"]:
        logger.warning(f"Invalid setting key: {key}")
        return False

    settings = load_settings()
    if user_id not in settings:
        settings[user_id] = {
            "horizon": "medium",
            "risk": "medium",
        }

    if key == "horizon" and value not in ["short", "medium", "long"]:
        logger.warning(f"Invalid horizon: {value}")
        return False
    if key == "risk" and value not in ["low", "medium", "high"]:
        logger.warning(f"Invalid risk: {value}")
        return False

    settings[user_id][key] = value
    return save_settings(settings)


def get_horizon_name(horizon: HorizonType) -> str:
    names = {
        "short": "Short-term (Scalp)",
        "medium": "Mid-term (Swing)",
        "long": "Long-term (Trend)",
    }
    return names.get(horizon, horizon.upper())


def get_risk_name(risk: RiskType) -> str:
    names = {
        "low": "Low Risk",
        "medium": "Medium Risk",
        "high": "High Risk",
    }
    return names.get(risk, risk.upper())


def get_timeframes_for_horizon(horizon: HorizonType) -> list[str]:
    """Get list of timeframes for a given horizon."""
    timeframes = {
        "short": ["1m", "5m", "15m"],
        "medium": ["15m", "1h"],
        "long": ["1h", "4h", "1d"],
    }
    return timeframes.get(horizon, ["15m", "1h"])


if __name__ == "__main__":
    # Basic smoke test
    update_user_settings(123456789, "horizon", "long")
    update_user_settings(123456789, "risk", "high")
    settings = get_user_settings(123456789)
    print(settings)
