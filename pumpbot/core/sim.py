from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, Optional, Tuple

from loguru import logger

from pumpbot.core.database import (
    get_open_trades,
    trade_close_all,
    trade_mark_partial,
    trade_open,
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
    equity_usd: float  # Total equity (simulation)
    risk_pct: float  # Risk per trade (%)
    tp1_ratio_qty: float  # Portion to close at TP1 (0.5 = 50%)
    fee_bps: float  # Exchange fee in basis points
    be_on_tp1: bool  # Move SL to breakeven after TP1
    notify: bool  # Notify via Telegram

    @classmethod
    def from_env(cls) -> "SimConfig":
        return cls(
            equity_usd=_env_float("SIM_EQUITY_USD", 10000),
            risk_pct=_env_float("SIM_RISK_PER_TRADE_PCT", 1.0),
            tp1_ratio_qty=_env_float("SIM_TP1_RATIO_QTY", 0.5),
            fee_bps=_env_float("SIM_FEE_BPS", 8.0),
            be_on_tp1=bool(_env_int("SIM_BE_ON_TP1", 1)),
            notify=bool(_env_int("SIM_NOTIFY", 1)),
        )


class SimEngine:
    """
    Simple rule set:
      - Position size (qty) = (equity * risk%) / stop_distance
      - TP1 closes qty * tp1_ratio_qty; optional BE after TP1
      - Fees applied per leg
      - Writes trades to SQLite
    """

    def __init__(self, notifier: Optional[Callable[[str], None]] = None):
        self.cfg = SimConfig.from_env()
        self._notify = notifier

    # -------- Helpers --------
    def _fee(self, notional_usd: float) -> float:
        return (self.cfg.fee_bps / 10_000.0) * float(notional_usd)

    async def _notify_if(self, text: str) -> None:
        if self.cfg.notify and self._notify:
            await self._notify(text)

    @staticmethod
    def _extract_entry_price(payload: dict) -> float:
        entry = payload.get("entry")
        if isinstance(entry, (list, tuple)) and entry:
            values = [float(x) for x in entry]
            return float(sum(values) / len(values))
        if entry is not None:
            return float(entry)
        return float(payload.get("price"))

    @staticmethod
    def _extract_tp_levels(payload: dict) -> Tuple[float, float]:
        levels = payload.get("tp_levels")
        if isinstance(levels, (list, tuple)) and levels:
            if len(levels) == 1:
                return float(levels[0]), float(levels[0])
            return float(levels[0]), float(levels[1])
        return float(payload.get("tp1")), float(payload.get("tp2"))

    # -------- Events --------
    async def on_signal_open(self, payload: dict):
        """
        Open position on new signal.
        payload: {symbol, side, entry/tp_levels, sl, ...}
        """
        symbol, side = payload["symbol"], payload["side"]
        entry = self._extract_entry_price(payload)
        tp1, tp2 = self._extract_tp_levels(payload)
        sl = float(payload["sl"])

        stop_dist = abs(entry - sl)
        if stop_dist <= 0:
            logger.warning(f"{symbol} stop distance is zero; trade not opened.")
            return

        risk_usd = self.cfg.equity_usd * (self.cfg.risk_pct / 100.0)
        qty = risk_usd / stop_dist
        if qty <= 0:
            logger.warning(f"{symbol} qty <= 0; trade not opened.")
            return

        size_usd = qty * entry
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

        trade_open(
            symbol=symbol,
            side=side,
            entry=entry,
            size=size_usd,
            qty=qty,
            tp1=tp1,
            tp2=tp2,
            sl=sl,
            opened_at=now,
        )

        txt = (
            f"{side} OPEN {symbol}\n"
            f"Entry:{entry:.4f} SL:{sl:.4f} TP1:{tp1:.4f} TP2:{tp2:.4f}"
        )
        logger.info(txt)
        await self._notify_if(txt)

    async def on_tick(self, symbol: str, last_price: float):
        """
        Advance open trades on every price tick.
        """
        for t in get_open_trades():
            (
                _id,
                sym,
                side,
                entry,
                size,
                qty,
                tp1,
                tp2,
                sl,
                filled_tp1_qty,
                status,
                opened_at,
                lastp,
            ) = t

            if sym != symbol:
                continue

            if side == "SHORT":
                if last_price <= tp2:
                    await self._final_close(
                        sym,
                        side,
                        entry,
                        qty,
                        tp1,
                        tp2,
                        sl,
                        filled_tp1_qty,
                        exit_price=tp2,
                        reason="TP2",
                    )
                    continue
                if last_price >= sl:
                    await self._final_close(
                        sym,
                        side,
                        entry,
                        qty,
                        tp1,
                        tp2,
                        sl,
                        filled_tp1_qty,
                        exit_price=sl,
                        reason="SL",
                    )
                    continue
                need_partial = (last_price <= tp1) and (
                    filled_tp1_qty < qty * self.cfg.tp1_ratio_qty
                )
                if need_partial:
                    close_qty = qty * self.cfg.tp1_ratio_qty - filled_tp1_qty
                    if close_qty > 0:
                        realized = (entry - tp1) * close_qty
                        realized -= self._fee(entry * close_qty) + self._fee(tp1 * close_qty)
                        trade_mark_partial(
                            sym,
                            close_qty,
                            last_price,
                            datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
                        )
                        await self._notify_if(f"TP1 HIT SHORT {sym} +${realized:.2f}")

            if side == "LONG":
                if last_price >= tp2:
                    await self._final_close(
                        sym,
                        side,
                        entry,
                        qty,
                        tp1,
                        tp2,
                        sl,
                        filled_tp1_qty,
                        exit_price=tp2,
                        reason="TP2",
                    )
                    continue
                if last_price <= sl:
                    await self._final_close(
                        sym,
                        side,
                        entry,
                        qty,
                        tp1,
                        tp2,
                        sl,
                        filled_tp1_qty,
                        exit_price=sl,
                        reason="SL",
                    )
                    continue
                need_partial = (last_price >= tp1) and (
                    filled_tp1_qty < qty * self.cfg.tp1_ratio_qty
                )
                if need_partial:
                    close_qty = qty * self.cfg.tp1_ratio_qty - filled_tp1_qty
                    if close_qty > 0:
                        realized = (tp1 - entry) * close_qty
                        realized -= self._fee(entry * close_qty) + self._fee(tp1 * close_qty)
                        trade_mark_partial(
                            sym,
                            close_qty,
                            last_price,
                            datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
                        )
                        await self._notify_if(f"TP1 HIT LONG {sym} +${realized:.2f}")

    # -------- Closing & total PnL --------
    def _compute_total_pnl(
        self,
        side: str,
        entry: float,
        qty: float,
        tp1: float,
        tp2: float,
        sl: float,
        filled_tp1_qty: float,
        final_exit_price: float,
        reason: str,
    ) -> float:
        """
        Total PnL = (TP1 partial) + (remainder at exit)
        Fees are applied per leg.
        """
        q1 = float(min(filled_tp1_qty, qty))
        q2 = float(max(qty - q1, 0.0))

        pnl = 0.0
        if q1 > 0:
            if side == "LONG":
                pnl += (tp1 - entry) * q1
                pnl -= self._fee(entry * q1) + self._fee(tp1 * q1)
            else:
                pnl += (entry - tp1) * q1
                pnl -= self._fee(entry * q1) + self._fee(tp1 * q1)

        exit_price = final_exit_price
        if self.cfg.be_on_tp1 and q1 > 0 and reason == "SL":
            exit_price = entry

        if q2 > 0:
            if side == "LONG":
                pnl += (exit_price - entry) * q2
                pnl -= self._fee(entry * q2) + self._fee(exit_price * q2)
            else:
                pnl += (entry - exit_price) * q2
                pnl -= self._fee(entry * q2) + self._fee(exit_price * q2)

        return float(pnl)

    async def _final_close(
        self,
        symbol: str,
        side: str,
        entry: float,
        qty: float,
        tp1: float,
        tp2: float,
        sl: float,
        filled_tp1_qty: float,
        exit_price: float,
        reason: str,
    ):
        """
        Close trade fully, compute PnL, and persist.
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
            reason=reason,
        )
        size_usd = float(qty) * float(entry)
        pnl_pct = (total_pnl / size_usd * 100.0) if size_usd else 0.0

        await self._notify_if(
            f"{symbol} {reason} | Exit:{exit_price} | PnL ${total_pnl:.2f} ({pnl_pct:.2f}%)"
        )
        trade_close_all(
            symbol,
            last_price=float(exit_price),
            now_ts=datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
            realized_pnl_usd=total_pnl,
            realized_pnl_pct=pnl_pct,
        )
