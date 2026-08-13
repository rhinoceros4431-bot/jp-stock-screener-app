"""SQLite を使ったプッシュ通知購読の永続化。"""
from __future__ import annotations

import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent / "app.db"


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_conn()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS subscriptions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            endpoint TEXT UNIQUE NOT NULL,
            p256dh TEXT NOT NULL,
            auth TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)
    conn.commit()
    conn.close()


def add_subscription(endpoint: str, p256dh: str, auth: str):
    conn = get_conn()
    conn.execute(
        "INSERT OR IGNORE INTO subscriptions (endpoint, p256dh, auth) VALUES (?, ?, ?)",
        (endpoint, p256dh, auth),
    )
    conn.commit()
    conn.close()


def remove_subscription(endpoint: str):
    conn = get_conn()
    conn.execute("DELETE FROM subscriptions WHERE endpoint = ?", (endpoint,))
    conn.commit()
    conn.close()


def list_subscriptions() -> list[dict]:
    conn = get_conn()
    rows = conn.execute("SELECT endpoint, p256dh, auth FROM subscriptions").fetchall()
    conn.close()
    return [dict(r) for r in rows]
