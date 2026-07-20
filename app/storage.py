"""로컬은 SQLite, 운영은 ``DATABASE_URL`` 기반 PostgreSQL 저장소."""
from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterator, Mapping

from .models import ReceiptData

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "receipts.db"


def init_db() -> None:
    if _uses_postgres():
        with _connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS receipts (
                    id BIGSERIAL PRIMARY KEY,
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
                    status TEXT NOT NULL DEFAULT 'confirmed',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL DEFAULT ''
                )
                """
            )
            conn.execute("ALTER TABLE receipts ADD COLUMN IF NOT EXISTS status TEXT NOT NULL DEFAULT 'confirmed'")
            conn.execute("ALTER TABLE receipts ADD COLUMN IF NOT EXISTS updated_at TEXT NOT NULL DEFAULT ''")
        return

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
                status TEXT NOT NULL DEFAULT 'confirmed',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL DEFAULT ''
            )
            """
        )
        columns = {row[1] for row in conn.execute("PRAGMA table_info(receipts)")}
        if "status" not in columns:
            conn.execute("ALTER TABLE receipts ADD COLUMN status TEXT NOT NULL DEFAULT 'confirmed'")
        if "updated_at" not in columns:
            conn.execute("ALTER TABLE receipts ADD COLUMN updated_at TEXT NOT NULL DEFAULT ''")


def _uses_postgres() -> bool:
    return bool(os.environ.get("DATABASE_URL"))


@contextmanager
def _connect() -> Iterator[Any]:
    if _uses_postgres():
        import psycopg
        from psycopg.rows import dict_row

        conn = psycopg.connect(os.environ["DATABASE_URL"], row_factory=dict_row)
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()
        return

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def save_receipt(kakao_user_id: str, data: ReceiptData, image_url: str = "", status: str = "confirmed") -> int:
    now = datetime.now(UTC).isoformat()
    with _connect() as conn:
        sql = """
            INSERT INTO receipts
                (kakao_user_id, merchant, amount, date, doc_type, category,
                 biz_or_personal, biz_reg_no, confidence, image_url, status, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        if _uses_postgres():
            sql = sql.replace("?", "%s") + " RETURNING id"
        cur = conn.execute(sql, (kakao_user_id, data.merchant, data.amount, data.date, data.doc_type,
            data.category, data.biz_or_personal, data.biz_reg_no, data.confidence, image_url, status, now, now))
        return cur.fetchone()["id"] if _uses_postgres() else cur.lastrowid


def create_draft_receipt(kakao_user_id: str, data: ReceiptData, image_url: str = "") -> int:
    """OCR 결과를 사용자가 확인하기 전 임시 상태로 저장한다."""
    with _connect() as conn:
        conn.execute(_sql("DELETE FROM receipts WHERE kakao_user_id = ? AND status = 'draft'"), (kakao_user_id,))
    return save_receipt(kakao_user_id, data, image_url, status="draft")


def get_pending_receipt(kakao_user_id: str) -> Mapping[str, Any] | None:
    with _connect() as conn:
        return conn.execute(_sql("""SELECT * FROM receipts WHERE kakao_user_id = ? AND status = 'draft' ORDER BY id DESC LIMIT 1"""), (kakao_user_id,)).fetchone()


def update_pending_receipt(kakao_user_id: str, changes: dict[str, object]) -> Mapping[str, Any] | None:
    allowed = {"merchant", "amount", "date", "doc_type", "category", "biz_or_personal", "biz_reg_no"}
    updates = {key: value for key, value in changes.items() if key in allowed}
    pending = get_pending_receipt(kakao_user_id)
    if pending is None or not updates:
        return pending
    assignments = ", ".join(f"{key} = {_placeholder()}" for key in updates)
    values = [*updates.values(), datetime.now(UTC).isoformat(), pending["id"], kakao_user_id]
    with _connect() as conn:
        conn.execute(_sql(f"UPDATE receipts SET {assignments}, updated_at = ? WHERE id = ? AND kakao_user_id = ?"), values)
    return get_pending_receipt(kakao_user_id)


def confirm_pending_receipt(kakao_user_id: str) -> Mapping[str, Any] | None:
    pending = get_pending_receipt(kakao_user_id)
    if pending is None:
        return None
    with _connect() as conn:
        conn.execute(_sql("UPDATE receipts SET status = 'confirmed', updated_at = ? WHERE id = ?"), (datetime.now(UTC).isoformat(), pending["id"]))
        return conn.execute(_sql("SELECT * FROM receipts WHERE id = ?"), (pending["id"],)).fetchone()


def get_receipts_for_month(kakao_user_id: str, yyyy_mm: str) -> list[Mapping[str, Any]]:
    with _connect() as conn:
        return conn.execute(_sql("""SELECT * FROM receipts WHERE kakao_user_id = ? AND status = 'confirmed' AND date LIKE ? ORDER BY date ASC"""), (kakao_user_id, f"{yyyy_mm}%")).fetchall()


def get_all_receipts(kakao_user_id: str) -> list[Mapping[str, Any]]:
    with _connect() as conn:
        return conn.execute(_sql("SELECT * FROM receipts WHERE kakao_user_id = ? AND status = 'confirmed' ORDER BY date ASC"), (kakao_user_id,)).fetchall()


def _placeholder() -> str:
    return "%s" if _uses_postgres() else "?"


def _sql(query: str) -> str:
    return query.replace("?", "%s") if _uses_postgres() else query
