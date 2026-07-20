"""카카오 계정/API 키 없이도 전체 파이프라인을 검증하는 데모 스크립트.

실행:
    EXTRACTOR=mock python demo/run_demo.py

동작:
    1) 카카오 웹훅이 보낼 법한 이미지 메시지 payload 5개를 흉내내어 /kakao/webhook 에 POST
    2) 각 응답(카카오톡에 실제로 보이는 답장 텍스트)을 출력
    3) "이번달" 발화를 보내 월간 요약 응답 확인
    4) 엑셀 리포트를 실제로 생성해서 파일 경로 출력
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("EXTRACTOR", "mock")
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from app import report  # noqa: E402

client = TestClient(app)
TEST_USER = "demo-user-001"


def fake_image_payload(image_url: str) -> dict:
    return {
        "userRequest": {
            "utterance": "(이미지 전송)",
            "user": {"properties": {"plusfriendUserKey": TEST_USER}},
        },
        "action": {"params": {"secureimage": image_url}},
    }


def fake_text_payload(text: str) -> dict:
    return {
        "userRequest": {
            "utterance": text,
            "user": {"properties": {"plusfriendUserKey": TEST_USER}},
        },
        "action": {"params": {}},
    }


def main() -> None:
    print("=== 1) 영수증 이미지 5건 전송 시뮬레이션 ===")
    for i in range(5):
        payload = fake_image_payload(f"https://dummy-kakao-cdn.example.com/receipt-{i}.jpg")
        resp = client.post("/kakao/webhook", json=payload)
        text = resp.json()["template"]["outputs"][0]["simpleText"]["text"]
        print(f"[봇 응답 {i+1}] {text}")
        confirm = client.post("/kakao/webhook", json=fake_text_payload("저장"))
        confirm_text = confirm.json()["template"]["outputs"][0]["simpleText"]["text"]
        print(f"[저장 확인 {i+1}] {confirm_text}")

    print("\n=== 2) '이번달' 발화 -> 월간 요약 ===")
    resp = client.post("/kakao/webhook", json=fake_text_payload("이번달"))
    print(resp.json()["template"]["outputs"][0]["simpleText"]["text"])

    print("\n=== 3) 신고철 엑셀 리포트 생성 ===")
    out_path = Path(__file__).resolve().parent / "demo_report.xlsx"
    report.export_to_excel(TEST_USER, out_path)
    print(f"엑셀 생성 완료: {out_path} ({out_path.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
