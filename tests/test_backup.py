from app import backup, storage
from app.models import ReceiptData


def test_backup_restore_round_trip(tmp_path):
    image = b"private-image-bytes"
    storage.save_receipt(
        "backup-user",
        ReceiptData(
            merchant="백업상점",
            amount=12000,
            date="2026-07-24",
            doc_type="카드전표",
            category="소모품비",
            biz_or_personal="사업",
            confidence=0.9,
        ),
        image_content=image,
        image_content_type="image/jpeg",
    )
    backup_path = backup.export_database(tmp_path / "backup.json.gz")

    storage.DB_PATH = tmp_path / "restored.db"
    restored = backup.restore_database(backup_path)
    rows = storage.get_all_receipts("backup-user")

    assert restored == 1
    assert rows[0]["merchant"] == "백업상점"
    assert rows[0]["image_content"] == image
    assert len(rows[0]["image_sha256"]) == 64


def test_restore_requires_empty_database(tmp_path):
    backup_path = backup.export_database(tmp_path / "empty-backup.json.gz")
    storage.save_receipt(
        "existing-user",
        ReceiptData("기존상점", 1000, "2026-07-24", "카드전표", "기타", "개인"),
    )

    try:
        backup.restore_database(backup_path)
    except ValueError as exc:
        assert "비어 있지 않습니다" in str(exc)
    else:
        raise AssertionError("비어 있지 않은 DB 복구가 차단되지 않았습니다.")
