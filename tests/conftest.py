import os

import pytest


@pytest.fixture(autouse=True)
def isolated_runtime(tmp_path, monkeypatch):
    """각 테스트가 실제 data/receipts.db와 환경변수를 건드리지 않게 격리한다."""
    from app import extractor, storage

    monkeypatch.setattr(storage, "DB_PATH", tmp_path / "receipts.db")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("EXTRACTOR", "mock")
    monkeypatch.delenv("WEBHOOK_SECRET", raising=False)
    monkeypatch.delenv("GOOGLE_VISION_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("STORE_RECEIPT_IMAGES", raising=False)
    monkeypatch.setenv("REPORT_SIGNING_SECRET", "test-report-secret")
    monkeypatch.setenv("REPORT_LINK_TTL_SECONDS", "600")
    extractor._EXTRACTOR_SINGLETON = None
    storage.init_db()

    yield

    extractor._EXTRACTOR_SINGLETON = None
    os.environ.pop("DOTENV_CHECK_VALUE", None)
