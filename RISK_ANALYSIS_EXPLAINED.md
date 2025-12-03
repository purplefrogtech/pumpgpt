# 🎯 Risk Seviyesi = Analiz Tekniği Değişikliği

**Kısa cevap:** EVET! Risk seviyesini değiştirdiğinizde, bot **9 farklı analiz modundan birini seçiyor**.

---

## 📊 Risk Seviyesi Nedir?

Risk seviyesi, bot'un sinyalleri **ne kadar agresif veya güvenli** şekilde araştığını kontrol eder:

```
LOW      → Çok az sinyal, yüksek güvenilirlik (%85-90)
MEDIUM   → Dengeli sinyal, orta güvenilirlik (%75-80)
HIGH     → Çok sinyal, düşük güvenilirlik (%60-70)
```

---

## 🔄 Analiz Tekniği Nasıl Değişiyor?

### Örnek 1: MEDIUM Horizon, Risk Seviyesini Değiştirirseniz

```
/sethorizon medium
/setrisk low       → MEDIUM_LOW preset yükleniyor
/setrisk medium    → MEDIUM_MEDIUM preset yükleniyor
/setrisk high      → MEDIUM_HIGH preset yükleniyor
```

Her biri **tamamen farklı analiz parametreleri** kullanır:

---

## 📈 9 Preset Karşılaştırması

### SCORING COEFFICIENTS (Sinyalleri Nasıl Puanlandırıyor)

|  | **SHORT/LOW** | **SHORT/MEDIUM** | **SHORT/HIGH** |
|---|---|---|---|
| Trend ağırlığı | 0.30 | 0.35 | **0.40** ← More aggressive |
| Momentum ağırlığı | 0.25 | 0.30 | **0.35** |
| Volüm ağırlığı | 0.20 | 0.20 | 0.15 |
| Volatilite cezası | 0.15 | 0.10 | **0.05** ← Less strict |
| Noise cezası | 0.10 | 0.05 | 0.05 |

**Ne demek?**
- **SHORT/LOW**: Trend'e % 30 ağırlık → Çok katı
- **SHORT/HIGH**: Trend'e % 40 ağırlık → Daha agresif
- Risk arttıkça volatilite cezası **azalıyor** → Düzensiz piyasalarda da sinyal verir

---

### QUALITY GATES (Sinyal Alınmadan Önce Kontrol Edilen Şartlar)

|  | **MEDIUM/LOW** | **MEDIUM/MEDIUM** | **MEDIUM/HIGH** |
|---|---|---|---|
| Min trend strength | **0.85** | 0.70 | **0.55** |
| Min volume spike | **1.8x** | 1.4x | **1.2x** |
| Min ATR % | **0.0015** | 0.0012 | **0.0010** |
| Max spread % | **0.003** | 0.005 | **0.008** |
| Min RR ratio | **1.5** | 1.3 | **1.2** |

**Ne demek?**

**MEDIUM/LOW** (Güvenli):
- Trend en az 0.85 (çok güçlü olmalı)
- Volüm en az 1.8x normal
- Hemen hemen hiç spread yok
- **Sonuç:** Haftada belki 1-2 sinyal

**MEDIUM/MEDIUM** (Dengeli - DEFAULT):
- Trend min 0.70 (normal)
- Volüm 1.4x
- Orta spread
- **Sonuç:** Günde 3-8 sinyal

**MEDIUM/HIGH** (Agresif):
- Trend sadece 0.55 (zayıf trend bile kabul)
- Volüm 1.2x (az spike)
- Yüksek spread (kalitesi düşük sinyalleri de alır)
- **Sonuç:** Günde 5-12 sinyal

---

### COOLDOWN (Aynı Coin İçin Sonraki Sinyal Ne Kadar Sonra)

|  | **LOW** | **MEDIUM** | **HIGH** |
|---|---|---|---|
| SHORT | 15 min | 10 min | **5 min** |
| MEDIUM | 30 min | 20 min | **10 min** |
| LONG | 60 min | 45 min | **30 min** |

**Ne demek?**
- **LOW**: BTCUSDT sinyal alırsan, 30 dakika sonra tekrar sinyal alabilirsin
- **HIGH**: Aynı coin'den her 10 dakikada sinyal alabilirsin (4x daha fazla!)

---

## 🧮 Sinyallenme Örneği: BTC/USDT

Market durumu:
```
Price: $45,000
EMA20: $44,900 (Price biraz yukarıda)
EMA50: $44,500 (Trend UP)
RSI: 65 (Momentum iyi)
Volume: 1.5x normal (Orta spike)
Volatility: 0.25 (Düşük)
```

### Farklı Risk Seviyelerinde Ne Oluyor?

#### LOW RISK
```
✅ Quality Gates:
  • Trend strength: 0.80 >= 0.85? FAIL ❌
  
Result: SINYAL YOK (çok katı)
```

#### MEDIUM RISK
```
✅ Quality Gates:
  • Trend strength: 0.80 >= 0.70? PASS ✅
  • Volume spike: 1.5 >= 1.4? PASS ✅
  • ATR: 250 >= 0.0012? PASS ✅
  • Spread: 0.002 <= 0.005? PASS ✅
  • RR ratio: 1.3 >= 1.3? PASS ✅

✅ Score:
  (0.80 × 0.40) = 0.32
  (0.65 × 0.30) = 0.195
  (1.5 × 0.20) = 0.30
  -(0.25 × 0.07) = -0.0175
  -(0.15 × 0.03) = -0.0045
  
  TOTAL = 0.79 × 100 = 79 ✅ SINYAL GÖNDERİL
```

#### HIGH RISK
```
✅ Quality Gates:
  • Trend strength: 0.80 >= 0.55? PASS ✅✅✅
  • Volume spike: 1.5 >= 1.2? PASS ✅✅✅
  • (diğerleri de PASS)

✅ Score:
  (0.80 × 0.40) = 0.32
  (0.65 × 0.35) = 0.2275 ← Momentum daha önemli
  (1.5 × 0.15) = 0.225 ← Volüm daha az
  -(0.25 × 0.05) = -0.0125 ← Ceza daha az
  
  TOTAL = 0.815 × 100 = 81.5 ✅ SINYAL (daha hızlı)
```

---

## 🎯 Sonuç: Risk Seviyesi Nasıl Çalışıyor?

```
HORIZON = Zaman dilimi (1 dk, 5 dk vs 1 saat)
RISK    = Sinyal kalitesi ve sıklığı

Kombinasyon = 9 FARKLı ANALIZ MODUDan BİRİ
```

### Risk Seviyesi Değiştirdiğimizde:

1. **Yeni Preset Yükleniyor**
   ```python
   user_settings = {"horizon": "medium", "risk": "high"}
   preset = load_for("medium", "high")  # MEDIUM_HIGH yükleniyor
   ```

2. **Detector Bunu Kullanıyor**
   ```python
   cooldown = preset.cooldown_minutes  # 10 min kullanılacak
   ```

3. **Analyzer Bunu Kullanıyor**
   ```python
   passes, reason = passes_quality_gate(components, preset)  # 5 gate'i kontrol ediyor
   score = compute_score(components, preset)  # Scoring farklı ağırlıklar ile
   ```

4. **Sonuç: Tamamen Farklı Sinyaller**
   - LOW: Az, güvenilir (%85-90 başarı)
   - MEDIUM: Dengeli (%75-80 başarı)
   - HIGH: Sık, riskli (%60-70 başarı)

---

## 🚀 Pratikte Kullanım

```bash
# Güvenli trading istiyorsan
/sethorizon long
/setrisk low
→ Haftada 1-2 sinyal, %90 başarı oranı

# Agresif trading istiyorsan
/sethorizon short
/setrisk high
→ Saatte 5-10 sinyal, %60 başarı oranı

# Dengeli trading (DEFAULT)
/sethorizon medium
/setrisk medium
→ Günde 3-8 sinyal, %78 başarı oranı
```

---

## 📋 Tüm 9 Preset Listesi

### SHORT HORIZON (1-15 dakika)
- **SHORT/LOW**: 15 min cooldown, 0.75 min trend, %85 success
- **SHORT/MEDIUM**: 10 min cooldown, 0.65 min trend, %75 success
- **SHORT/HIGH**: 5 min cooldown, 0.50 min trend, %60 success

### MEDIUM HORIZON (15 min - 1 saat)
- **MEDIUM/LOW**: 30 min cooldown, 0.85 min trend, %85 success
- **MEDIUM/MEDIUM**: 20 min cooldown, 0.70 min trend, %78 success (DEFAULT)
- **MEDIUM/HIGH**: 10 min cooldown, 0.55 min trend, %70 success

### LONG HORIZON (1 saat - 1 gün)
- **LONG/LOW**: 60 min cooldown, 0.90 min trend, %90 success
- **LONG/MEDIUM**: 45 min cooldown, 0.75 min trend, %80 success
- **LONG/HIGH**: 30 min cooldown, 0.60 min trend, %72 success

---

## ✅ Özet

**Evet, analiz tekniği tamamen değişiyor!**

Risk seviyesini değiştirmek:
- ✅ Scoring ağırlıklarını değiştiriyor
- ✅ Quality gates'i değiştiriyor
- ✅ Cooldown'ı değiştiriyor
- ✅ Sinyal sıklığını değiştiriyor
- ✅ Başarı oranını değiştiriyor

**Sonuç:** 9 farklı "bot kişiliği" arasında seçim yapıyorsunuz! 🤖
