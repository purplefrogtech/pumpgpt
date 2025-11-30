# 🔧 PUMP•GPT v2.1 - Sinyal Optimizasyon Notları

## 📋 Yapılan Değişiklikler

### 1. 🔴 KRITIK FİKS: on_alert() Fonksiyonu
**Problem:** `scan_symbols` tarafından çağrılan `on_alert()` fonksiyonu sinyali **göndermiyordu**!
- Payload oluşturuluyordu
- Ancak hiçbir webhook/notifier tetiklenmiyor
- Quality filter kontrolü yapılıyor ama sonuç hiç döndürülmüyordu

**Çözüm:** `main.py` satırları 150-195 düzeltildi
- Proper error handling eklendi
- Quality filter + throttle kontrol sonuçları doğru döndürülüyor
- Detaylı loglama eklendi (her aşamada neden blok edildiyse görülüyor)
- SimEngine hatasında sinyal kütüphanesi başarısız sayılmıyor

---

### 2. 🟠 Quality Filter Esnetildi

#### Eski Thresholds (TOO STRICT):
```python
MIN_RISK_REWARD = 1.5
MIN_SUCCESS_RATE = 70.0%  # ❌ İlk sinyallerde 0%!
MIN_VOLATILITY_SCORE = 0.0008
MIN_MOMENTUM_SCORE = 0.15
MAX_SPREAD_PCT = 0.002
MIN_STOP_ATR_FACTOR = 0.6
```

#### Yeni Thresholds (OPTIMIZED):
```python
MIN_RISK_REWARD = 1.3  # 30% daha esnek
MIN_SUCCESS_RATE = 30%  # İlk sinyallerde sorun yok
MIN_VOLATILITY_SCORE = 0.0003  # 370% daha düşük
MIN_MOMENTUM_SCORE = 0.05  # 300% daha düşük
MAX_SPREAD_PCT = 0.005  # 150% daha yüksek (esnek)
MIN_STOP_ATR_FACTOR = 0.5  # Biraz daha yakın SL
```

#### Quality Filter Mantığı (Yeni):
- **MANDATORY**: Trend, RSI, Volume, Structure, Candle → BLOK EDERLER
- **WARNING**: Diğer koşullar → Loglama yapılır ama BLOK ETMEZ
- Success rate sadece bilgi amaçlı (ilk sinyallerde 0% olabileceğinden)

---

### 3. 🟠 Throttle Esnetildi

**Eski:** 30 dakika → Aynı sembol çok az sinyal
**Yeni:** 5 dakika → Dengeli signal generation

```python
# throttle.py satır 16
def allow_signal(symbol: str, minutes: int = 5) -> bool:  # ← 5 dakika
```

**Faydası:** Aynı sembol 5 dakikada bir sinyal verebilir (30 dakikada 1 yerine 6x daha sık!)

---

### 4. 🟠 Volume Spike Ratio Esnetildi

**Eski:** 1.5x (50% spike gerekli)
**Yeni:** 1.3x (30% spike yeterli)

```python
# detector.py satırı 23
VOLUME_SPIKE_RATIO = 1.3  # 20% daha düşük
```

---

### 5. 📊 scan_symbols() Loglama Geliştirildi

**Eklenen Loglar:**
```
🔍 Mid-term scan starting | interval=15m, htf=30m | symbols=[...]
=== Scan #1 started ===
✅ LONG candidate | trend=UP/UP | struct=HH-HL | rsi_reb=✓
🎯 BTCUSDT LONG CANDIDATE | R:R 2.15 | ATR ⚡ Yüksek | Vol 1.8x | RSI 52.3
📢 SIGNAL #1 SENT: BTCUSDT LONG
```

**Avantajlar:**
- Her sembol için neden blok edildiyse görülüyor
- Sinyal sayıldığını görebilirsin
- Filtrelemenin hangi aşamasında takıldığını bilirsin

---

### 6. 🔧 scan_symbols() Basitleştirildi

**Removed Redundant Checks:**
- Quality filter'da ZATEN kontrol edilen koşullar detector'dan kaldırıldı
- Detector: Sadece temel trend/RSI/volume/pattern kontrol
- Quality filter: Detaylı volatility/momentum/spread/liquidity kontrol

**Sonuç:** Daha hızlı ve temiz kod flow

---

## 🎯 Beklenen Sonuçlar

### Sinyal Sıklığı
- **Eski:** Yılda 2-3 sinyal (aşırı az)
- **Yeni:** Haftalık 2-5 sinyal (gerçekçi orta vadeli strateji)

### Signal Quality
- Spam yok (mandatory filtreleme hala var)
- Çöp sinyal yok (trend/RSI/volume kontrol var)
- Dengeli risk/reward (1.3 minimum)

### Simulator Integration
- Her sinyal otomatik işlem açar
- P&L takibi yapılır
- Success rate arttıkça filtreleme sıkılaştırılabilir

---

## 🔍 Monitoring Checklist

Bot başladığında izlemen gereken şeyler:

```bash
✅ "🔍 Mid-term scan starting" → Scanner başladı
✅ "=== Scan #N started ===" → N. tarama başladı
⚠️  "❌ Quality: ..." → Sinyal blok edildiyse neden olduğu yazılı
✅ "🎯 SYMBOL LONG CANDIDATE" → İyi aday bulundu
✅ "📢 SIGNAL #N SENT: SYMBOL" → Sinyal gönderildi
✅ "Trade opened in simulator" → Simulator'da işlem açıldı
```

---

## 🔧 Fine-tuning Kılavuzu

Eğer hala çok az sinyal alıyorsan:

### 1. MIN_VOLATILITY_SCORE'u daha düşür
```python
MIN_VOLATILITY_SCORE = 0.0001  # (şu anki: 0.0003)
```

### 2. MIN_MOMENTUM_SCORE'u daha düşür
```python
MIN_MOMENTUM_SCORE = 0.01  # (şu anki: 0.05)
```

### 3. MIN_RISK_REWARD'u daha düşür (riski artırır!)
```python
MIN_RISK_REWARD = 1.1  # (şu anki: 1.3)
```

### 4. Throttle'ı daha da kıs
```python
def allow_signal(symbol: str, minutes: int = 2) -> bool:  # (şu anki: 5)
```

---

## 📝 Kod Değişiklik Özeti

| Dosya | Değişiklik | Etki |
|-------|-----------|------|
| `main.py` | on_alert() fonk. düzeltildi | CRITICAL - Sinyallar gönderilecek |
| `quality_filter.py` | Thresholds esnetildi + loglama | Daha esnek gate |
| `throttle.py` | 30min → 5min | 6x daha sık sinyal |
| `detector.py` | Loglama + basitleşme | Debug + performans |
| `quality_filter.py` | Zorunlu vs uyarı ayrımı | Bilgili kararlar |

---

## 🚀 Sonraki Adımlar

1. **.env** dosyanı güncelle (`.env.example` referans olarak kullan)
2. **Bot'u başlat** ve logları izle
3. **İlk sinyali alana kadar bekle** (genelde 15-30 dakika)
4. **Loglara bakarak** hangi sembolde sinyaller oluştuğunu gözlemle
5. **Fine-tuning** ihtiyacına göre thresholds ayarla
6. **Simulator P&L** izle ve stratejinin işe yarayıp yaramadığını kontrol et

---

## ⚠️ Önemli Notlar

- **Success Rate:** İlk sinyallerde 0% olabileceğinden, otomatik blok etmez
- **Throttle:** 5 dakika = aynı sembol için 5 dakikada 1 sinyal max
- **Quality Gate:** Trend + RSI + Volume + Structure + Candle zorunlu, diğer koşullar uyarı
- **Debug Mode:** `.env` dosyasında `DEBUG_MODE=1` yapınca çok daha detaylı log görürsün

---

**Sorular?** Loglara bak, detaylı mesajlar veriyor.
**Hala az sinyal?** Fine-tuning kılavuzunu takip et.
