from __future__ import annotations

import os
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional, Tuple

import matplotlib

# Headless backend
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402
from loguru import logger  # noqa: E402

from pumpbot.core.detector import TREND_DOWN, TREND_UP

DB_PATH = Path("signals.db")
CSV_PATH = os.getenv("SIGNALS_DAILY_CSV", "signals_daily.csv")


def _read_signals_csv(csv_path: str = CSV_PATH) -> Optional[pd.DataFrame]:
    if not os.path.exists(csv_path):
        return None
    try:
        df = pd.read_csv(
            csv_path,
            names=["ts", "symbol", "price", "score", "trend", "tp1", "tp2", "sl"],
        )
        df["ts"] = pd.to_datetime(df["ts"])
        return df
    except Exception:
        logger.exception("signals_daily.csv okunurken hata:")
        return None


def _read_trades_sqlite(start_dt: datetime, end_dt: datetime) -> Optional[pd.DataFrame]:
    if not DB_PATH.exists():
        return None
    try:
        con = sqlite3.connect(DB_PATH)
        q = """
        SELECT symbol, side, entry, tp1, tp2, sl, status,
               opened_at, closed_at, pnl_usd, pnl_pct
        FROM trades
        WHERE (opened_at BETWEEN ? AND ?)
           OR (closed_at BETWEEN ? AND ?)
        ORDER BY id ASC
        """
        df = pd.read_sql_query(
            q,
            con,
            params=[
                start_dt.strftime("%Y-%m-%d 00:00:00"),
                end_dt.strftime("%Y-%m-%d 23:59:59"),
                start_dt.strftime("%Y-%m-%d 00:00:00"),
                end_dt.strftime("%Y-%m-%d 23:59:59"),
            ],
        )
        con.close()
        for c in ["opened_at", "closed_at"]:
            if c in df.columns:
                df[c] = pd.to_datetime(df[c], errors="coerce")
        return df
    except Exception:
        logger.exception("SQLite trades okunurken hata:")
        return None


def _plot_score_hist(df_signals: pd.DataFrame, out_png: str) -> None:
    plt.figure(figsize=(6, 3))
    df_signals["score"].astype(float).hist(bins=30)
    plt.title("Sinyal Skor Dağılımı")
    plt.xlabel("Skor")
    plt.ylabel("Adet")
    plt.tight_layout()
    plt.savefig(out_png, dpi=150)
    plt.close()


def _plot_equity_curve(df_trades: pd.DataFrame, out_png: str) -> Optional[str]:
    """Kapalı işlemlerden kümülatif PnL eğrisi."""
    closed = df_trades.dropna(subset=["closed_at"]).copy()
    if closed.empty:
        return None
    closed = closed.sort_values("closed_at")
    closed["cum_pnl"] = closed["pnl_usd"].fillna(0).cumsum()
    plt.figure(figsize=(6, 3))
    plt.plot(closed["closed_at"], closed["cum_pnl"], linewidth=2)
    plt.title("Kümülatif PnL (Kapalı işlemler)")
    plt.xlabel("Zaman")
    plt.ylabel("USD")
    plt.tight_layout()
    plt.savefig(out_png, dpi=150)
    plt.close()
    return out_png


def generate_daily_report(csv_path: str = CSV_PATH) -> Tuple[str, Optional[str]]:
    """
    Returns (summary_text, chart_path_or_None) for the current day.
    """
    today = datetime.now().date()
    start_dt = datetime.combine(today, datetime.min.time())
    end_dt = datetime.combine(today, datetime.max.time())

    df_signals = _read_signals_csv(csv_path)
    df_signals_today = (
        df_signals[
            (df_signals["ts"] >= start_dt) & (df_signals["ts"] <= end_dt)
        ].copy()
        if df_signals is not None
        else None
    )
    df_trades = _read_trades_sqlite(start_dt, end_dt)

    parts = ["🧾 Gün Sonu Özeti"]

    if df_signals_today is not None and not df_signals_today.empty:
        up_cnt = int((df_signals_today["trend"] == TREND_UP).sum())
        dn_cnt = int((df_signals_today["trend"] == TREND_DOWN).sum())
        parts += [
            f"• Toplam sinyal: {len(df_signals_today)}",
            f"• Yükseliş/Düşüş: {up_cnt}/{dn_cnt}",
            f"• Ortalama skor: {df_signals_today['score'].astype(float).mean():.2f}",
            f"• En yüksek skor: {df_signals_today['score'].astype(float).max():.2f}",
        ]
    else:
        parts.append("• Bugün için sinyal verisi yok veya CSV bulunamadı.")

    if df_trades is not None and not df_trades.empty:
        closed = df_trades.dropna(subset=["closed_at"])
        win_cnt = int((closed["pnl_usd"] > 0).sum())
        lose_cnt = int((closed["pnl_usd"] <= 0).sum())
        pnl_sum = float(closed["pnl_usd"].fillna(0).sum())
        winrate = (win_cnt / len(closed) * 100.0) if len(closed) else 0.0
        parts += [
            f"• Kapalı işlem: {len(closed)} | Win/Loss: {win_cnt}/{lose_cnt} (Winrate {winrate:.1f}%)",
            f"• Toplam PnL (USD): {pnl_sum:.2f}",
        ]
    else:
        parts.append("• İşlem kaydı yok.")

    summary_text = "\n".join(parts)

    score_png = None
    equity_png = None

    if df_signals_today is not None and not df_signals_today.empty:
        score_png = f"report_scores_{today.strftime('%Y%m%d')}.png"
        _plot_score_hist(df_signals_today, score_png)

    if df_trades is not None and not df_trades.empty:
        equity_png = f"report_equity_{today.strftime('%Y%m%d')}.png"
        _plot_equity_curve(df_trades, equity_png)

    chart = score_png or equity_png
    return summary_text, chart
