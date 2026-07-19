"""SQLite 기반 저장소. MVP 단계 최소 구현 (실서비스 전환 시 Postgres 등으로 교체 권장)."""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Iterator

from .models import ReceiptData

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "receipts.db"


def init_db() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with _connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS receipts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                kakao_user_id TEXT NOT NULL,
                merchant TEXT NOT NULL,
                amount INTEGER NOT NULL,
                date TEXT NOT NULL,
                doc_type TEXT NOT NULL,
                category TEXT NOT NULL,
                biz_or_personal TEXT NOT NULL,
                biz_reg_no TEXT,
                confidence REAL,
                image_url TEXT,
                created_at TEXT NOT NULL
            )
            """
        )


@contextmanager
def _connect() -> Iterator[sqlite3.Connection]:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def save_receipt(kakao_user_id: str, data: ReceiptData, image_url: str = "") -> int:
    with _connect() as conn:
        cur = conn.execute(
            """
            INSERT INTO receipts
                (kakao_user_id, merchant, amount, date, doc_type, category,
                 biz_or_personal, biz_reg_no, confidence, image_url, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                kakao_user_id,
                data.merchant,
                data.amount,
                data.date,
                data.doc_type,
                data.category,
                data.biz_or_personal,
                data.biz_reg_no,
                data.confidence,
                image_url,
                datetime.utcnow().isoformat(),
            ),
        )
        return cur.lastrowid


def get_receipts_for_month(kakao_user_id: str, yyyy_mm: str) -> list[sqlite3.Row]:
    with _connect() as conn:
        cur = conn.execute(
            """
            SELECT * FROM receipts
            WHERE kakao_user_id = ? AND date LIKE ?
            ORDER BY date ASC
            """,
            (kakao_user_id, f"{yyyy_mm}%"),
        )
        return cur.fetchall()


def get_all_receipts(kakao_user_id: str) -> list[sqlite3.Row]:
    with _connect() as conn:
        cur = conn.execute(
            "SELECT * FROM receipts WHERE kakao_user_id = ? ORDER BY date ASC",
            (kakao_user_id,),
        )
        return cur.fetchall()
