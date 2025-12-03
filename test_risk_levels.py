#!/usr/bin/env python3
"""
Test Script: Risk Seviyesi Nasıl Analiz Değiştiriyor?

Bu script, farklı risk seviyeleriyle aynı market verisi için
nasıl farklı sinyaller üretildiğini gösterir.
"""

from pumpbot.core.presets import MEDIUM_LOW, MEDIUM_MEDIUM, MEDIUM_HIGH
from pumpbot.core.signal_engine import SignalComponents, compute_score, passes_quality_gate


def test_risk_levels():
    """
    Aynı market verisi (components) ile 3 farklı risk seviyesini test et.
    """
    
    # Örnek market components (BTC/USDT analiz sonucu)
    components = SignalComponents(
        trend_strength=0.72,   # Moderate trend
        momentum=0.65,         # Decent momentum (RSI 65)
        volume_spike=1.4,      # Moderate volume spike
        volatility=0.25,       # Low volatility
        noise_level=0.20,      # Low noise
    )
    
    print("=" * 70)
    print("🧪 TEST: Risk Seviyesi = Analiz Modu Değişikliği")
    print("=" * 70)
    print()
    
    print("📊 Market Verisi (Sabit):")
    print(f"  Trend Strength:  {components.trend_strength:.2f}")
    print(f"  Momentum:        {components.momentum:.2f}")
    print(f"  Volume Spike:    {components.volume_spike:.2f}x")
    print(f"  Volatility:      {components.volatility:.2f}")
    print(f"  Noise Level:     {components.noise_level:.2f}")
    print()
    
    print("=" * 70)
    print("TEST 1: LOW RISK (MEDIUM/LOW)")
    print("=" * 70)
    
    preset_low = MEDIUM_LOW
    passes_low, reason_low = passes_quality_gate(components, preset_low)
    score_low = compute_score(components, preset_low) if passes_low else None
    
    print(f"Preset: {preset_low.description}")
    print()
    print("Quality Gates:")
    print(f"  ✓ Trend strength: {components.trend_strength:.2f} >= {preset_low.min_trend_strength}? ", end="")
    if components.trend_strength >= preset_low.min_trend_strength:
        print("✅ PASS")
    else:
        print(f"❌ FAIL - Trend çok zayıf")
    print(f"  ✓ Volume spike: {components.volume_spike:.2f}x >= {preset_low.min_volume_spike}x? ", end="")
    if components.volume_spike >= preset_low.min_volume_spike:
        print("✅ PASS")
    else:
        print(f"❌ FAIL - Volüm çok az")
    print(f"  ✓ Noise level: {components.noise_level:.2f} <= 0.8? ", end="")
    if components.noise_level <= 0.8:
        print("✅ PASS")
    else:
        print("❌ FAIL")
    print()
    print(f"Result: {passes_low}")
    if not passes_low:
        print(f"Reason: {reason_low}")
        print()
        print("⛔ SINYAL BLOKE EDILDI (Quality gates başarısız)")
    else:
        print(f"Score: {score_low:.1f}/100 ✅ SINYAL GÖNDERİLİYOR")
    print()
    print(f"Cooldown: {preset_low.cooldown_minutes} dakika (Tekrar sinyal için çok bekleyeceğiz)")
    print()
    
    print("=" * 70)
    print("TEST 2: MEDIUM RISK (MEDIUM/MEDIUM)")
    print("=" * 70)
    
    preset_med = MEDIUM_MEDIUM
    passes_med, reason_med = passes_quality_gate(components, preset_med)
    score_med = compute_score(components, preset_med) if passes_med else None
    
    print(f"Preset: {preset_med.description}")
    print()
    print("Quality Gates:")
    print(f"  ✓ Trend strength: {components.trend_strength:.2f} >= {preset_med.min_trend_strength}? ", end="")
    if components.trend_strength >= preset_med.min_trend_strength:
        print("✅ PASS")
    else:
        print("❌ FAIL")
    print(f"  ✓ Volume spike: {components.volume_spike:.2f}x >= {preset_med.min_volume_spike}x? ", end="")
    if components.volume_spike >= preset_med.min_volume_spike:
        print("✅ PASS")
    else:
        print("❌ FAIL")
    print(f"  ✓ Noise level: {components.noise_level:.2f} <= 0.8? ", end="")
    if components.noise_level <= 0.8:
        print("✅ PASS")
    else:
        print("❌ FAIL")
    print()
    print(f"Result: {passes_med}")
    if not passes_med:
        print(f"Reason: {reason_med}")
        print()
        print("⛔ SINYAL BLOKE EDILDI")
    else:
        print(f"Score: {score_med:.1f}/100 ✅ SINYAL GÖNDERİLİYOR")
    print()
    print(f"Cooldown: {preset_med.cooldown_minutes} dakika (Dengeli bekleme)")
    print()
    
    print("=" * 70)
    print("TEST 3: HIGH RISK (MEDIUM/HIGH)")
    print("=" * 70)
    
    preset_high = MEDIUM_HIGH
    passes_high, reason_high = passes_quality_gate(components, preset_high)
    score_high = compute_score(components, preset_high) if passes_high else None
    
    print(f"Preset: {preset_high.description}")
    print()
    print("Quality Gates:")
    print(f"  ✓ Trend strength: {components.trend_strength:.2f} >= {preset_high.min_trend_strength}? ", end="")
    if components.trend_strength >= preset_high.min_trend_strength:
        print("✅ PASS")
    else:
        print("❌ FAIL")
    print(f"  ✓ Volume spike: {components.volume_spike:.2f}x >= {preset_high.min_volume_spike}x? ", end="")
    if components.volume_spike >= preset_high.min_volume_spike:
        print("✅ PASS")
    else:
        print("❌ FAIL")
    print(f"  ✓ Noise level: {components.noise_level:.2f} <= 0.8? ", end="")
    if components.noise_level <= 0.8:
        print("✅ PASS")
    else:
        print("❌ FAIL")
    print()
    print(f"Result: {passes_high}")
    if not passes_high:
        print(f"Reason: {reason_high}")
        print()
        print("⛔ SINYAL BLOKE EDILDI")
    else:
        print(f"Score: {score_high:.1f}/100 ✅ SINYAL GÖNDERİLİYOR (HIZLI)")
    print()
    print(f"Cooldown: {preset_high.cooldown_minutes} dakika (Çok kısa, sık sinyal)")
    print()
    
    # Summary
    print("=" * 70)
    print("📊 ÖZET: Aynı Market Verisi, Farklı Sonuçlar")
    print("=" * 70)
    print()
    
    results = []
    if passes_low:
        results.append(f"LOW:    ✅ Sinyal ({score_low:.1f}), {preset_low.cooldown_minutes} min cooldown")
    else:
        results.append(f"LOW:    ❌ Bloke edildi ({reason_low})")
    
    if passes_med:
        results.append(f"MEDIUM: ✅ Sinyal ({score_med:.1f}), {preset_med.cooldown_minutes} min cooldown")
    else:
        results.append(f"MEDIUM: ❌ Bloke edildi")
    
    if passes_high:
        results.append(f"HIGH:   ✅ Sinyal ({score_high:.1f}), {preset_high.cooldown_minutes} min cooldown")
    else:
        results.append(f"HIGH:   ❌ Bloke edildi")
    
    for result in results:
        print(result)
    print()
    
    print("🎯 SONUÇ:")
    print("  Risk seviyesi değiştirmek = Farklı quality gates = Farklı sinyaller")
    print("  LOW  = Çok katı, az sinyal, yüksek başarı")
    print("  MED  = Dengeli, orta sinyal, orta başarı")
    print("  HIGH = Gevşek, çok sinyal, düşük başarı")
    print()


if __name__ == "__main__":
    test_risk_levels()
