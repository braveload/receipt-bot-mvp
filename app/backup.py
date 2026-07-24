"""영수증 데이터베이스의 gzip JSON 백업과 복구."""
from __future__ import annotations

import argparse
import base64
import gzip
import json
import os
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Mapping

from . import storage

BACKUP_VERSION = 1
BACKUP_COLUMNS = (
    "kakao_user_id",
    "merchant",
    "amount",
    "date",
    "doc_type",
    "category",
    "biz_or_personal",
    "biz_reg_no",
    "confidence",
    "image_url",
    "image_content",
    "image_content_type",
    "image_sha256",
    "status",
    "created_at",
    "updated_at",
)


def _serializable_row(row: Mapping[str, Any]) -> dict[str, Any]:
    result = {column: row[column] for column in BACKUP_COLUMNS}
    image = result["image_content"]
    if image is not None:
        result["image_content"] = base64.b64encode(bytes(image)).decode("ascii")
    return result


def export_database(path: Path) -> Path:
    """전체 영수증을 원자적으로 gzip JSON 파일에 백업한다."""
    storage.init_db()
    with storage._connect() as conn:
        rows = conn.execute(
            f"SELECT {', '.join(BACKUP_COLUMNS)} FROM receipts ORDER BY id"
        ).fetchall()

    payload = {
        "version": BACKUP_VERSION,
        "created_at": datetime.now(UTC).isoformat(),
        "receipts": [_serializable_row(row) for row in rows],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False, suffix=".tmp") as temp:
        temp_path = Path(temp.name)
    try:
        with gzip.open(temp_path, "wt", encoding="utf-8") as stream:
            json.dump(payload, stream, ensure_ascii=False, separators=(",", ":"))
        os.chmod(temp_path, 0o600)
        temp_path.replace(path)
    finally:
        temp_path.unlink(missing_ok=True)
    return path


def restore_database(path: Path) -> int:
    """빈 데이터베이스에 백업을 복구하고 복구 건수를 반환한다."""
    with gzip.open(path, "rt", encoding="utf-8") as stream:
        payload = json.load(stream)
    if payload.get("version") != BACKUP_VERSION:
        raise ValueError("지원하지 않는 백업 버전입니다.")

    storage.init_db()
    with storage._connect() as conn:
        count_row = conn.execute("SELECT COUNT(*) AS count FROM receipts").fetchone()
        if count_row["count"]:
            raise ValueError("복구 대상 데이터베이스가 비어 있지 않습니다.")

        placeholders = ", ".join(storage._placeholder() for _ in BACKUP_COLUMNS)
        sql = f"INSERT INTO receipts ({', '.join(BACKUP_COLUMNS)}) VALUES ({placeholders})"
        for row in payload.get("receipts", []):
            image = row.get("image_content")
            row["image_content"] = base64.b64decode(image) if image is not None else None
            conn.execute(sql, tuple(row.get(column) for column in BACKUP_COLUMNS))
    return len(payload.get("receipts", []))


def main() -> None:
    parser = argparse.ArgumentParser(description="영수증봇 DB 백업·복구")
    subparsers = parser.add_subparsers(dest="command", required=True)
    for command in ("export", "restore"):
        command_parser = subparsers.add_parser(command)
        command_parser.add_argument("path", type=Path)
    args = parser.parse_args()

    if args.command == "export":
        result = export_database(args.path)
        print(f"백업 완료: {result}")
    else:
        restored = restore_database(args.path)
        print(f"복구 완료: {restored}건")


if __name__ == "__main__":
    main()
