#!/usr/bin/env python3
"""
DEBUG TEST: Why is bot not sending signals?

This script simulates what happens inside the detector/analyzer
to identify where signals are being blocked.
"""

import asyncio
import sys
sys.path.insert(0, '/Users/Purplefrog/Desktop/Codes/pumpgpt')

from binance import AsyncClient
from loguru import logger

# Configure logging to see debug messages
logger.remove()
logger.add(lambda m: print(m, end=""), level="DEBUG")

from pumpbot.core.analyzer import analyze_symbol_midterm
from pumpbot.core.presets import load_for
from pumpbot.telebot.user_settings import get_user_settings


async def test_signal_generation():
    """Test if a symbol can generate a signal."""
    
    # Setup
    api_key = input("Binance API Key: ").strip()
    api_secret = input("Binance API Secret: ").strip()
    symbol = input("Symbol to test (e.g., BTCUSDT): ").strip().upper()
    
    if not api_key or not api_secret or not symbol:
        print("Missing inputs!")
        return
    
    # Client
    client = await AsyncClient.create(api_key=api_key, api_secret=api_secret)
    
    # User settings
    user_settings = get_user_settings(0)
    preset = load_for(user_settings["horizon"], user_settings["risk"])
    
    print(f"\n{'='*70}")
    print(f"Testing Symbol: {symbol}")
    print(f"User 0: {user_settings['horizon']} / {user_settings['risk']}")
    print(f"Preset: {preset.description}")
    print(f"{'='*70}\n")
    
    # Test analyzer
    print("[1] Fetching market data...")
    sig = await analyze_symbol_midterm(
        client=client,
        symbol=symbol,
        base_timeframe="15m",
        htf_timeframe="1h",
        leverage=10,
        strategy="TEST",
        preset=preset,
    )
    
    if sig is None:
        print("\n❌ NO SIGNAL GENERATED (Signal is None)")
        print("\nPossible reasons:")
        print("  1. HTF trend not detected (consolidation?)")
        print("  2. Quality gates failed (trend too weak, volume too low)")
        print("  3. Chart generation failed")
        print("\nCheck DEBUG logs above for details.")
    else:
        print(f"\n✅ SIGNAL GENERATED!")
        print(f"  Symbol: {sig.symbol}")
        print(f"  Side: {sig.side}")
        print(f"  Entry: {sig.entry}")
        print(f"  Score: {sig.score}")
        print(f"  Chart: {sig.chart_path}")
    
    await client.close_connection()


if __name__ == "__main__":
    asyncio.run(test_signal_generation())
