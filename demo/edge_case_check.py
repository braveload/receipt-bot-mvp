"""회귀 방지용 엣지케이스 점검 스크립트 (정식 pytest는 아니지만 assert로 빠르게 검증).

실행: EXTRACTOR=mock python demo/edge_case_check.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("EXTRACTOR", "mock")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient  # noqa: E402


def check_malformed_json():
    from app.main import app

    client = TestClient(app)
    resp = client.post(
        "/kakao/webhook", content=b"not-json{{{", headers={"content-type": "application/json"}
    )
    assert resp.status_code == 200, f"malformed json -> {resp.status_code} (500이면 안됨)"
    text = resp.json()["template"]["outputs"][0]["simpleText"]["text"]
    print(f"[OK] malformed json -> 200, reply='{text}'")


def check_extraction_failure(monkeypatch_module):
    from app import main as main_module
    from app.extractor import ExtractionError

    class FailingExtractor:
        def extract(self, image_url):  # noqa: ARG002
            raise ExtractionError("test forced failure")

    original = main_module.get_extractor
    main_module.get_extractor = lambda: FailingExtractor()
    try:
        client = TestClient(main_module.app)
        payload = {
            "userRequest": {
                "utterance": "(이미지 전송)",
                "user": {"properties": {"plusfriendUserKey": "edge-case-user"}},
            },
            "action": {"params": {"secureimage": "https://example.com/bad.jpg"}},
        }
        resp = client.post("/kakao/webhook", json=payload)
        assert resp.status_code == 200, f"extraction failure -> {resp.status_code} (500이면 안됨)"
        text = resp.json()["template"]["outputs"][0]["simpleText"]["text"]
        assert "실패" in text or "오류" in text
        print(f"[OK] extraction failure handled gracefully -> '{text}'")
    finally:
        main_module.get_extractor = original


def check_webhook_secret():
    os.environ["WEBHOOK_SECRET"] = "s3cr3t"
    # main 모듈을 이미 임포트한 상태이므로 재로딩해서 환경변수를 반영
    import importlib

    from app import main as main_module

    importlib.reload(main_module)

    client = TestClient(main_module.app)
    payload = {"userRequest": {"utterance": "안녕", "user": {"properties": {}}}, "action": {"params": {}}}

    resp_no_secret = client.post("/kakao/webhook", json=payload)
    assert resp_no_secret.status_code == 401, f"시크릿 없이 401 나와야 하는데 {resp_no_secret.status_code}"
    print("[OK] webhook secret 미제공 시 401")

    resp_wrong = client.post("/kakao/webhook", json=payload, headers={"x-webhook-secret": "wrong"})
    assert resp_wrong.status_code == 401
    print("[OK] webhook secret 틀리면 401")

    resp_ok = client.post("/kakao/webhook", json=payload, headers={"x-webhook-secret": "s3cr3t"})
    assert resp_ok.status_code == 200
    print("[OK] webhook secret 맞으면 200")

    del os.environ["WEBHOOK_SECRET"]
    importlib.reload(main_module)


def check_dotenv_loading():
    env_path = Path(__file__).resolve().parent.parent / ".env"
    env_path.write_text("EXTRACTOR=mock\nDOTENV_CHECK_VALUE=hello123\n")
    try:
        import importlib

        from app import main as main_module

        importlib.reload(main_module)  # reload 시 load_dotenv() 재실행됨
        assert os.environ.get("DOTENV_CHECK_VALUE") == "hello123", ".env 값이 os.environ에 반영 안됨"
        print("[OK] .env 파일이 자동으로 로드됨 (python-dotenv)")
    finally:
        env_path.unlink(missing_ok=True)
        os.environ.pop("DOTENV_CHECK_VALUE", None)


def check_excel_endpoint():
    from app import main as main_module

    client = TestClient(main_module.app)
    # 데이터 몇 건 먼저 넣기
    payload = {
        "userRequest": {
            "utterance": "(이미지 전송)",
            "user": {"properties": {"plusfriendUserKey": "excel-test-user"}},
        },
        "action": {"params": {"secureimage": "https://example.com/r.jpg"}},
    }
    client.post("/kakao/webhook", json=payload)
    resp = client.get("/report/excel-test-user/excel")
    assert resp.status_code == 200, f"엑셀 다운로드 실패 {resp.status_code}"
    assert resp.headers["content-type"].startswith("application/vnd.openxmlformats")
    assert len(resp.content) > 1000
    print(f"[OK] 엑셀 다운로드 엔드포인트 정상 ({len(resp.content)} bytes)")


if __name__ == "__main__":
    check_malformed_json()
    check_extraction_failure(None)
    check_webhook_secret()
    check_dotenv_loading()
    check_excel_endpoint()
    print("\n모든 엣지케이스 통과")
