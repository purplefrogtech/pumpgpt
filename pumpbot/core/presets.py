"""
Signal Engine Presets
Coefficient tables for different horizon + risk combinations
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

HorizonType = Literal["short", "medium", "long"]
RiskType = Literal["low", "medium", "high"]


@dataclass
class SignalCoefficients:
    """Coefficients for signal scoring."""
    
    # Main signal components
    trend_coef: float  # Trend strength weight
    momentum_coef: float  # Momentum (RSI) weight
    volume_coef: float  # Volume spike weight
    
    # Risk/Noise reduction
    volatility_coef: float  # Volatility risk penalty
    noise_coef: float  # Noise level penalty
    
    # Thresholds
    min_trend_strength: float  # Minimum trend alignment (0-1)
    min_volume_spike: float  # Minimum volume ratio
    min_atr_pct: float  # Minimum ATR %
    max_spread_pct: float  # Maximum spread %
    min_rr_ratio: float  # Minimum risk:reward ratio
    
    # Signal frequency
    cooldown_minutes: int  # Minutes between signals for same symbol
    
    # Description
    description: str = ""


# ============== PRESETS BY HORIZON + RISK ==============

# SHORT HORIZON (Scalping)
SHORT_LOW = SignalCoefficients(
    trend_coef=0.30,
    momentum_coef=0.25,
    volume_coef=0.20,
    volatility_coef=0.15,
    noise_coef=0.10,
    min_trend_strength=0.75,
    min_volume_spike=2.0,
    min_atr_pct=0.002,
    max_spread_pct=0.003,
    min_rr_ratio=1.5,
    cooldown_minutes=15,
    description="SHORT/LOW: Very conservative scalp signals, high confidence",
)

SHORT_MEDIUM = SignalCoefficients(
    trend_coef=0.35,
    momentum_coef=0.30,
    volume_coef=0.20,
    volatility_coef=0.10,
    noise_coef=0.05,
    min_trend_strength=0.65,
    min_volume_spike=1.5,
    min_atr_pct=0.0015,
    max_spread_pct=0.005,
    min_rr_ratio=1.3,
    cooldown_minutes=10,
    description="SHORT/MEDIUM: Balanced scalp signals",
)

SHORT_HIGH = SignalCoefficients(
    trend_coef=0.40,
    momentum_coef=0.35,
    volume_coef=0.15,
    volatility_coef=0.05,
    noise_coef=0.05,
    min_trend_strength=0.50,
    min_volume_spike=1.2,
    min_atr_pct=0.0010,
    max_spread_pct=0.008,
    min_rr_ratio=1.2,
    cooldown_minutes=5,
    description="SHORT/HIGH: Aggressive scalp signals, high frequency",
)

# MEDIUM HORIZON (Swing Trading)
MEDIUM_LOW = SignalCoefficients(
    trend_coef=0.40,
    momentum_coef=0.25,
    volume_coef=0.20,
    volatility_coef=0.10,
    noise_coef=0.05,
    min_trend_strength=0.85,
    min_volume_spike=1.8,
    min_atr_pct=0.0015,
    max_spread_pct=0.003,
    min_rr_ratio=1.5,
    cooldown_minutes=30,
    description="MEDIUM/LOW: Conservative swing signals, high reliability",
)

MEDIUM_MEDIUM = SignalCoefficients(
    trend_coef=0.40,
    momentum_coef=0.30,
    volume_coef=0.20,
    volatility_coef=0.07,
    noise_coef=0.03,
    min_trend_strength=0.70,
    min_volume_spike=1.4,
    min_atr_pct=0.0012,
    max_spread_pct=0.005,
    min_rr_ratio=1.3,
    cooldown_minutes=20,
    description="MEDIUM/MEDIUM: Balanced swing signals (default)",
)

MEDIUM_HIGH = SignalCoefficients(
    trend_coef=0.40,
    momentum_coef=0.35,
    volume_coef=0.15,
    volatility_coef=0.05,
    noise_coef=0.05,
    min_trend_strength=0.55,
    min_volume_spike=1.2,
    min_atr_pct=0.0010,
    max_spread_pct=0.008,
    min_rr_ratio=1.2,
    cooldown_minutes=10,
    description="MEDIUM/HIGH: Aggressive swing signals",
)

# LONG HORIZON (Trend Following)
LONG_LOW = SignalCoefficients(
    trend_coef=0.50,
    momentum_coef=0.20,
    volume_coef=0.15,
    volatility_coef=0.10,
    noise_coef=0.05,
    min_trend_strength=0.90,
    min_volume_spike=1.5,
    min_atr_pct=0.0015,
    max_spread_pct=0.003,
    min_rr_ratio=1.5,
    cooldown_minutes=60,
    description="LONG/LOW: Very selective trend signals, highest confidence",
)

LONG_MEDIUM = SignalCoefficients(
    trend_coef=0.50,
    momentum_coef=0.25,
    volume_coef=0.15,
    volatility_coef=0.07,
    noise_coef=0.03,
    min_trend_strength=0.75,
    min_volume_spike=1.3,
    min_atr_pct=0.0012,
    max_spread_pct=0.005,
    min_rr_ratio=1.3,
    cooldown_minutes=45,
    description="LONG/MEDIUM: Balanced trend signals",
)

LONG_HIGH = SignalCoefficients(
    trend_coef=0.45,
    momentum_coef=0.30,
    volume_coef=0.15,
    volatility_coef=0.05,
    noise_coef=0.05,
    min_trend_strength=0.60,
    min_volume_spike=1.2,
    min_atr_pct=0.0010,
    max_spread_pct=0.008,
    min_rr_ratio=1.2,
    cooldown_minutes=30,
    description="LONG/HIGH: More frequent trend signals",
)


# ============== LOOKUP ==============

PRESET_MAP = {
    ("short", "low"): SHORT_LOW,
    ("short", "medium"): SHORT_MEDIUM,
    ("short", "high"): SHORT_HIGH,
    ("medium", "low"): MEDIUM_LOW,
    ("medium", "medium"): MEDIUM_MEDIUM,
    ("medium", "high"): MEDIUM_HIGH,
    ("long", "low"): LONG_LOW,
    ("long", "medium"): LONG_MEDIUM,
    ("long", "high"): LONG_HIGH,
}


def load_for(horizon: HorizonType, risk: RiskType) -> SignalCoefficients:
    """Load preset for given horizon + risk combination."""
    key = (horizon, risk)
    if key not in PRESET_MAP:
        # Fallback to medium/medium
        return MEDIUM_MEDIUM
    return PRESET_MAP[key]


def get_all_presets() -> dict[str, SignalCoefficients]:
    """Get all presets as a dictionary."""
    return PRESET_MAP.copy()


def describe_preset(horizon: HorizonType, risk: RiskType) -> str:
    """Get description of a preset."""
    preset = load_for(horizon, risk)
    return preset.description


if __name__ == "__main__":
    # Test
    print("Testing presets...")
    
    preset = load_for("medium", "low")
    print(f"\nMedium/Low Preset:")
    print(f"  Description: {preset.description}")
    print(f"  Trend coef: {preset.trend_coef}")
    print(f"  Min trend strength: {preset.min_trend_strength}")
    print(f"  Cooldown: {preset.cooldown_minutes} min")
    
    preset = load_for("short", "high")
    print(f"\nShort/High Preset:")
    print(f"  Description: {preset.description}")
    print(f"  Cooldown: {preset.cooldown_minutes} min")
    print(f"  Min trend strength: {preset.min_trend_strength}")
