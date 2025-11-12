# pumpbot/core/sim.py
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from loguru import logger

from pumpbot.core.database import (
    trade_open, trade_mark_partial, trade_close_all, get_open_trades
)

def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except Exception:
        return float(default)

def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except Exception:
        return int(default)

@dataclass
class SimConfig:
    equity_usd: float                 # Toplam sermaye (simülasyon)
    risk_pct: float                   # İşlem başına risk %
    tp1_ratio_qty: float              # TP1'de kapatılacak miktar oranı (0.5 = %50)
    fee_bps: float                    # Borsa ücreti (bps: 10 = 0.10%)
    be_on_tp1: bool                   # TP1 sonrası SL'yi break-even'a çek
    notify: bool                      # Telegram bildirimi açık mı

    @classmethod
    def from_env(cls):
        return cls(
            equity_usd=_env_float("SIM_EQUITY_USD", 10000),
            risk_pct=_env_float("SIM_RISK_PER_TRADE_PCT", 1.0),
            tp1_ratio_qty=_env_float("SIM_TP1_RATIO_QTY", 0.5),
            fee_bps=_env_float("SIM_FEE_BPS", 8.0),       # varsayılan: 0.08%
            be_on_tp1=bool(_env_int("SIM_BE_ON_TP1", 1)), # 1 = açık
            notify=bool(_env_int("SIM_NOTIFY", 1)),
        )

class SimEngine:
    """
    Basit kural:
      - Pozisyon büyüklüğü = (equity * risk%) / stop_distance
      - TP1 vurulursa qty*tp1_ratio kapat, istenirse SL = entry (break-even)
      - Kapanışta toplam PnL (kısmi + final) doğru hesaplanır ve DB'ye yazılır.
      - Fee yaklaşık olarak her bacakta notional * fee_bps/10000 kadar düşülür.
    """

    def __init__(self, notifier=None):
        self.cfg = SimConfig.from_env()
        self._notify = notifier

    # -------- Yardımcılar --------
    def _fee(self, notional_usd: float) -> float:
        return (self.cfg.fee_bps / 10_000.0) * float(notional_usd)

    async def _notify_if(self, text: str):
        if self.cfg.notify and self._notify:
            await self._notify(text)

    # -------- Olaylar --------
    async def on_signal_open(self, p: dict):
        """
        Yeni sinyalde pozisyon aç.
        p = {symbol, side, price, tp1, tp2, sl, ...}
        """
        symbol, side = p["symbol"], p["side"]
        entry, sl = float(p["price"]), float(p["sl"])

        stop_dist = abs(entry - sl)
        if stop_dist <= 0:
            logger.warning(f"{symbol} için stop mesafesi 0! Pozisyon açılmadı.")
            return

        risk_usd = self.cfg.equity_usd * (self.cfg.risk_pct / 100.0)
        qty = risk_usd / stop_dist
        if qty <= 0:
            logger.warning(f"{symbol} için hesaplanan miktar <= 0! Pozisyon açılmadı.")
            return

        size_usd = qty * entry
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

        # DB kayıt
        trade_open(
            symbol=symbol,
            side=side,
            entry=entry,
            size_usd=size_usd,
            qty=qty,
            tp1=float(p["tp1"]),
            tp2=float(p["tp2"]),
            sl=float(p["sl"]),
            opened_at=now
        )

        txt = f"🟢 *{side} OPEN* {symbol}\nEntry:{entry} SL:{p['sl']} TP1:{p['tp1']} TP2:{p['tp2']}"
        logger.info(txt.replace('*', ''))
        await self._notify_if(txt)

    async def on_tick(self, symbol: str, last_price: float):
        """
        Her yeni fiyat (ticker) güncellemesinde açık işlemleri ilerlet.
        """
        for t in get_open_trades():
            (_id, sym, side, entry, size, qty, tp1, tp2, sl,
             filled_tp1_qty, status, opened_at, lastp) = t

            if sym != symbol:
                continue

            # SHORT
            if side == "SHORT":
                # TP2 – tam kapanış
                if last_price <= tp2:
                    await self._final_close(sym, side, entry, qty, tp1, tp2, sl,
                                            filled_tp1_qty, exit_price=tp2, reason="TP2")
                    continue
                # SL – tam kapanış
                if last_price >= sl:
                    await self._final_close(sym, side, entry, qty, tp1, tp2, sl,
                                            filled_tp1_qty, exit_price=sl, reason="SL")
                    continue
                # TP1 – kısmi kapanış
                need_partial = (last_price <= tp1) and (filled_tp1_qty < qty * self.cfg.tp1_ratio_qty)
                if need_partial:
                    close_qty = qty * self.cfg.tp1_ratio_qty - filled_tp1_qty
                    if close_qty > 0:
                        # realized pnl (kısmi)
                        realized = (entry - tp1) * close_qty
                        # iki işlem ücreti (close leg + önceki open leg payı)
                        realized -= self._fee(entry * close_qty) + self._fee(tp1 * close_qty)
                        # DB güncelle
                        trade_mark_partial(sym, close_qty, last_price,
                                           datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"))
                        await self._notify_if(f"✅ TP1 HIT SHORT {sym} +${realized:.2f}")

                        # BE özelliği: SL = entry
                        if self.cfg.be_on_tp1:
                            # Not: SL güncellemesini DB şemasına atmıyoruz; sim mantık akışında
                            # 'sl' değişkenini RAM tarafında sadece bu tick için yükseltmek yeterli değil.
                            # Bu nedenle BE sadece kapanış hesaplarına etki etsin diye
                            # _final_close sırasında dikkate alacağız (bkz. compute_total_pnl).
                            pass

            # LONG
            if side == "LONG":
                if last_price >= tp2:
                    await self._final_close(sym, side, entry, qty, tp1, tp2, sl,
                                            filled_tp1_qty, exit_price=tp2, reason="TP2")
                    continue
                if last_price <= sl:
                    await self._final_close(sym, side, entry, qty, tp1, tp2, sl,
                                            filled_tp1_qty, exit_price=sl, reason="SL")
                    continue
                need_partial = (last_price >= tp1) and (filled_tp1_qty < qty * self.cfg.tp1_ratio_qty)
                if need_partial:
                    close_qty = qty * self.cfg.tp1_ratio_qty - filled_tp1_qty
                    if close_qty > 0:
                        realized = (tp1 - entry) * close_qty
                        realized -= self._fee(entry * close_qty) + self._fee(tp1 * close_qty)
                        trade_mark_partial(sym, close_qty, last_price,
                                           datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"))
                        await self._notify_if(f"✅ TP1 HIT LONG {sym} +${realized:.2f}")
                        # BE açıklaması için bkz. yukarıdaki not.

    # -------- Kapanış ve toplam PnL --------
    def _compute_total_pnl(self, side: str, entry: float, qty: float,
                           tp1: float, tp2: float, sl: float,
                           filled_tp1_qty: float, final_exit_price: float,
                           reason: str) -> float:
        """
        Toplam PnL = (TP1 kapatılan kısım) + (kalan miktarın final çıkışı)
        Ücretler (fee) her bacak için düşülür.
        BE (break-even) açık ise, TP1 sonrası SL'ye gelmiş kapanışlarda,
        kalan kısım için exit_price=entry varsayımı kullanılır (gerçekçi basit model).
        """
        q1 = float(min(filled_tp1_qty, qty))
        q2 = float(max(qty - q1, 0.0))

        pnl = 0.0
        # TP1 kısmı:
        if q1 > 0:
            if side == "LONG":
                pnl += (tp1 - entry) * q1
                pnl -= self._fee(entry * q1) + self._fee(tp1 * q1)
            else:
                pnl += (entry - tp1) * q1
                pnl -= self._fee(entry * q1) + self._fee(tp1 * q1)

        # Kalan kısım:
        exit_price = final_exit_price

        # BE politikası: TP1 vurulmuş ve SL nedeniyle kapanışsa, BE aktifse
        if self.cfg.be_on_tp1 and q1 > 0 and reason == "SL":
            exit_price = entry  # kalan kısım break-even'dan kapanmış kabul

        if q2 > 0:
            if side == "LONG":
                pnl += (exit_price - entry) * q2
                pnl -= self._fee(entry * q2) + self._fee(exit_price * q2)
            else:
                pnl += (entry - exit_price) * q2
                pnl -= self._fee(entry * q2) + self._fee(exit_price * q2)

        return float(pnl)

    async def _final_close(self, symbol: str, side: str, entry: float, qty: float,
                           tp1: float, tp2: float, sl: float,
                           filled_tp1_qty: float, exit_price: float, reason: str):
        """
        İşlemi tamamen kapat, toplam PnL'i hesapla, DB'ye işle.
        """
        total_pnl = self._compute_total_pnl(
            side=side,
            entry=float(entry),
            qty=float(qty),
            tp1=float(tp1),
            tp2=float(tp2),
            sl=float(sl),
            filled_tp1_qty=float(filled_tp1_qty),
            final_exit_price=float(exit_price),
            reason=reason
        )
        size_usd = float(qty) * float(entry)
        pnl_pct = (total_pnl / size_usd * 100.0) if size_usd else 0.0

        await self._notify_if(f"💰 {symbol} {reason} | Exit:{exit_price} | PnL ${total_pnl:.2f} ({pnl_pct:.2f}%)")
        trade_close_all(
            symbol,
            last_price=float(exit_price),
            now_ts=datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
            realized_pnl_usd=total_pnl,
            realized_pnl_pct=pnl_pct
        )
