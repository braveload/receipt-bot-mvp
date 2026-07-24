"""웹앱/안드로이드 REST API (자체 로그인 + 영수증 CRUD)."""
from __future__ import annotations

import io

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

# 1x1 최소 JPEG (magic bytes 통과용)
_TINY_JPEG = bytes.fromhex(
    "ffd8ffe000104a46494600010100000100010000ffdb004300030202020202"
    "03020202030303030405080505040404050a070706080c0a0c0c0b0a0b0b0d"
    "0e12100d0e110e0b0b1016101113141515150c0f171816141812141514ffc9"
    "0000000000000000000000000000000000000000000000000000000000ffda"
    "0008010100003f00d2cf20ffd9"
)


def _register(email="test@example.com", password="testpass123") -> str:
    r = client.post("/api/auth/register", json={"email": email, "password": password})
    assert r.status_code == 201, r.text
    return r.json()["token"]


def test_register_and_login():
    token = _register("a@example.com", "password123")
    assert token

    r = client.post("/api/auth/login", json={"email": "a@example.com", "password": "password123"})
    assert r.status_code == 200
    assert r.json()["user"]["email"] == "a@example.com"

    r = client.post("/api/auth/login", json={"email": "a@example.com", "password": "wrong"})
    assert r.status_code == 401


def test_duplicate_register_rejected():
    _register("dup@example.com", "password123")
    r = client.post("/api/auth/register", json={"email": "dup@example.com", "password": "password123"})
    assert r.status_code == 409


def test_me_requires_auth():
    r = client.get("/api/me")
    assert r.status_code == 401


def test_upload_correct_confirm_summary_export_flow():
    token = _register("flow@example.com", "password123")
    headers = {"Authorization": f"Bearer {token}"}

    r = client.get("/api/me", headers=headers)
    assert r.status_code == 200
    assert r.json()["email"] == "flow@example.com"

    r = client.post(
        "/api/receipts/upload",
        headers=headers,
        files={"file": ("receipt.jpg", io.BytesIO(_TINY_JPEG), "image/jpeg")},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["duplicate"] is False
    receipt = body["receipt"]
    assert receipt["status"] == "draft"

    r = client.get("/api/receipts/pending", headers=headers)
    assert r.status_code == 200
    assert r.json()["id"] == receipt["id"]

    r = client.patch(
        "/api/receipts/pending",
        headers=headers,
        json={"changes": {"merchant": "테스트상점", "amount": 12345, "category": "식비", "biz_or_personal": "사업"}},
    )
    assert r.status_code == 200, r.text
    assert r.json()["merchant"] == "테스트상점"
    assert r.json()["amount"] == 12345

    r = client.patch(
        "/api/receipts/pending",
        headers=headers,
        json={"changes": {"category": "존재하지않는카테고리"}},
    )
    assert r.status_code == 422

    r = client.post("/api/receipts/confirm", headers=headers)
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "confirmed"

    month = receipt["date"][:7]
    r = client.get(f"/api/receipts?month={month}", headers=headers)
    assert r.status_code == 200
    assert len(r.json()) == 1

    r = client.get(f"/api/receipts/summary?month={month}", headers=headers)
    assert r.status_code == 200
    summary = r.json()
    assert summary["count"] == 1
    assert summary["biz_total"] == 12345

    r = client.get(f"/api/receipts/export?month={month}", headers=headers)
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/vnd.openxmlformats")

    r = client.delete("/api/receipts/latest", headers=headers)
    assert r.status_code == 200
    assert r.json()["deleted"] is True

    r = client.delete("/api/receipts/latest", headers=headers)
    assert r.status_code == 404


def test_other_user_cannot_see_receipts():
    token_a = _register("usera@example.com", "password123")
    token_b = _register("userb@example.com", "password123")

    client.post(
        "/api/receipts/upload",
        headers={"Authorization": f"Bearer {token_a}"},
        files={"file": ("r.jpg", io.BytesIO(_TINY_JPEG), "image/jpeg")},
    )
    r = client.get("/api/receipts/pending", headers={"Authorization": f"Bearer {token_b}"})
    assert r.status_code == 200
    assert r.json() is None


def test_discard_pending():
    token = _register("discard@example.com", "password123")
    headers = {"Authorization": f"Bearer {token}"}
    client.post(
        "/api/receipts/upload",
        headers=headers,
        files={"file": ("r.jpg", io.BytesIO(_TINY_JPEG), "image/jpeg")},
    )
    r = client.delete("/api/receipts/pending", headers=headers)
    assert r.status_code == 200
    assert r.json()["discarded"] is True

    r = client.get("/api/receipts/pending", headers=headers)
    assert r.json() is None

    r = client.delete("/api/receipts/pending", headers=headers)
    assert r.json()["discarded"] is False
