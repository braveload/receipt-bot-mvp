from fastapi.testclient import TestClient

from app import contact, main, storage


def contact_payload(**overrides):
    payload = {
        "name": "리로상사",
        "contact": "test@example.com",
        "message": "영수증봇 테스트 참여 방법을 알고 싶습니다.",
        "privacy_consent": True,
        "website": "",
    }
    payload.update(overrides)
    return payload


def test_contact_is_saved_before_unconfigured_email_is_marked_failed(monkeypatch):
    monkeypatch.setenv("CONTACT_HASH_SECRET", "contact-test-secret")
    client = TestClient(main.app)

    response = client.post("/api/contact", json=contact_payload())

    assert response.status_code == 201
    assert response.json()["ok"] is True
    reference = response.json()["reference"]
    inquiry = storage.get_inquiry(reference)
    assert inquiry["name"] == "리로상사"
    assert inquiry["contact"] == "test@example.com"
    assert inquiry["status"] == "new"
    assert inquiry["email_status"] == "failed"
    assert inquiry["client_hash"] != "testclient"


def test_contact_validation_honeypot_and_rate_limit(monkeypatch):
    monkeypatch.setenv("CONTACT_HASH_SECRET", "contact-test-secret")
    client = TestClient(main.app)

    assert client.post(
        "/api/contact",
        json=contact_payload(privacy_consent=False),
    ).status_code == 422
    assert client.post(
        "/api/contact",
        json=contact_payload(message="짧음"),
    ).status_code == 422

    assert client.post(
        "/api/contact",
        json=contact_payload(name=" 함 "),
    ).status_code == 422

    honeypot = client.post(
        "/api/contact",
        json=contact_payload(website="https://spam.example"),
    )
    assert honeypot.status_code == 201
    assert honeypot.json()["reference"] == "RW-RECEIVED"

    for index in range(5):
        response = client.post(
            "/api/contact",
            json=contact_payload(message=f"정상적인 테스트 문의 내용입니다. 번호 {index}"),
        )
        assert response.status_code == 201
    limited = client.post("/api/contact", json=contact_payload())
    assert limited.status_code == 429


def test_contact_smtp_success_updates_status(monkeypatch):
    monkeypatch.setenv("CONTACT_HASH_SECRET", "contact-test-secret")
    monkeypatch.setenv("SMTP_USERNAME", "sender@naver.com")
    monkeypatch.setenv("SMTP_PASSWORD", "app-password")
    monkeypatch.setenv("CONTACT_EMAIL_TO", "reromoon@naver.com")
    sent_messages = []

    class FakeSMTP:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def login(self, username, password):
            assert username == "sender@naver.com"
            assert password == "app-password"

        def send_message(self, message):
            sent_messages.append(message)

    monkeypatch.setattr(contact.smtplib, "SMTP_SSL", FakeSMTP)
    client = TestClient(main.app)

    response = client.post("/api/contact", json=contact_payload())
    reference = response.json()["reference"]

    assert response.status_code == 201
    assert storage.get_inquiry(reference)["email_status"] == "sent"
    assert len(sent_messages) == 1
    assert reference in sent_messages[0]["Subject"]


def test_expired_inquiry_cleanup():
    storage.create_inquiry(
        reference="RW-OLD",
        name="오래된 문의",
        contact="old@example.com",
        message="삭제 대상이 되는 오래된 문의 내용입니다.",
        client_hash="old-hash",
    )
    assert storage.delete_expired_inquiries("9999-01-01T00:00:00+00:00") == 1
    assert storage.get_inquiry("RW-OLD") is None
