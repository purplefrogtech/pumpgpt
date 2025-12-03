# Integration Guide: Horizon + Risk System

## Quick Start

### 1. Verify Installation

```bash
# Check all new files exist
ls -la pumpbot/telebot/user_settings.py
ls -la pumpbot/core/presets.py
ls -la pumpbot/core/signal_engine.py
```

### 2. Test User Settings

```bash
python -c "
from pumpbot.telebot.user_settings import *
from pumpbot.core.presets import load_for

# Test default user
settings = get_user_settings(123456789)
print('Default settings:', settings)

# Test update
update_user_settings(123456789, 'horizon', 'long')
update_user_settings(123456789, 'risk', 'low')

# Test load
settings = get_user_settings(123456789)
print('Updated settings:', settings)

# Test preset
preset = load_for(settings['horizon'], settings['risk'])
print('Preset cooldown:', preset.cooldown_minutes)
"
```

### 3. Test Signal Engine

```bash
python -c "
from pumpbot.core.signal_engine import *

components = SignalComponents(
    trend_strength=0.8,
    momentum=0.7,
    volume_spike=1.5,
    volatility=0.2,
    noise_level=0.1,
)

from pumpbot.core.presets import MEDIUM_MEDIUM
score = compute_score(components, MEDIUM_MEDIUM)
print(f'Score: {score:.1f}')
"
```

### 4. Start Bot and Test Commands

```bash
python pumpbot/main.py
```

In Telegram:
```
/profile          # See default settings
/sethorizon long  # Change horizon
/setrisk low      # Change risk
/profile          # Confirm changes
```

---

## Integration Points (Pending)

### detector.py Integration

**What needs to change:**
- `scan_symbols()` needs to know which user to scan for
- `_process_symbol()` needs to load user settings
- Pass coefficients to analyzer

**Current flow:**
```python
def scan_symbols():
    for symbol in symbols:
        _process_symbol(symbol)

def _process_symbol(symbol):
    analyze_symbol_midterm(symbol, ...)  # Uses hardcoded thresholds
```

**New flow:**
```python
def scan_symbols(user_id):
    user_settings = get_user_settings(user_id)
    for symbol in symbols:
        _process_symbol(symbol, user_settings)

def _process_symbol(symbol, user_settings):
    coefficients = load_for(user_settings['horizon'], user_settings['risk'])
    analyze_symbol_midterm(symbol, coefficients=coefficients)
```

### analyzer.py Integration

**What needs to change:**
- `analyze_symbol_midterm()` should compute SignalComponents
- Call `signal_engine.compute_score()` instead of hardcoded check
- Include score in returned payload

**Current logic:**
```python
def analyze_symbol_midterm(symbol):
    trend_strength = compute_trend(...)
    if trend_strength > 0.7:  # Hardcoded
        return SignalPayload(...)
```

**New logic:**
```python
def analyze_symbol_midterm(symbol, coefficients):
    components = SignalComponents(
        trend_strength=compute_trend(...),
        momentum=compute_momentum(...),
        volume_spike=compute_volume_ratio(...),
        volatility=compute_volatility(...),
        noise_level=compute_noise(...),
    )
    
    score = compute_score(components, coefficients)
    passes, reason = passes_quality_gate(components, coefficients)
    
    if not passes:
        return None
    
    return SignalPayload(
        score=score,
        explanation=explain_score(components, coefficients, score),
        ...
    )
```

### main.py Integration

**What needs to change:**
- `on_alert()` should use score from payload
- Optional: Display score in signal message

**Current:**
```python
async def on_alert(payload):
    await send_vip_signal(app, chat_ids, payload)
```

**New:**
```python
async def on_alert(payload):
    # Score already in payload from analyzer
    await send_vip_signal(app, chat_ids, payload)
    # Optional: Log score
    logger.info(f"Signal sent with score: {payload.score:.1f}")
```

---

## File Dependencies

```
main.py
├── imports: get_user_settings, update_user_settings
├── imports: cmd_sethorizon, cmd_setrisk, cmd_profile
├── calls: on_alert(payload)
│   └── passes to: send_vip_signal(app, chat_ids, payload)
│
detector.py
├── calls: scan_symbols(user_id)  [NEW PARAMETER]
│   └── calls: _process_symbol(symbol, user_settings)
│       └── calls: analyze_symbol_midterm(symbol, coefficients)
│
analyzer.py
├── function: analyze_symbol_midterm(symbol, coefficients)  [NEW PARAM]
│   ├── imports: signal_engine.compute_score()
│   ├── imports: signal_engine.passes_quality_gate()
│   ├── imports: signal_engine.explain_score()
│   └── returns: payload with score

presets.py
├── exports: load_for(horizon, risk) → SignalCoefficients
├── exports: describe_preset(horizon, risk)

signal_engine.py
├── exports: compute_score(components, coefficients) → float
├── exports: passes_quality_gate(components, coefficients) → (bool, str)
├── exports: explain_score(components, coefficients, score) → str

user_settings.py
├── exports: get_user_settings(user_id) → Dict
├── exports: update_user_settings(user_id, key, value) → bool
├── exports: load_settings() → Dict[int, Dict]
├── exports: save_settings(data) → bool
```

---

## Checklist for Full Integration

- [ ] Update `detector.py` scan_symbols() to accept user_id
- [ ] Update `detector.py` _process_symbol() to accept user_settings
- [ ] Update `analyzer.py` analyze_symbol_midterm() to compute components
- [ ] Update `analyzer.py` analyze_symbol_midterm() to call compute_score()
- [ ] Update signal payload to include score field
- [ ] Update `main.py` on_alert() to use score (if needed)
- [ ] Test: /profile command
- [ ] Test: /sethorizon command
- [ ] Test: /setrisk command
- [ ] Test: Signal generation with short/high preset
- [ ] Test: Signal generation with long/low preset
- [ ] Monitor: Check user_settings.json for correct updates
- [ ] Create: CHANGELOG_v3.0.md entry

---

## Debug Commands

```python
# In Python shell, test the system:

# 1. Settings persistence
from pumpbot.telebot.user_settings import *
update_user_settings(123, "horizon", "long")
assert get_user_settings(123)["horizon"] == "long"
print("✅ Settings persistence OK")

# 2. Presets loading
from pumpbot.core.presets import load_for
preset = load_for("long", "low")
assert preset.cooldown_minutes == 60
print("✅ Presets loading OK")

# 3. Signal scoring
from pumpbot.core.signal_engine import *
comp = SignalComponents(0.8, 0.7, 1.5, 0.2, 0.1)
score = compute_score(comp, preset)
assert 0 <= score <= 100
print(f"✅ Signal scoring OK (score: {score:.1f})")

# 4. Quality gates
passes, reason = passes_quality_gate(comp, preset)
assert passes == True  # Should pass for these components
print("✅ Quality gates OK")
```

---

## Performance Tuning

### To make signals more frequent:
```python
# In core/presets.py, decrease these:
LONG_LOW.min_trend_strength = 0.80  # was 0.90
LONG_LOW.cooldown_minutes = 45      # was 60
```

### To make signals more reliable:
```python
# In core/presets.py, increase these:
SHORT_HIGH.min_trend_strength = 0.60  # was 0.50
SHORT_HIGH.min_volume_spike = 1.3     # was 1.2
```

---

## Common Issues

### Issue: Signals suddenly changed after update

**Cause:** User settings were applied  
**Solution:** Run `/profile` to check current settings

### Issue: No signals for user with long/low preset

**Cause:** Long/low is very strict (60 min cooldown, 90% trend required)  
**Solution:** Try /sethorizon medium or /setrisk medium

### Issue: Too many false signals with short/high preset

**Cause:** Short/high is aggressive (5 min cooldown, 50% trend required)  
**Solution:** Try /setrisk medium

---

## Next Steps

1. **Wait** for signal generation integration to be implemented in detector/analyzer
2. **Monitor** bot behavior with different user presets
3. **Tune** coefficients based on real signal performance
4. **Document** successful configurations in a user guide
