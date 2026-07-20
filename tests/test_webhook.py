from datetime import UTC, datetime
from urllib.parse import urlsplit

from fastapi.testclient import TestClient

from app import main, storage
from app.extractor import ExtractionError


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


def test_extraction_failure_is_user_friendly(monkeypatch):
    class FailingExtractor:
        def extract(self, image_url):
            raise ExtractionError("forced failure")

    monkeypatch.setattr(main, "get_extractor", lambda: FailingExtractor())
    response = TestClient(main.app).post("/kakao/webhook", json=image_payload())

    assert response.status_code == 200
    assert "실패" in response_text(response)


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
