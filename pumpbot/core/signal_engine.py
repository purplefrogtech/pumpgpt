"""
Signal Engine
Computes signal scores based on technical indicators and presets
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from loguru import logger

from pumpbot.core.presets import SignalCoefficients


@dataclass
class SignalComponents:
    """Individual signal components for scoring."""
    
    trend_strength: float  # 0-1, how strong is the trend
    momentum: float  # RSI-based, 0-1
    volume_spike: float  # volume ratio
    volatility: float  # ATR-based, 0-1 (higher = more volatile)
    noise_level: float  # 0-1, how much noise in signal


def compute_score(
    components: SignalComponents,
    coefficients: SignalCoefficients,
) -> float:
    """
    Compute overall signal score.
    
    score = (Trend_Strength * TREND_COEF)
          + (Momentum * MOM_COEF)
          + (Volume_Spike * VOL_COEF)
          - (Volatility_Risk * VOLAT_COEF)
          - (Noise_Level * NOISE_COEF)
    
    Returns:
        Float score (typically 0-100)
    """
    
    # Clamp components to 0-1 range
    trend = max(0.0, min(1.0, components.trend_strength))
    momentum = max(0.0, min(1.0, components.momentum))
    volatility = max(0.0, min(1.0, components.volatility))
    noise = max(0.0, min(1.0, components.noise_level))
    
    # Volume spike can be >1 (e.g., 1.5x normal)
    volume = components.volume_spike
    
    # Compute components
    trend_part = trend * coefficients.trend_coef * 100
    momentum_part = momentum * coefficients.momentum_coef * 100
    volume_part = min(volume / 2.0, 1.0) * coefficients.volume_coef * 100  # Normalize volume
    volatility_penalty = volatility * coefficients.volatility_coef * 100
    noise_penalty = noise * coefficients.noise_coef * 100
    
    # Final score
    score = (trend_part + momentum_part + volume_part) - (volatility_penalty + noise_penalty)
    
    # Clamp to 0-100
    score = max(0.0, min(100.0, score))
    
    return score


def passes_quality_gate(
    components: SignalComponents,
    coefficients: SignalCoefficients,
) -> tuple[bool, Optional[str]]:
    """
    Check if signal passes quality gates (thresholds).
    
    Returns:
        (passes: bool, reason: str if failed else None)
    """
    
    # Trend strength check
    if components.trend_strength < coefficients.min_trend_strength:
        return False, f"Trend too weak: {components.trend_strength:.2f} < {coefficients.min_trend_strength:.2f}"
    
    # Volume spike check
    if components.volume_spike < coefficients.min_volume_spike:
        return False, f"Volume spike too low: {components.volume_spike:.2f}x < {coefficients.min_volume_spike:.2f}x"
    
    # Volatility check (ATR-based)
    # Note: volatility is a risk metric, we're checking the raw ATR value elsewhere
    # This is more about whether volatility is reasonable
    if components.volatility > 0.9:  # Too volatile?
        # Some users might want high volatility for short-term trades
        # So we only warn, don't block
        logger.debug(f"High volatility: {components.volatility:.2f}")
    
    # Noise check
    if components.noise_level > 0.8:
        return False, f"Signal too noisy: {components.noise_level:.2f} > 0.8"
    
    return True, None


def explain_score(
    components: SignalComponents,
    coefficients: SignalCoefficients,
    score: float,
) -> str:
    """Generate human-readable explanation of score."""
    
    trend_part = components.trend_strength * coefficients.trend_coef * 100
    momentum_part = components.momentum * coefficients.momentum_coef * 100
    volume_part = (components.volume_spike / 2.0) * coefficients.volume_coef * 100
    volatility_penalty = components.volatility * coefficients.volatility_coef * 100
    noise_penalty = components.noise_level * coefficients.noise_coef * 100
    
    explanation = (
        f"📊 Signal Score: {score:.1f}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"✅ Positives:\n"
        f"  • Trend: {trend_part:.1f} (str: {components.trend_strength:.2f})\n"
        f"  • Momentum: {momentum_part:.1f} (RSI: {components.momentum:.2f})\n"
        f"  • Volume: {volume_part:.1f} (spike: {components.volume_spike:.2f}x)\n"
        f"\n❌ Penalties:\n"
        f"  • Volatility risk: -{volatility_penalty:.1f} (ATR: {components.volatility:.2f})\n"
        f"  • Noise level: -{noise_penalty:.1f} (noise: {components.noise_level:.2f})\n"
    )
    
    return explanation


if __name__ == "__main__":
    # Test
    from pumpbot.core.presets import MEDIUM_MEDIUM, MEDIUM_LOW, SHORT_HIGH
    
    print("Testing signal engine...\n")
    
    # Test case 1: Strong signal
    components = SignalComponents(
        trend_strength=0.85,
        momentum=0.75,
        volume_spike=1.8,
        volatility=0.3,
        noise_level=0.1,
    )
    
    score = compute_score(components, MEDIUM_MEDIUM)
    passes, reason = passes_quality_gate(components, MEDIUM_MEDIUM)
    
    print("Test 1: Strong signal (Medium/Medium preset)")
    print(f"Score: {score:.1f}")
    print(f"Passes: {passes}")
    print(explain_score(components, MEDIUM_MEDIUM, score))
    
    # Test case 2: Weak trend
    components2 = SignalComponents(
        trend_strength=0.45,
        momentum=0.65,
        volume_spike=1.5,
        volatility=0.2,
        noise_level=0.05,
    )
    
    score2 = compute_score(components2, MEDIUM_LOW)
    passes2, reason2 = passes_quality_gate(components2, MEDIUM_LOW)
    
    print("\nTest 2: Weak trend (Medium/Low preset)")
    print(f"Score: {score2:.1f}")
    print(f"Passes: {passes2} (reason: {reason2})")
