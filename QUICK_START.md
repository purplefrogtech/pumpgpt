# PUMP•GPT v3.0 - Quick Reference Card

## 🚀 Installation (5 minutes)

```bash
# 1. Clone/navigate to project
cd pumpgpt

# 2. Create virtual environment
python -m venv venv
source venv/bin/activate  # Linux/Mac
# or: venv\Scripts\activate  # Windows

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure
cp .env.example .env
# Edit .env with your keys

# 5. Run
python pumpbot/main.py
```

---

## 📋 Essential Configuration

**Minimum Required (.env):**
```bash
BOT_TOKEN=your_bot_token
TELEGRAM_CHAT_IDS=your_chat_id
BINANCE_API_KEY=your_key
BINANCE_API_SECRET=your_secret
VIP_USER_IDS=your_user_id
```

**Signal Tuning:**
```bash
TIMEFRAME=15m
HTF_TIMEFRAME=1h
SCAN_INTERVAL_SECONDS=60
THROTTLE_MINUTES=5
```

**Quality Thresholds:**
```bash
MIN_RISK_REWARD=1.2
MIN_ATR_PCT=0.000075
MIN_VOLUME_RATIO=1.2
```

---

## 🎮 Telegram Commands

### Info
- `/start` - Welcome
- `/health` - Binance check
- `/symbols` - List coins
- `/status` - Recent signals
- `/profile` - Your settings

### Settings
- `/sethorizon short|medium|long` - Time focus
- `/setrisk low|medium|high` - Risk level

### Monitoring
- `/pnl` - P&L summary
- `/trades` - Trade history
- `/config` - Strategy params
- `/report` - Daily report
- `/testsignal` - System test

---

## 📊 Signal Frequency (Default Settings)

| Market | Majors | Mid-caps | Alts |
|--------|--------|----------|------|
| Normal | 2-5/day | 1-3/day | 0-2/day |
| Trend | 5-10/day | 3-5/day | 2-4/day |
| Quiet | 0-2/day | 0-1/day | 0/day |

*Per symbol throttle: 5 minutes*

---

## 🔧 Troubleshooting

**No signals?**
1. Check `/health` (Binance OK?)
2. Lower `MIN_RISK_REWARD` (1.1)
3. Lower `MIN_ATR_PCT` (0.00003)
4. Set `/setrisk high`
5. Lower `THROTTLE_MINUTES` (2)

**Too many false signals?**
1. Raise `MIN_RISK_REWARD` (1.5)
2. Raise `MIN_ATR_PCT` (0.0001)
3. Set `/setrisk low`
4. Add `MIN_SUCCESS_RATE=50`

**Bot crashes?**
1. Check logs for errors
2. Verify API credentials
3. Check internet connection
4. Restart: `python main.py`

---

## 📁 Important Files

| File | Purpose |
|------|---------|
| `main.py` | Entry point |
| `pumpbot/core/analyzer.py` | Signal logic |
| `pumpbot/core/quality_filter.py` | Validation |
| `.env` | Configuration (secrets) |
| `signals.db` | SQLite database |
| `./charts/` | Generated PNG charts |

---

## 📊 Database Queries

```bash
# Open SQLite
sqlite3 signals.db

# View stats
SELECT COUNT(*) FROM signals;
SELECT COUNT(*) FROM trades;
SELECT status, COUNT(*) FROM trades GROUP BY status;

# View recent trades
SELECT symbol, side, entry, pnl_usd FROM trades ORDER BY id DESC LIMIT 10;

# Calculate winrate
SELECT SUM(CASE WHEN pnl_usd>0 THEN 1 ELSE 0 END)*100/COUNT(*) FROM trades WHERE status='CLOSED';
```

---

## 🎛️ Signal Presets (9 Total)

```
                SHORT           MEDIUM          LONG
LOW (strict)    3-8/day         1-4/day         0-2/day
MEDIUM (bal)    8-15/day        3-8/day         1-3/day
HIGH (loose)    15-30/day       5-12/day        2-5/day
```

Each preset has custom:
- Quality gate thresholds
- Scoring weights
- Cooldown timing

---

## 🔄 Signal Flow (Simplified)

```
HTF Trend (1h) → Base Entry (15m) → Position Size
      ↓               ↓                   ↓
  UP/DOWN        Pullback + BB         Entry/SL/TP
                                        ↓
Chart Generate ← Quality Filter ← Score Compute
      ↓               ↓
   PNG            Pass? No → Block
      ↓              ↓
   Attach         Yes ↓
      ↓          Throttle Check
  Send VIP ←      ↓
   Signal        Sim Trade
```

---

## 🛡️ Quality Filters (Mandatory)

Must pass ALL to get signal:
- Price > 0
- Trend confirmed
- RSI in [30, 70]
- Risk:Reward ≥ 1.2
- ATR% ≥ 0.000075
- Spread ≤ 1%
- Not in liquidity cluster

---

## ⚙️ Performance Tips

**More Signals:**
- Lower `MIN_RISK_REWARD`
- Lower `MIN_ATR_PCT`
- Set `/setrisk high`
- Reduce `THROTTLE_MINUTES`
- Add more symbols

**Better Quality:**
- Raise `MIN_RISK_REWARD`
- Set `/setrisk low`
- Increase `THROTTLE_MINUTES`
- Add `MIN_SUCCESS_RATE=50`

**Less CPU:**
- Raise `SCAN_INTERVAL_SECONDS`
- Lower `SCAN_CONCURRENCY` (1-2)
- Fewer symbols

---

## 📊 Risk Management

**Position Sizing:**
```
qty = (equity × risk%) / stop_distance
```

**TP Strategy:**
- TP1: Close 50% (default)
- TP2: Close 50% (remaining)
- SL: Auto-close if hit

**Fee Handling:**
```
fee = notional × fee_bps / 10000
pnl_net = pnl_gross - total_fees
```

---

## 📈 Monitoring Checklist

Daily:
- [ ] Check `/status` for signals
- [ ] Monitor `/pnl` for drawdown
- [ ] Review `/health` (Binance OK?)
- [ ] Check logs for errors

Weekly:
- [ ] View `/report` for summary
- [ ] Check `/trades` for patterns
- [ ] Review win rate trend
- [ ] Adjust settings if needed

---

## 🚨 Important Warnings

⚠️ **This is simulation/educational only**
- Do NOT blindly trade all signals
- Do NOT use with real money without testing
- Crypto is HIGHLY VOLATILE
- Always use stop losses
- Past performance ≠ future results
- Your money, your responsibility

---

## 📞 Quick Support

**Bot won't start?**
- Check Python 3.11+: `python --version`
- Check deps: `pip list | grep telegram`
- Check .env exists and has values
- Check logs for specific error

**No signals after 1 hour?**
- Send `/health` → Check ✅
- Send `/status` → Check if any signals
- Lower quality thresholds
- Check scanner running (logs)

**Signals too frequent?**
- Set `/setrisk low`
- Increase `THROTTLE_MINUTES`
- Raise quality thresholds

**Telegram errors?**
- Verify BOT_TOKEN correct
- Verify TELEGRAM_CHAT_IDS correct
- Verify VIP_USER_IDS correct
- Try `/testsignal`

---

## 🔐 Security Reminders

✅ Do's:
- Store `.env` locally (never share)
- Use read-only API keys
- Restrict VIP_USER_IDS
- Back up database regularly

❌ Don'ts:
- Commit `.env` to git
- Share API keys
- Post logs with credentials
- Use weak bot token

---

## 📚 Documentation

Quick reads:
- **RUN.md** - Setup & troubleshooting (10 min)
- **SYSTEM_DESIGN.md** - Architecture (15 min)
- **CHECKLIST.md** - Verification (5 min)

Deep dives:
- `pumpbot/core/analyzer.py` - Signal logic
- `pumpbot/core/presets.py` - Preset definitions
- `pumpbot/core/quality_filter.py` - Validation rules

---

## 🎯 Success Indicators

✅ System working when:
1. `/health` shows ✅ Binance OK
2. `/testsignal` sends mock signal
3. After 1 hour: `/status` shows signals
4. After 24 hours: `/pnl` shows trades
5. `/report` shows daily summary

---

## 📊 Expected Results (Default Settings)

**After 24 hours:**
- 10-20 signals across 40+ symbols
- 1-3 signals per major (BTC, ETH, SOL)
- 50-80% of signals generated
- 40-60% of trades closed

**After 1 week:**
- 70-140 total signals
- Database with 50+ trades
- Win rate trend visible
- Equity curve shows P&L

---

**Last Updated:** December 2025
**Version:** 3.0
**Status:** Production Ready ✅
