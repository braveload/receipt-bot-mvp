from datetime import UTC, datetime
from urllib.parse import urlsplit

from fastapi.testclient import TestClient

from app import main, storage
from app.extractor import ExtractionError
from app.models import ReceiptData


def image_payload(user_id="test-user", image_url="https://example.com/receipt.jpg"):
    return {
        "userRequest": {
            "utterance": "(이미지 전송)",
            "user": {"properties": {"plusfriendUserKey": user_id}},
        },
        "action": {"params": {"secureimage": image_url}},
    }


def text_payload(text, user_id="test-user"):
    return {
        "userRequest": {
            "utterance": text,
            "user": {"properties": {"plusfriendUserKey": user_id}},
        },
        "action": {"params": {}},
    }


def response_text(response):
    return response.json()["template"]["outputs"][0]["simpleText"]["text"]


def test_health():
    response = TestClient(main.app).get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_malformed_json_returns_kakao_response():
    response = TestClient(main.app).post(
        "/kakao/webhook",
        content=b"not-json{{{",
        headers={"content-type": "application/json"},
    )

    assert response.status_code == 200
    assert "다시 시도" in response_text(response)


def test_missing_user_id_does_not_use_shared_fallback_identity():
    payload = text_payload("안녕")
    payload["userRequest"]["user"]["properties"] = {}

    response = TestClient(main.app).post("/kakao/webhook", json=payload)

    assert response.status_code == 200
    assert "사용자 정보를 확인하지 못했어요" in response_text(response)


def test_original_image_is_stored_privately(monkeypatch):
    monkeypatch.setenv("STORE_RECEIPT_IMAGES", "true")
    monkeypatch.setattr(
        main,
        "download_private_image",
        lambda url: (b"private-receipt-image", "image/jpeg"),
    )

    response = TestClient(main.app).post("/kakao/webhook", json=image_payload())
    pending = storage.get_pending_receipt("test-user")

    assert response.status_code == 200
    assert pending["image_url"] == ""
    assert pending["image_content"] == b"private-receipt-image"
    assert pending["image_content_type"] == "image/jpeg"
    assert len(pending["image_sha256"]) == 64


def test_private_image_is_downloaded_once_and_duplicate_is_blocked(monkeypatch):
    calls = {"download": 0, "extract_bytes": 0}

    def download(url):
        calls["download"] += 1
        return b"same-private-image", "image/jpeg"

    class BytesExtractor:
        def extract(self, image_url):
            raise AssertionError("저장 모드에서 URL 재다운로드가 발생했습니다.")

        def extract_bytes(self, image, media_type):
            calls["extract_bytes"] += 1
            return ReceiptData("중복상점", 11000, "2026-07-24", "카드전표", "기타", "개인")

    monkeypatch.setenv("STORE_RECEIPT_IMAGES", "true")
    monkeypatch.setattr(main, "download_private_image", download)
    monkeypatch.setattr(main, "get_extractor", lambda: BytesExtractor())
    client = TestClient(main.app)

    first = client.post("/kakao/webhook", json=image_payload(user_id="duplicate-user"))
    second = client.post("/kakao/webhook", json=image_payload(user_id="duplicate-user"))

    assert first.status_code == 200
    assert "이미 등록한 영수증" in response_text(second)
    assert calls == {"download": 2, "extract_bytes": 1}


def test_receipt_review_edit_confirm_summary_and_signed_excel(tmp_path, monkeypatch):
    client = TestClient(main.app)
    extracted = client.post("/kakao/webhook", json=image_payload())
    assert extracted.status_code == 200
    assert "스타벅스 강남점" in response_text(extracted)
    assert "저장" in [item["label"] for item in extracted.json()["template"]["quickReplies"]]

    assert storage.get_all_receipts("test-user") == []
    pending = storage.get_pending_receipt("test-user")
    assert pending["status"] == "draft"

    edited = client.post(
        "/kakao/webhook",
        json=text_payload("수정 상호명=스타벅스 선릉점; 금액=5,000; 카테고리=식비; 구분=개인"),
    )
    assert edited.status_code == 200
    assert "스타벅스 선릉점" in response_text(edited)
    assert "5,000원" in response_text(edited)

    confirmed = client.post("/kakao/webhook", json=text_payload("저장"))
    assert confirmed.status_code == 200
    assert "저장 완료" in response_text(confirmed)

    rows = storage.get_all_receipts("test-user")
    assert len(rows) == 1
    assert rows[0]["merchant"] == "스타벅스 선릉점"
    assert rows[0]["amount"] == 5000

    summary = client.post("/kakao/webhook", json=text_payload("이번달"))
    assert summary.status_code == 200
    assert "총 1건" in response_text(summary)
    assert "5,000원" in response_text(summary)

    fake_main_file = tmp_path / "project" / "app" / "main.py"
    monkeypatch.setattr(main, "Path", lambda *_: fake_main_file)
    link_response = client.post("/kakao/webhook", json=text_payload("신고파일"))
    link = response_text(link_response).splitlines()[-1]
    parsed = urlsplit(link)
    excel = client.get(f"{parsed.path}?{parsed.query}")
    assert excel.status_code == 200
    assert excel.headers["content-type"].startswith(
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    assert len(excel.content) > 1000


def test_signed_excel_rejects_invalid_and_expired_links():
    client = TestClient(main.app)
    now = int(datetime.now(UTC).timestamp())

    invalid = client.get(
        f"/report/test-user/excel?expires={now + 60}&signature=bad&month="
    )
    assert invalid.status_code == 403

    expired_signature = main._report_signature("test-user", "", now - 1)
    expired = client.get(
        f"/report/test-user/excel?expires={now - 1}&signature={expired_signature}&month="
    )
    assert expired.status_code == 410


def test_edit_validation_and_no_pending_receipt_messages():
    client = TestClient(main.app)

    no_pending = client.post("/kakao/webhook", json=text_payload("저장"))
    assert "저장할 영수증이 없어요" in response_text(no_pending)

    client.post("/kakao/webhook", json=image_payload())
    invalid = client.post("/kakao/webhook", json=text_payload("수정 금액=abc"))
    assert "금액은" in response_text(invalid)


def test_tax_total_must_match_before_save():
    client = TestClient(main.app)
    client.post("/kakao/webhook", json=image_payload(user_id="tax-user"))
    client.post(
        "/kakao/webhook",
        json=text_payload("수정 금액=11000; 공급가액=9000; 부가세=1000", user_id="tax-user"),
    )

    rejected = client.post("/kakao/webhook", json=text_payload("저장", user_id="tax-user"))
    assert "합계가 총액" in response_text(rejected)
    assert storage.get_all_receipts("tax-user") == []

    client.post(
        "/kakao/webhook",
        json=text_payload("수정 공급가액=10000", user_id="tax-user"),
    )
    saved = client.post("/kakao/webhook", json=text_payload("저장", user_id="tax-user"))
    assert "저장 완료" in response_text(saved)


def test_delete_requires_confirmation_and_is_scoped_to_user():
    client = TestClient(main.app)
    for user_id in ("delete-user", "other-user"):
        client.post("/kakao/webhook", json=image_payload(user_id=user_id))
        client.post("/kakao/webhook", json=text_payload("저장", user_id=user_id))

    warning = client.post("/kakao/webhook", json=text_payload("삭제", user_id="delete-user"))
    assert "삭제확정" in response_text(warning)
    assert len(storage.get_all_receipts("delete-user")) == 1

    deleted = client.post("/kakao/webhook", json=text_payload("삭제확정", user_id="delete-user"))
    assert "삭제했어요" in response_text(deleted)
    assert storage.get_all_receipts("delete-user") == []
    assert len(storage.get_all_receipts("other-user")) == 1


def test_extraction_failure_is_user_friendly(monkeypatch, capsys):
    class FailingExtractor:
        def extract(self, image_url):
            raise ExtractionError("forced failure")

    monkeypatch.setattr(main, "get_extractor", lambda: FailingExtractor())
    response = TestClient(main.app).post("/kakao/webhook", json=image_payload())

    assert response.status_code == 200
    assert "실패" in response_text(response)
    log = capsys.readouterr().out
    assert "test-user" not in log
    assert "user_hash=" in log


def test_missing_google_key_is_user_friendly(monkeypatch):
    from app import extractor

    monkeypatch.setenv("EXTRACTOR", "google")
    extractor._EXTRACTOR_SINGLETON = None
    response = TestClient(main.app).post("/kakao/webhook", json=image_payload())

    assert response.status_code == 200
    assert "일시적인 오류" in response_text(response)


def test_webhook_secret(monkeypatch):
    monkeypatch.setenv("WEBHOOK_SECRET", "s3cr3t")
    client = TestClient(main.app)

    assert client.post("/kakao/webhook", json=text_payload("안녕")).status_code == 401
    assert (
        client.post(
            "/kakao/webhook",
            json=text_payload("안녕"),
            headers={"X-Webhook-Secret": "wrong"},
        ).status_code
        == 401
    )
    assert (
        client.post(
            "/kakao/webhook",
            json=text_payload("안녕"),
            headers={"X-Webhook-Secret": "s3cr3t"},
        ).status_code
        == 200
    )
