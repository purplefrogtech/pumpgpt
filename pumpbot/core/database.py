# pumpbot/core/database.py
import sqlite3
from pathlib import Path

from loguru import logger

DB_PATH = Path("signals.db")


def _conn():
    # WAL mode improves concurrency
    con = sqlite3.connect(DB_PATH, isolation_level=None)
    con.execute("PRAGMA journal_mode=WAL;")
    con.execute("PRAGMA synchronous=NORMAL;")
    return con


def init_db():
    with _conn() as con:
        con.executescript(
            """
        CREATE TABLE IF NOT EXISTS signals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT, price REAL, volume REAL, score REAL,
            rsi REAL, macd REAL, macd_sig REAL,
            volume_spike REAL, ts_utc TEXT
        );
        CREATE TABLE IF NOT EXISTS trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL,
            side TEXT NOT NULL,
            entry REAL NOT NULL, size REAL NOT NULL, qty REAL NOT NULL,
            tp1 REAL NOT NULL, tp2 REAL NOT NULL, sl REAL NOT NULL,
            filled_tp1_qty REAL DEFAULT 0,
            status TEXT NOT NULL,
            opened_at TEXT NOT NULL, closed_at TEXT,
            pnl_usd REAL DEFAULT 0, pnl_pct REAL DEFAULT 0,
            last_price REAL, last_update TEXT
        );
        """
        )
    logger.debug("SQLite tables ready (WAL): signals + trades")


def save_signal(symbol, price, volume, score, rsi, macd, macd_sig, volume_spike, ts_utc):
    try:
        with _conn() as con:
            con.execute(
                """
                INSERT INTO signals
                (symbol, price, volume, score, rsi, macd, macd_sig, volume_spike, ts_utc)
                VALUES (?,?,?,?,?,?,?,?,?)
            """,
                (symbol, price, volume, score, rsi, macd, macd_sig, volume_spike, ts_utc),
            )
        score_txt = f"{float(score):.2f}" if score is not None else "-"
        logger.info(f"Signal saved: {symbol} | score={score_txt}")
    except Exception:
        logger.exception("Signal DB insert error:")


def last_signals(limit=5):
    with _conn() as con:
        cur = con.execute(
            """
            SELECT symbol, price, volume, score, ts_utc
            FROM signals ORDER BY id DESC LIMIT ?
        """,
            (limit,),
        )
        return cur.fetchall()


def trade_open(symbol, side, entry, size, qty, tp1, tp2, sl, opened_at):
    try:
        with _conn() as con:
            con.execute(
                """
                INSERT INTO trades
                (symbol, side, entry, size, qty, tp1, tp2, sl, status, opened_at, last_price, last_update)
                VALUES (?,?,?,?,?,?,?,?, 'OPEN', ?, ?, ?)
            """,
                (symbol, side, entry, size, qty, tp1, tp2, sl, opened_at, entry, opened_at),
            )
    except Exception:
        logger.exception("Trade open error:")


def trade_mark_partial(symbol, qty_delta, last_price, now_ts):
    try:
        with _conn() as con:
            con.execute(
                """
                UPDATE trades
                SET filled_tp1_qty = filled_tp1_qty + ?,
                    status = CASE WHEN filled_tp1_qty + ? >= qty THEN 'CLOSED' ELSE 'PARTIAL' END,
                    last_price=?, last_update=?
                WHERE symbol=? AND status IN ('OPEN','PARTIAL')
            """,
                (qty_delta, qty_delta, last_price, now_ts, symbol),
            )
    except Exception:
        logger.exception("Trade partial error:")


def trade_close_all(symbol, last_price, now_ts, realized_pnl_usd, realized_pnl_pct):
    try:
        with _conn() as con:
            con.execute(
                """
                UPDATE trades
                SET status='CLOSED', closed_at=?, last_price=?, last_update=?, pnl_usd=?, pnl_pct=?
                WHERE symbol=? AND status IN ('OPEN','PARTIAL')
            """,
                (now_ts, last_price, now_ts, realized_pnl_usd, realized_pnl_pct, symbol),
            )
    except Exception:
        logger.exception("Trade close error:")


def get_open_trades():
    with _conn() as con:
        return con.execute(
            """
            SELECT id, symbol, side, entry, size, qty, tp1, tp2, sl,
                   filled_tp1_qty, status, opened_at, last_price
            FROM trades WHERE status IN ('OPEN','PARTIAL')
        """
        ).fetchall()


def recent_trades(limit=10):
    with _conn() as con:
        return con.execute(
            """
            SELECT symbol, side, entry, tp1, tp2, sl, status,
                   opened_at, closed_at, pnl_usd, pnl_pct
            FROM trades ORDER BY id DESC LIMIT ?
        """,
            (limit,),
        ).fetchall()


def pnl_summary():
    with _conn() as con:
        row = con.execute(
            """
            SELECT COUNT(*),
                   SUM(CASE WHEN pnl_usd>0 THEN 1 ELSE 0 END),
                   SUM(CASE WHEN pnl_usd<=0 THEN 1 ELSE 0 END),
                   COALESCE(SUM(pnl_usd),0)
            FROM trades WHERE status='CLOSED'
        """
        ).fetchone()
    n, w, l, p = row if row else (0, 0, 0, 0.0)
    return {
        "closed": n,
        "wins": w,
        "losses": l,
        "winrate": (w / n * 100.0 if n else 0.0),
        "pnl_usd": p,
    }
