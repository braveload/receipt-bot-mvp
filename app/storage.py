"""로컬은 SQLite, 운영은 ``DATABASE_URL`` 기반 PostgreSQL 저장소."""
from __future__ import annotations

import hashlib
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
                    image_content BYTEA,
                    image_content_type TEXT,
                    image_sha256 TEXT,
                    supply_amount INTEGER,
                    vat_amount INTEGER,
                    status TEXT NOT NULL DEFAULT 'confirmed',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL DEFAULT ''
                )
                """
            )
            conn.execute(
                "ALTER TABLE receipts ADD COLUMN IF NOT EXISTS status TEXT NOT NULL DEFAULT 'confirmed'"
            )
            conn.execute(
                "ALTER TABLE receipts ADD COLUMN IF NOT EXISTS updated_at TEXT NOT NULL DEFAULT ''"
            )
            conn.execute("ALTER TABLE receipts ADD COLUMN IF NOT EXISTS image_content BYTEA")
            conn.execute("ALTER TABLE receipts ADD COLUMN IF NOT EXISTS image_content_type TEXT")
            conn.execute("ALTER TABLE receipts ADD COLUMN IF NOT EXISTS image_sha256 TEXT")
            conn.execute("ALTER TABLE receipts ADD COLUMN IF NOT EXISTS supply_amount INTEGER")
            conn.execute("ALTER TABLE receipts ADD COLUMN IF NOT EXISTS vat_amount INTEGER")
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_receipts_user_image_hash "
                "ON receipts(kakao_user_id, image_sha256)"
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS inquiries (
                    id BIGSERIAL PRIMARY KEY,
                    reference TEXT NOT NULL UNIQUE,
                    name TEXT NOT NULL,
                    contact TEXT NOT NULL,
                    message TEXT NOT NULL,
                    client_hash TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'new',
                    email_status TEXT NOT NULL DEFAULT 'pending',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_inquiries_hash_created "
                "ON inquiries(client_hash, created_at)"
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id BIGSERIAL PRIMARY KEY,
                    email TEXT NOT NULL UNIQUE,
                    password_hash TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
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
                image_content BLOB,
                image_content_type TEXT,
                image_sha256 TEXT,
                supply_amount INTEGER,
                vat_amount INTEGER,
                status TEXT NOT NULL DEFAULT 'confirmed',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL DEFAULT ''
            )
            """
        )
        columns = {row["name"] for row in conn.execute("PRAGMA table_info(receipts)")}
        if "status" not in columns:
            conn.execute("ALTER TABLE receipts ADD COLUMN status TEXT NOT NULL DEFAULT 'confirmed'")
        if "updated_at" not in columns:
            conn.execute("ALTER TABLE receipts ADD COLUMN updated_at TEXT NOT NULL DEFAULT ''")
        if "image_content" not in columns:
            conn.execute("ALTER TABLE receipts ADD COLUMN image_content BLOB")
        if "image_content_type" not in columns:
            conn.execute("ALTER TABLE receipts ADD COLUMN image_content_type TEXT")
        if "image_sha256" not in columns:
            conn.execute("ALTER TABLE receipts ADD COLUMN image_sha256 TEXT")
        if "supply_amount" not in columns:
            conn.execute("ALTER TABLE receipts ADD COLUMN supply_amount INTEGER")
        if "vat_amount" not in columns:
            conn.execute("ALTER TABLE receipts ADD COLUMN vat_amount INTEGER")
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_receipts_user_image_hash "
            "ON receipts(kakao_user_id, image_sha256)"
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS inquiries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                reference TEXT NOT NULL UNIQUE,
                name TEXT NOT NULL,
                contact TEXT NOT NULL,
                message TEXT NOT NULL,
                client_hash TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'new',
                email_status TEXT NOT NULL DEFAULT 'pending',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_inquiries_hash_created "
            "ON inquiries(client_hash, created_at)"
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )


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


def save_receipt(
    kakao_user_id: str,
    data: ReceiptData,
    image_url: str = "",
    status: str = "confirmed",
    image_content: bytes | None = None,
    image_content_type: str | None = None,
) -> int:
    now = datetime.now(UTC).isoformat()
    image_sha256 = hashlib.sha256(image_content).hexdigest() if image_content else None
    with _connect() as conn:
        sql = """
            INSERT INTO receipts
                (kakao_user_id, merchant, amount, date, doc_type, category,
                 biz_or_personal, biz_reg_no, confidence, image_url, image_content,
                 image_content_type, image_sha256, supply_amount, vat_amount,
                 status, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        if _uses_postgres():
            sql = sql.replace("?", "%s") + " RETURNING id"
        cur = conn.execute(
            sql,
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
                image_content,
                image_content_type,
                image_sha256,
                data.supply_amount,
                data.vat_amount,
                status,
                now,
                now,
            ),
        )
        return cur.fetchone()["id"] if _uses_postgres() else cur.lastrowid


def create_draft_receipt(
    kakao_user_id: str,
    data: ReceiptData,
    image_url: str = "",
    image_content: bytes | None = None,
    image_content_type: str | None = None,
) -> int:
    """OCR 결과를 사용자가 확인하기 전 임시 상태로 저장한다."""
    with _connect() as conn:
        conn.execute(
            _sql("DELETE FROM receipts WHERE kakao_user_id = ? AND status = 'draft'"),
            (kakao_user_id,),
        )
    return save_receipt(
        kakao_user_id,
        data,
        image_url,
        status="draft",
        image_content=image_content,
        image_content_type=image_content_type,
    )


def get_pending_receipt(kakao_user_id: str) -> Mapping[str, Any] | None:
    with _connect() as conn:
        return conn.execute(
            _sql("""
            SELECT * FROM receipts
            WHERE kakao_user_id = ? AND status = 'draft'
            ORDER BY id DESC LIMIT 1
            """),
            (kakao_user_id,),
        ).fetchone()


def update_pending_receipt(kakao_user_id: str, changes: dict[str, object]) -> Mapping[str, Any] | None:
    allowed = {
        "merchant", "amount", "date", "doc_type", "category",
        "biz_or_personal", "biz_reg_no", "supply_amount", "vat_amount",
    }
    updates = {key: value for key, value in changes.items() if key in allowed}
    pending = get_pending_receipt(kakao_user_id)
    if pending is None or not updates:
        return pending

    assignments = ", ".join(f"{key} = {_placeholder()}" for key in updates)
    values = [*updates.values(), datetime.now(UTC).isoformat(), pending["id"], kakao_user_id]
    with _connect() as conn:
        conn.execute(
            _sql(f"UPDATE receipts SET {assignments}, updated_at = ? WHERE id = ? AND kakao_user_id = ?"),
            values,
        )
    return get_pending_receipt(kakao_user_id)


def discard_pending_receipt(kakao_user_id: str) -> bool:
    """확인 전 임시(draft) 영수증을 취소한다. 삭제된 게 있으면 True."""
    with _connect() as conn:
        cursor = conn.execute(
            _sql("DELETE FROM receipts WHERE kakao_user_id = ? AND status = 'draft'"),
            (kakao_user_id,),
        )
        return cursor.rowcount > 0


def confirm_pending_receipt(kakao_user_id: str) -> Mapping[str, Any] | None:
    pending = get_pending_receipt(kakao_user_id)
    if pending is None:
        return None
    with _connect() as conn:
        conn.execute(
            _sql("UPDATE receipts SET status = 'confirmed', updated_at = ? WHERE id = ?"),
            (datetime.now(UTC).isoformat(), pending["id"]),
        )
        return conn.execute(_sql("SELECT * FROM receipts WHERE id = ?"), (pending["id"],)).fetchone()


def get_receipts_for_month(kakao_user_id: str, yyyy_mm: str) -> list[Mapping[str, Any]]:
    with _connect() as conn:
        cur = conn.execute(
            _sql("""
            SELECT * FROM receipts
            WHERE kakao_user_id = ? AND status = 'confirmed' AND date LIKE ?
            ORDER BY date ASC
            """),
            (kakao_user_id, f"{yyyy_mm}%"),
        )
        return cur.fetchall()


def get_all_receipts(kakao_user_id: str) -> list[Mapping[str, Any]]:
    with _connect() as conn:
        cur = conn.execute(
            _sql("SELECT * FROM receipts WHERE kakao_user_id = ? AND status = 'confirmed' ORDER BY date ASC"),
            (kakao_user_id,),
        )
        return cur.fetchall()


def find_receipt_by_image(kakao_user_id: str, image_content: bytes) -> Mapping[str, Any] | None:
    image_sha256 = hashlib.sha256(image_content).hexdigest()
    with _connect() as conn:
        return conn.execute(
            _sql(
                "SELECT * FROM receipts WHERE kakao_user_id = ? AND image_sha256 = ? "
                "ORDER BY id DESC LIMIT 1"
            ),
            (kakao_user_id, image_sha256),
        ).fetchone()


def delete_latest_receipt(kakao_user_id: str) -> Mapping[str, Any] | None:
    """사용자의 가장 최근 확정 영수증 한 건을 영구 삭제한다."""
    with _connect() as conn:
        row = conn.execute(
            _sql(
                "SELECT * FROM receipts WHERE kakao_user_id = ? AND status = 'confirmed' "
                "ORDER BY id DESC LIMIT 1"
            ),
            (kakao_user_id,),
        ).fetchone()
        if row is not None:
            conn.execute(
                _sql("DELETE FROM receipts WHERE id = ? AND kakao_user_id = ?"),
                (row["id"], kakao_user_id),
            )
        return row


def create_inquiry(
    reference: str,
    name: str,
    contact: str,
    message: str,
    client_hash: str,
) -> None:
    now = datetime.now(UTC).isoformat()
    with _connect() as conn:
        conn.execute(
            _sql(
                """
                INSERT INTO inquiries
                    (reference, name, contact, message, client_hash, status,
                     email_status, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, 'new', 'pending', ?, ?)
                """
            ),
            (reference, name, contact, message, client_hash, now, now),
        )


def get_inquiry(reference: str) -> Mapping[str, Any] | None:
    with _connect() as conn:
        return conn.execute(
            _sql("SELECT * FROM inquiries WHERE reference = ?"),
            (reference,),
        ).fetchone()


def count_recent_inquiries(client_hash: str, since: str) -> int:
    with _connect() as conn:
        row = conn.execute(
            _sql(
                "SELECT COUNT(*) AS inquiry_count FROM inquiries "
                "WHERE client_hash = ? AND created_at >= ?"
            ),
            (client_hash, since),
        ).fetchone()
        return int(row["inquiry_count"])


def update_inquiry_email_status(reference: str, email_status: str) -> None:
    if email_status not in {"pending", "sent", "failed"}:
        raise ValueError("invalid inquiry email status")
    with _connect() as conn:
        conn.execute(
            _sql(
                "UPDATE inquiries SET email_status = ?, updated_at = ? "
                "WHERE reference = ?"
            ),
            (email_status, datetime.now(UTC).isoformat(), reference),
        )


def delete_expired_inquiries(cutoff: str) -> int:
    with _connect() as conn:
        cursor = conn.execute(
            _sql("DELETE FROM inquiries WHERE created_at < ?"),
            (cutoff,),
        )
        return max(cursor.rowcount, 0)


def _placeholder() -> str:
    return "%s" if _uses_postgres() else "?"


def _sql(query: str) -> str:
    return query.replace("?", "%s") if _uses_postgres() else query


def create_user(email: str, password_hash: str) -> int:
    """이메일 중복 시 ValueError."""
    now = datetime.now(UTC).isoformat()
    sql = "INSERT INTO users (email, password_hash, created_at) VALUES (?, ?, ?)"
    if _uses_postgres():
        sql = sql.replace("?", "%s") + " RETURNING id"
        import psycopg

        try:
            with _connect() as conn:
                cur = conn.execute(sql, (email, password_hash, now))
                return cur.fetchone()["id"]
        except psycopg.errors.UniqueViolation as exc:
            raise ValueError("already registered") from exc

    try:
        with _connect() as conn:
            cur = conn.execute(sql, (email, password_hash, now))
            return cur.lastrowid
    except sqlite3.IntegrityError as exc:
        raise ValueError("already registered") from exc


def get_user_by_email(email: str) -> Mapping[str, Any] | None:
    with _connect() as conn:
        return conn.execute(_sql("SELECT * FROM users WHERE email = ?"), (email,)).fetchone()


def get_user_by_id(user_id: int) -> Mapping[str, Any] | None:
    with _connect() as conn:
        return conn.execute(_sql("SELECT * FROM users WHERE id = ?"), (user_id,)).fetchone()

