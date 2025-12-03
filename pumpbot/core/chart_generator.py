"""
OHLC chart generator using matplotlib.
Stores charts in ./charts directory with timestamp.
"""

from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Tuple

from loguru import logger

try:
    import matplotlib
    matplotlib.use('Agg')  # Non-GUI backend
    import matplotlib.pyplot as plt
    import matplotlib.patches as mpatches
    from matplotlib.patches import Rectangle
except ImportError:
    logger.error("matplotlib not installed. Install with: pip install matplotlib")
    plt = None


CHARTS_DIR = Path("charts")


def ensure_charts_dir() -> None:
    """Create ./charts directory if it doesn't exist."""
    CHARTS_DIR.mkdir(exist_ok=True)


def generate_chart(
    symbol: str,
    closes: List[float],
    highs: List[float],
    lows: List[float],
    opens: List[float],
    volumes: Optional[List[float]] = None,
    ema20: Optional[List[float]] = None,
    ema50: Optional[List[float]] = None,
    entry_price: Optional[float] = None,
    tp1: Optional[float] = None,
    tp2: Optional[float] = None,
    sl: Optional[float] = None,
    signal_side: Optional[str] = None,  # "LONG" or "SHORT"
) -> Optional[str]:
    """
    Generate OHLC candle chart with optional EMAs and signal levels.
    
    Args:
        symbol: Trading pair (e.g., "BTCUSDT")
        closes: List of closing prices
        highs: List of high prices
        lows: List of low prices
        opens: List of opening prices
        volumes: Optional list of volumes
        ema20: Optional EMA20 line
        ema50: Optional EMA50 line
        entry_price: Entry level to mark on chart
        tp1: First take-profit level
        tp2: Second take-profit level
        sl: Stop-loss level
        signal_side: "LONG" or "SHORT" to color entry accordingly
    
    Returns:
        Path to saved chart file, or None if generation failed
    """
    if plt is None:
        logger.error("matplotlib not available for chart generation")
        return None
    
    if not closes or not highs or not lows or not opens:
        logger.warning(f"{symbol}: Cannot generate chart - missing OHLC data")
        return None
    
    if len(closes) != len(highs) or len(closes) != len(lows) or len(closes) != len(opens):
        logger.warning(f"{symbol}: OHLC length mismatch")
        return None
    
    try:
        ensure_charts_dir()
        
        # Convert all inputs to float to avoid string comparison errors
        try:
            closes = [float(x) for x in closes]
            highs = [float(x) for x in highs]
            lows = [float(x) for x in lows]
            opens = [float(x) for x in opens]
            if volumes:
                volumes = [float(x) for x in volumes]
            if ema20:
                ema20 = [float(x) for x in ema20]
            if ema50:
                ema50 = [float(x) for x in ema50]
        except (ValueError, TypeError) as cast_exc:
            logger.warning(f"{symbol}: Could not convert data to float: {cast_exc}")
            return None
        
        # Use last 50 candles for visibility
        lookback = min(50, len(closes))
        x = list(range(lookback))
        closes_vis = closes[-lookback:]
        highs_vis = highs[-lookback:]
        lows_vis = lows[-lookback:]
        opens_vis = opens[-lookback:]
        
        ema20_vis = ema20[-lookback:] if ema20 and len(ema20) >= lookback else None
        ema50_vis = ema50[-lookback:] if ema50 and len(ema50) >= lookback else None
        
        # Create figure with subplots
        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 8), gridspec_kw={'height_ratios': [3, 1]})
        fig.suptitle(f'{symbol} OHLC Chart', fontsize=14, fontweight='bold')
        
        # --- Price chart ---
        candle_width = 0.6
        wick_width = 0.1
        
        for i in x:
            o, h, low, c = opens_vis[i], highs_vis[i], lows_vis[i], closes_vis[i]
            color = '#00aa00' if c >= o else '#ff0000'  # Green for up, red for down
            
            # Wick (high-low line)
            ax1.plot([i, i], [low, h], color=color, linewidth=wick_width)
            
            # Body (open-close rectangle)
            body_height = abs(c - o)
            body_bottom = min(o, c)
            ax1.add_patch(Rectangle((i - candle_width/2, body_bottom), candle_width, body_height,
                                    facecolor=color, edgecolor=color, linewidth=0.5))
        
        # EMAs
        if ema20_vis:
            ax1.plot(x, ema20_vis, label='EMA20', color='blue', linewidth=1.5, alpha=0.7)
        if ema50_vis:
            ax1.plot(x, ema50_vis, label='EMA50', color='orange', linewidth=1.5, alpha=0.7)
        
        # Signal levels
        if entry_price is not None:
            entry_color = '#00aa00' if signal_side == 'LONG' else '#ff0000'
            entry_label = f'Entry ({entry_price:.4f})'
            ax1.axhline(y=entry_price, color=entry_color, linestyle='--', linewidth=1.5, label=entry_label, alpha=0.8)
        
        if tp1 is not None:
            ax1.axhline(y=tp1, color='#0088ff', linestyle='--', linewidth=1, label=f'TP1 ({tp1:.4f})', alpha=0.6)
        
        if tp2 is not None:
            ax1.axhline(y=tp2, color='#00ccff', linestyle='--', linewidth=1, label=f'TP2 ({tp2:.4f})', alpha=0.6)
        
        if sl is not None:
            ax1.axhline(y=sl, color='#ff6600', linestyle='--', linewidth=1, label=f'SL ({sl:.4f})', alpha=0.6)
        
        ax1.set_ylabel('Price (USDT)', fontsize=10)
        ax1.legend(loc='upper left', fontsize=8)
        ax1.grid(True, alpha=0.3)
        ax1.set_xlim(left=0, right=len(x)-1)
        
        # --- Volume chart ---
        volumes_vis = volumes[-lookback:] if volumes else [0] * lookback
        vol_colors = ['#00aa0055' if closes_vis[i] >= opens_vis[i] else '#ff000055' for i in range(len(closes_vis))]
        ax2.bar(x, volumes_vis, color=vol_colors, width=0.8)
        ax2.set_ylabel('Volume', fontsize=10)
        ax2.grid(True, alpha=0.3)
        ax2.set_xlim(left=0, right=len(x)-1)
        
        plt.tight_layout()
        
        # Save with timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"chart_{symbol}_{timestamp}.png"
        filepath = CHARTS_DIR / filename
        
        plt.savefig(filepath, dpi=100, bbox_inches='tight')
        plt.close(fig)
        
        logger.info(f"Chart saved: {filepath}")
        return str(filepath)
        
    except Exception as exc:
        logger.error(f"Chart generation failed for {symbol}: {exc}")
        return None
