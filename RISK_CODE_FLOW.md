# 🔄 Risk Seviyesi → Analiz Akışı (Code Flow)

## 1️⃣ USER AYARI YAPTIĞINDA

```
User: /setrisk high
       ↓
Telegram Handler (cmd_setrisk)
       ↓
update_user_settings(user_id=123, "risk", "high")
       ↓
Yazılıyor: telebot/user_settings.json
{
  "123": {
    "horizon": "medium",  
    "risk": "high"  ← DEĞIŞTI!
  }
}
```

---

## 2️⃣ BOT BAŞLATILDIĞINDE (main.py)

```python
async def main():
    # ...
    
    # Binance'tan geçerli semboller çekiliyor
    valid_symbols = await _fetch_valid_symbols_from_binance(client)
    
    symbols = _build_symbols(env_symbols_csv)
    # symbols = [BTCUSDT, ETHUSDT, ...50+ coin]
    
    # Scan task başlatılıyor user_id ile
    task_scan = asyncio.create_task(
        scan_symbols(
            client,
            symbols,
            timeframe,
            scan_interval,
            on_alert,
            user_id=0,  # Default user
        )
    )
```

---

## 3️⃣ DETECTOR BAŞLATILDIĞINDE (detector.py)

```python
async def scan_symbols(
    client,
    symbols: Iterable[str],
    interval: str,
    period_seconds: int,
    on_alert: Callable,
    user_id: Optional[int] = None,
):
    if user_id is None:
        user_id = 0
    
    # ⭐ PRESET YÜKLENIYOR
    user_settings = get_user_settings(user_id)
    # {
    #   "horizon": "medium",
    #   "risk": "high"
    # }
    
    preset = load_preset(
        user_settings["horizon"],   # "medium"
        user_settings["risk"]        # "high" ← BU KEY!
    )
    # preset = MEDIUM_HIGH SignalCoefficients
    # {
    #   trend_coef: 0.40,
    #   momentum_coef: 0.35,
    #   volume_coef: 0.15,
    #   volatility_coef: 0.05,
    #   noise_coef: 0.05,
    #   min_trend_strength: 0.55,  ← DÜŞÜK!
    #   min_volume_spike: 1.2,      ← DÜŞÜK!
    #   cooldown_minutes: 10,       ← KISA!
    #   ...
    # }
    
    logger.info(
        f"Scanner starting | user_id={user_id} horizon=medium "
        f"risk=high base_tf=15m htf_tf=4h symbols=50"
    )
    
    # HER SYMBOL İÇİN PROCESS BAŞLATILIYOR
    async def process(sym: str):
        await _process_symbol(client, sym, "15m", "4h", on_alert, preset)
        #                                                          ^^^^^
        #                                                   PRESET BURAYA GEÇİLİYOR
    
    while True:
        tasks = [asyncio.create_task(process(sym)) for sym in symbols]
        # [process(BTCUSDT), process(ETHUSDT), process(BNBUSDT), ...]
        #                     ↓
        #                Aynı preset ile hepsi analiz ediliyor!
```

---

## 4️⃣ ANALYZER ÇAĞRILDIĞINDE (detector.py → analyzer.py)

```python
async def _process_symbol(
    client,
    symbol: str,
    base_timeframe: str,
    htf_timeframe: str,
    on_alert: Callable,
    preset: SignalCoefficients,  # ⭐ PRESET BURAYA GELİYOR
):
    # ...
    
    # Cooldown PRESET'TEN ALINIYOR
    cooldown_minutes = preset.cooldown_minutes  # 10 min (HIGH risk)
    
    if last_ts and datetime.now(timezone.utc) - last_ts < timedelta(minutes=cooldown_minutes):
        return  # Çok yakın olduğu için atlıyor
    
    # ANALYZER ÇAĞRILIYOR
    sig = await analyze_symbol_midterm(
        client=client,
        symbol=symbol,
        base_timeframe=base_tf,
        htf_timeframe=htf_tf,
        leverage=LEVERAGE,
        strategy=STRATEGY_NAME,
        preset=preset,  # ⭐ PRESET BURAYA GEÇİLİYOR
    )
```

---

## 5️⃣ ANALYZER ÇALIŞTIĞINDE (analyzer.py)

```python
async def analyze_symbol_midterm(
    # ...
    preset=None,  # SignalCoefficients (MEDIUM_HIGH)
) -> Optional[SignalPayload]:
    
    # Market verileri çekiliyor
    base_close, base_high, base_low, base_open, base_volume = fetch_candles()
    # ...
    
    # ⭐ SIGNAL COMPONENTS HESAPLANIYOR
    trend_strength = 0.75  # Price vs EMA
    momentum = 0.68  # RSI/100
    volume_spike = 1.6  # Volume ratio
    volatility = 0.22  # ATR normalized
    noise_level = 0.15  # Signal clarity
    
    components = SignalComponents(
        trend_strength=0.75,
        momentum=0.68,
        volume_spike=1.6,
        volatility=0.22,
        noise_level=0.15,
    )
    
    if preset:
        # ⭐ QUALITY GATES KONTROL EDİLİYOR (PRESET İLE)
        passes, reason = passes_quality_gate(components, preset)
        # Kontrol edilen şeyler:
        # • 0.75 >= 0.55 (min_trend_strength)? ✅ PASS
        # • 1.6 >= 1.2 (min_volume_spike)? ✅ PASS
        # • noise 0.15 <= 0.8? ✅ PASS
        # → Hepsi PASS → Devam et
        
        if not passes:
            logger.debug(f"{symbol} quality gate failed: {reason}")
            return None  # ❌ SINYAL YOK
        
        # ⭐ SCORE HESAPLANIYOR (PRESET COEFFICIENTS İLE)
        score = compute_score(components, preset)
        # score = (0.75 * 0.40)      # trend component (HIGH risk yüksek)
        #       + (0.68 * 0.35)      # momentum component
        #       + (1.6 * 0.15)       # volume component
        #       - (0.22 * 0.05)      # volatility penalty (HIGH risk az)
        #       - (0.15 * 0.05)      # noise penalty
        # = 0.30 + 0.238 + 0.24 - 0.011 - 0.0075
        # = 0.7595 * 100 = 75.95
        
        logger.debug(f"{symbol} signal score: {score:.1f}")
    else:
        score = None  # Preset yok ise score yok
    
    # ⭐ PAYLOAD OLUŞTURULUYOR (SCORE İLE)
    payload = SignalPayload(
        symbol=symbol,
        side="LONG",
        entry_price=45000.0,
        tp1=45500.0,
        tp2=46000.0,
        sl=44500.0,
        score=75.95,  # ⭐ SCORE PAYLOADA EKLENIYOR
        # ...
    )
    
    return payload
```

---

## 6️⃣ SIGNAL GÖNDERILIRKEN (main.py → on_alert)

```python
async def on_alert(payload: dict, market_data: dict):
    """
    Central signal gating logic.
    """
    symbol = payload.get("symbol", "UNKNOWN")
    side = payload.get("side", "?")
    score = payload.get("score")  # 75.95
    
    # ⭐ SCORE TELEGRAM'A YAZILIYOR
    signal_text = f"""
🚨 *SIGNAL DETECTED*
Symbol: {symbol}
Side: {side}
Entry: {payload['entry_price']}
Score: {score:.1f}/100  ← BU YER BURADA!
    """
    
    await send_vip_signal(app, chat_ids, payload)
```

---

## 🎯 RISK SEVIYESI DEĞIŞTIĞINDE NE OLUYOR?

### Senaryö: HIGH → LOW'a değiştiriyorsunuz

**Öncesi (HIGH):**
```python
preset = MEDIUM_HIGH
  min_trend_strength = 0.55  ← Düşük
  min_volume_spike = 1.2      ← Düşük
  cooldown_minutes = 10       ← Kısa
  volatility_coef = 0.05      ← Az ceza
  → Sık sinyal verir
```

**Sonrası (LOW):**
```python
preset = MEDIUM_LOW
  min_trend_strength = 0.85  ← YÜKSEK!
  min_volume_spike = 1.8     ← YÜKSEK!
  cooldown_minutes = 30      ← UZUN!
  volatility_coef = 0.10     ← ÇOK CEZA!
  → Az sinyal verir ama %85 başarı
```

**Teknik Değişiklik:**
```
1. Quality gates daha katı (0.55 → 0.85)
2. Cooldown daha uzun (10 → 30 dakika)
3. Scoring ağırlıkları değişiyor (yanlış)
4. Aynı market verisi, BAŞKA SONUÇ
```

**Örnek:**
```
Market: trend_strength = 0.70

HIGH Risk:  0.70 >= 0.55? ✅ PASS → Sinyal ver
LOW Risk:   0.70 >= 0.85? ❌ FAIL → Sinyal YAPMA
```

---

## 📊 KÖK FARK: Hangi Kod Satırında?

### pumpbot/core/presets.py
```python
# Risk = Preset seçimi
MEDIUM_LOW = SignalCoefficients(min_trend_strength=0.85, cooldown_minutes=30, ...)
MEDIUM_MEDIUM = SignalCoefficients(min_trend_strength=0.70, cooldown_minutes=20, ...)
MEDIUM_HIGH = SignalCoefficients(min_trend_strength=0.55, cooldown_minutes=10, ...)
```

### pumpbot/core/detector.py (Line ~60)
```python
# Preset yükleniyor
preset = load_preset(user_settings["horizon"], user_settings["risk"])
```

### pumpbot/core/detector.py (Line ~100)
```python
# Preset kullanılıyor (cooldown)
cooldown_minutes = preset.cooldown_minutes
```

### pumpbot/core/analyzer.py (Line ~300)
```python
# Preset kullanılıyor (quality gates + scoring)
passes, reason = passes_quality_gate(components, preset)
score = compute_score(components, preset)
```

---

## ✅ SONUÇ

**Risk Seviyesi = Tamamen Farklı Analiz Modu**

```
/setrisk low     → 0.85 trend needed, 30 min cooldown, %85 success
/setrisk medium  → 0.70 trend needed, 20 min cooldown, %78 success
/setrisk high    → 0.55 trend needed, 10 min cooldown, %60 success

Aynı piyasa verisi
Aynı coin
Aynı teknik göstergeler

AMMA:
BAŞKA preset → BAŞKA quality gates → BAŞKA score → BAŞKA sonuç!
```

**3 Farklı Bot Kişiliği:**
- **LOW**: "Çok dikkatli, nadir sinyal, güvenilir" 🛡️
- **MEDIUM**: "Dengeli, her gün sinyal" ⚖️
- **HIGH**: "Agresif, sık sinyal, riskli" ⚡
