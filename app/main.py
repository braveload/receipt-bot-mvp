"""영수증봇 MVP 웹훅 서버.

로컬 실행:
    uvicorn app.main:app --reload

배포 시에는 이 서버가 공인 HTTPS 주소로 떠 있어야 카카오 오픈빌더 스킬서버로 등록 가능
(Render, Railway, Fly.io 등 무료/저가 티어로 충분히 시작 가능).
"""
from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse

from . import kakao_adapter, report, storage
from .extractor import ExtractionError, get_extractor

try:
    from dotenv import load_dotenv

    load_dotenv()  # 로컬 실행 시 .env 파일을 읽어 os.environ에 반영
except ImportError:  # pragma: no cover - 프로덕션(Render 등)은 보통 대시보드에서 env 주입
    pass

app = FastAPI(title="영수증봇 MVP")
storage.init_db()  # 모듈 로드 시점에 즉시 실행 (TestClient를 컨텍스트 매니저 없이 쓰면
                    # startup 이벤트가 안 뜨는 경우가 있어, 안전하게 여기서도 한 번 더 호출)


@app.on_event("startup")
def _startup() -> None:
    storage.init_db()


def _verify_webhook_secret(x_webhook_secret: str | None) -> None:
    """WEBHOOK_SECRET 환경변수가 설정된 경우에만 검증 (미설정 시 통과 — 로컬 데모 편의).

    카카오 i 오픈빌더는 스킬 URL에 커스텀 헤더를 실어 보내는 표준 서명 방식을 제공하지
    않으므로, 최소한의 보호로 관리자센터의 "스킬 서버 URL"에 쿼리 파라미터나 커스텀
    헤더 형태로 비밀값을 실어 보내고 여기서 대조하는 방식을 권장한다. 배포 전 실제
    오픈빌더 설정 화면에서 헤더 전달이 가능한지 확인 후 값을 맞춰 넣을 것.
    """
    secret = os.environ.get("WEBHOOK_SECRET")
    if secret and x_webhook_secret != secret:
        raise HTTPException(status_code=401, detail="invalid webhook secret")


@app.post("/kakao/webhook")
async def kakao_webhook(request: Request, x_webhook_secret: str | None = Header(default=None)) -> JSONResponse:
    _verify_webhook_secret(x_webhook_secret)

    try:
        payload = await request.json()
    except Exception:
        return JSONResponse(
            kakao_adapter.build_simple_text_response("요청을 이해하지 못했어요. 다시 시도해주세요.")
        )

    user_id = kakao_adapter.extract_user_id(payload)

    image_url = kakao_adapter.extract_image_url(payload)
    if image_url:
        try:
            # get_extractor()도 try 안으로 포함 — EXTRACTOR=google인데 GOOGLE_VISION_API_KEY가
            # 없는 경우처럼, 추출기 생성 자체가 실패해도(RuntimeError) 500 대신 친절한 안내가
            # 나가도록 한다. (이전에는 get_extractor()가 try 밖에 있어 이 경우 500이었음 — 수정)
            extractor = get_extractor()
            data = extractor.extract(image_url)
        except ExtractionError as exc:
            # 모델이 이상한 응답을 준 경우 — 500 대신 사용자에게 친절하게 안내하고 로그만 남김
            print(f"[extract-error] user={user_id} url={image_url} err={exc}")
            return JSONResponse(
                kakao_adapter.build_simple_text_response(
                    "영수증을 읽는 데 실패했어요 😥 사진이 흐릿하지 않은지 확인 후 다시 보내주세요."
                )
            )
        except Exception as exc:  # 네트워크 오류, 설정 오류(RuntimeError) 등 예상 못한 실패 대비 최종 방어선
            print(f"[extract-fatal] user={user_id} url={image_url} err={exc}")
            return JSONResponse(
                kakao_adapter.build_simple_text_response(
                    "일시적인 오류가 발생했어요. 잠시 후 다시 시도해주세요."
                )
            )

        storage.save_receipt(user_id, data, image_url)

        biz_note = "사업 경비로 분류했어요" if data.biz_or_personal == "사업" else "개인 지출로 분류했어요"
        reply = (
            f"{data.merchant} · {data.amount:,}원 · {biz_note} ({data.category})"
        )
        if data.confidence < 0.6:
            reply += "\n※ 글씨가 흐려서 확인이 필요할 수 있어요. 틀렸다면 '수정'이라고 답해주세요."
        return JSONResponse(kakao_adapter.build_simple_text_response(reply))

    # 이미지가 아닌 텍스트 발화 처리 (예: "이번달", "신고파일")
    utterance = payload.get("userRequest", {}).get("utterance", "").strip()
    if utterance in ("이번달", "이번 달", "요약"):
        yyyy_mm = datetime.utcnow().strftime("%Y-%m")
        text = report.build_monthly_summary_text(user_id, yyyy_mm)
        return JSONResponse(kakao_adapter.build_simple_text_response(text))

    if utterance in ("신고파일", "신고철", "엑셀"):
        text = "신고용 엑셀 파일을 준비했어요. 잠시 후 다운로드 링크를 보내드릴게요. (MVP 데모에서는 /report/{user_id}/excel 엔드포인트로 직접 확인 가능)"
        return JSONResponse(kakao_adapter.build_simple_text_response(text))

    return JSONResponse(
        kakao_adapter.build_simple_text_response(
            "영수증 사진을 보내주시면 자동으로 정리해드려요! '이번달'이라고 보내면 요약도 볼 수 있어요."
        )
    )


@app.get("/report/{user_id}/excel")
def download_excel(user_id: str, month: str | None = None):
    out_path = Path(__file__).resolve().parent.parent / "data" / f"{user_id}_report.xlsx"
    report.export_to_excel(user_id, out_path, yyyy_mm=month)
    return FileResponse(
        out_path,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename=out_path.name,
    )


@app.get("/health")
def health():
    return {"status": "ok"}
