from __future__ import annotations

import html
from datetime import datetime
from pathlib import Path
from typing import Iterable, List, Sequence

from loguru import logger
from telegram.constants import ParseMode


def _parse_chat_ids(chat_ids_csv: str) -> List[int]:
    chat_ids: List[int] = []
    for raw in chat_ids_csv.split(","):
        token = raw.strip()
        if not token:
            continue
        try:
            chat_ids.append(int(token))
        except ValueError:
            logger.warning(f"Geçersiz chat_id atlandı: {token}")
    return chat_ids


def _format_price(value) -> str:
    if value is None:
        return "-"
    try:
        num = float(value)
    except (TypeError, ValueError):
        return str(value)
    if abs(num) >= 100:
        return f"{num:,.2f}"
    if abs(num) >= 1:
        return f"{num:,.4f}"
    return f"{num:.6f}".rstrip("0").rstrip(".")


def _format_dt(dt_val) -> str:
    if isinstance(dt_val, datetime):
        return dt_val.strftime("%Y-%m-%d %H:%M (UTC)")
    if isinstance(dt_val, str):
        try:
            parsed = datetime.fromisoformat(dt_val.replace("Z", "+00:00"))
            return parsed.strftime("%Y-%m-%d %H:%M (UTC)")
        except ValueError:
            return dt_val
    return ""


def _fmt_pct(val, signed: bool = True) -> str:
    try:
        num = float(val)
        return f"{num:+.1f}%" if signed else f"{num:.1f}%"
    except Exception:
        return "-"


def _tp_lines(levels: Sequence[float]) -> List[str]:
    medals = ["🥇", "🥈", "🥉"]
    lines: List[str] = []
    for idx, tp in enumerate(levels, start=1):
        medal = medals[idx - 1] if idx - 1 < len(medals) else "🎯"
        lines.append(f"{medal} <b>TP {idx}</b>: <code>{_format_price(tp)}</code>")
    return lines


def format_signal_message(payload: dict) -> str:
    symbol = payload.get("symbol", "-")
    side_raw = str(payload.get("side", "")).upper()
    side_icon = "🟢" if side_raw == "LONG" else "🔴"
    side = side_raw or "-"
    leverage = payload.get("leverage", "-")
    timeframe = payload.get("timeframe", "-")
    strategy = payload.get("strategy", "-")
    trend_label = payload.get("trend_label") or payload.get("trend_direction") or "-"
    rsi_val = payload.get("rsi")
    atr_pct = payload.get("atr_pct")
    volume_change_pct = payload.get("volume_change_pct")
    success_rate = payload.get("success_rate")
    risk_reward = payload.get("risk_reward")

    entries: Sequence = payload.get("entry") or []
    if not isinstance(entries, Iterable) or isinstance(entries, (str, bytes)):
        entries = [entries]
    entries = [e for e in entries if e is not None]

    tp_levels: Sequence = payload.get("tp_levels") or []
    if not isinstance(tp_levels, Iterable) or isinstance(tp_levels, (str, bytes)):
        tp_levels = [tp_levels]
    tp_levels = [lvl for lvl in tp_levels if lvl is not None]

    stop_loss = payload.get("sl", "-")
    created_at = _format_dt(payload.get("created_at"))

    entry_lines = [f"{idx}) <code>{_format_price(entry)}</code>" for idx, entry in enumerate(entries, start=1)] or ["-"]
    tp_lines = _tp_lines(tp_levels) if tp_levels else []

    lines = [
        "💎 <b>PUMP•GPT VIP SIGNAL</b>",
        "━━━━━━━━━━━━━━━━━━━━━━━━",
        f"📌 <b>{html.escape(str(symbol))}</b> · {side_icon} <b>{side}</b> · {leverage}x",
        f"⏱ Timeframe: {html.escape(str(timeframe))} · Strateji: {html.escape(str(strategy))}",
        "",
        "🎯 <b>Entry Bölgesi</b>",
        *entry_lines,
        "",
        *tp_lines,
        f"🛑 <b>Stop Loss</b>: <code>{_format_price(stop_loss)}</code>",
        "",
        f"📈 Trend: {trend_label}",
        f"📊 RSI: {rsi_val:.1f}" if isinstance(rsi_val, (int, float)) else f"📊 RSI: {rsi_val or '-'}",
        f"🌡 ATR: {_fmt_pct((atr_pct or 0) * 100, signed=False)}" if atr_pct is not None else "🌡 ATR: -",
        f"📦 Volume: {_fmt_pct(volume_change_pct)}",
        (
            f"🎯 Success(30): {_fmt_pct(success_rate, signed=False)} | R:R {risk_reward:.2f}"
            if risk_reward is not None
            else f"🎯 Success(30): {_fmt_pct(success_rate, signed=False)}"
        ),
        "",
        f"📊 Sinyal Zamanı: <code>{created_at}</code>",
        "",
        "⚠️ <i>Kripto piyasaları yüksek risk içerir. İşlemler yatırım tavsiyesi değildir.</i>",
    ]

    return "\n".join([line for line in lines if line is not None])


def format_daily_report_caption(summary: str) -> str:
    safe_summary = html.escape(summary.strip())
    return f"📆 <b>PUMP•GPT Gün Sonu VIP Raporu</b>\n━━━━━━━━━━━━━━━━━━━━━━━━\n{safe_summary}\n\n⚠️ İşlemler yatırım tavsiyesi değildir."


async def send_vip_signal(app, chat_ids_csv: str, payload: dict) -> None:
    chat_ids = _parse_chat_ids(chat_ids_csv)
    caption = format_signal_message(payload)
    chart_path = payload.get("chart_path") or payload.get("chart")
    has_chart = bool(chart_path) and Path(str(chart_path)).exists()

    for cid in chat_ids:
        try:
            if has_chart:
                with open(chart_path, "rb") as photo:
                    await app.bot.send_photo(
                        chat_id=cid,
                        photo=photo,
                        caption=caption,
                        parse_mode=ParseMode.HTML,
                    )
            else:
                await app.bot.send_message(
                    chat_id=cid,
                    text=caption,
                    parse_mode=ParseMode.HTML,
                    disable_web_page_preview=True,
                )
        except Exception as exc:
            logger.error(f"VIP signal send failed for chat {cid}: {exc}")
