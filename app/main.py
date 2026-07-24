"""영수증봇 MVP 웹훅 서버.

로컬 실행:
    uvicorn app.main:app --reload

배포 시에는 이 서버가 공인 HTTPS 주소로 떠 있어야 카카오 오픈빌더 스킬서버로 등록 가능
(Render, Railway, Fly.io 등 무료/저가 티어로 충분히 시작 가능).
"""
from __future__ import annotations

import os
import hashlib
import hmac
import re
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlencode

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse

from . import kakao_adapter, report, storage
from .extractor import ExtractionError, download_private_image, get_extractor

try:
    from dotenv import load_dotenv

    load_dotenv()  # 로컬 실행 시 .env 파일을 읽어 os.environ에 반영
except ImportError:  # pragma: no cover - 프로덕션(Render 등)은 보통 대시보드에서 env 주입
    pass


@asynccontextmanager
async def lifespan(app: FastAPI):  # noqa: ARG001
    storage.init_db()
    yield


app = FastAPI(title="영수증봇 MVP", lifespan=lifespan)
storage.init_db()  # 모듈 로드 시점에 즉시 실행 (TestClient를 컨텍스트 매니저 없이 쓰면
                    # startup 이벤트가 안 뜨는 경우가 있어, 안전하게 여기서도 한 번 더 호출)

EDITABLE_FIELDS = {
    "상호명": "merchant",
    "금액": "amount",
    "날짜": "date",
    "증빙유형": "doc_type",
    "카테고리": "category",
    "구분": "biz_or_personal",
    "사업/개인": "biz_or_personal",
    "사업자번호": "biz_reg_no",
}
VALID_DOC_TYPES = {"간이영수증", "세금계산서", "현금영수증", "카드전표"}
VALID_CATEGORIES = {"광고비", "접대비", "소모품비", "통신비", "교통비", "식비", "임차료", "기타"}


def _log_user_id(user_id: str) -> str:
    """운영 로그용 비가역 사용자 식별자."""
    return hashlib.sha256(user_id.encode()).hexdigest()[:12]


def _format_receipt(row) -> str:
    return (
        f"상호명: {row['merchant']}\n"
        f"금액: {row['amount']:,}원\n"
        f"날짜: {row['date']}\n"
        f"증빙유형: {row['doc_type']}\n"
        f"카테고리: {row['category']}\n"
        f"구분: {row['biz_or_personal']}"
    )


def _parse_corrections(utterance: str) -> dict[str, object]:
    body = utterance.removeprefix("수정").strip()
    if not body:
        return {}
    changes: dict[str, object] = {}
    for part in re.split(r"\s*;\s*", body):
        if "=" not in part:
            raise ValueError("수정 항목은 '항목=값' 형식으로 입력해주세요.")
        label, raw_value = (value.strip() for value in part.split("=", 1))
        field = EDITABLE_FIELDS.get(label)
        if not field or not raw_value:
            raise ValueError(f"수정할 수 없는 항목입니다: {label}")
        value: object = raw_value
        if field == "amount":
            digits = raw_value.replace(",", "").removesuffix("원").strip()
            if not digits.isdigit() or int(digits) <= 0:
                raise ValueError("금액은 0보다 큰 숫자로 입력해주세요.")
            value = int(digits)
        elif field == "date":
            try:
                datetime.strptime(raw_value, "%Y-%m-%d")
            except ValueError as exc:
                raise ValueError("날짜는 YYYY-MM-DD 형식으로 입력해주세요.") from exc
        elif field == "doc_type" and raw_value not in VALID_DOC_TYPES:
            raise ValueError(f"증빙유형은 {', '.join(sorted(VALID_DOC_TYPES))} 중 하나여야 합니다.")
        elif field == "category" and raw_value not in VALID_CATEGORIES:
            raise ValueError(f"카테고리는 {', '.join(sorted(VALID_CATEGORIES))} 중 하나여야 합니다.")
        elif field == "biz_or_personal" and raw_value not in {"사업", "개인"}:
            raise ValueError("구분은 '사업' 또는 '개인'으로 입력해주세요.")
        changes[field] = value
    return changes


def _report_signature(user_id: str, month: str, expires: int) -> str:
    secret = os.environ.get("REPORT_SIGNING_SECRET") or os.environ.get("WEBHOOK_SECRET")
    if not secret:
        raise RuntimeError("REPORT_SIGNING_SECRET 환경변수 필요")
    message = f"{user_id}\n{month}\n{expires}".encode()
    return hmac.new(secret.encode(), message, hashlib.sha256).hexdigest()


def _signed_report_url(request: Request, user_id: str, month: str = "") -> str:
    ttl = int(os.environ.get("REPORT_LINK_TTL_SECONDS", "600"))
    ttl = min(max(ttl, 60), 3600)
    expires = int(datetime.now(UTC).timestamp()) + ttl
    signature = _report_signature(user_id, month, expires)
    base_url = os.environ.get("PUBLIC_BASE_URL", str(request.base_url).rstrip("/"))
    query = urlencode({"expires": expires, "signature": signature, "month": month})
    return f"{base_url}/report/{user_id}/excel?{query}"


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
    if user_id == "unknown-user":
        return JSONResponse(
            kakao_adapter.build_simple_text_response(
                "사용자 정보를 확인하지 못했어요. 카카오톡 채널에서 다시 시도해주세요."
            )
        )

    image_url = kakao_adapter.extract_image_url(payload)
    if image_url:
        try:
            image_content = None
            image_content_type = None
            if os.environ.get("STORE_RECEIPT_IMAGES", "").lower() in {"1", "true", "yes"}:
                image_content, image_content_type = download_private_image(image_url)
            # get_extractor()도 try 안으로 포함 — EXTRACTOR=google인데 GOOGLE_VISION_API_KEY가
            # 없는 경우처럼, 추출기 생성 자체가 실패해도(RuntimeError) 500 대신 친절한 안내가
            # 나가도록 한다. (이전에는 get_extractor()가 try 밖에 있어 이 경우 500이었음 — 수정)
            extractor = get_extractor()
            data = extractor.extract(image_url)
        except ExtractionError as exc:
            # 모델이 이상한 응답을 준 경우 — 500 대신 사용자에게 친절하게 안내하고 로그만 남김
            print(f"[extract-error] user_hash={_log_user_id(user_id)} err={exc}")
            return JSONResponse(
                kakao_adapter.build_simple_text_response(
                    "영수증을 읽는 데 실패했어요 😥 사진이 흐릿하지 않은지 확인 후 다시 보내주세요."
                )
            )
        except Exception as exc:  # 네트워크 오류, 설정 오류(RuntimeError) 등 예상 못한 실패 대비 최종 방어선
            print(f"[extract-fatal] user_hash={_log_user_id(user_id)} err={type(exc).__name__}")
            return JSONResponse(
                kakao_adapter.build_simple_text_response(
                    "일시적인 오류가 발생했어요. 잠시 후 다시 시도해주세요."
                )
            )

        storage.create_draft_receipt(
            user_id,
            data,
            image_url="" if image_content else image_url,
            image_content=image_content,
            image_content_type=image_content_type,
        )
        pending = storage.get_pending_receipt(user_id)
        reply = "영수증을 읽었어요. 아래 내용을 확인해주세요.\n\n" + _format_receipt(pending)
        if data.confidence < 0.6:
            reply += "\n\n※ OCR 신뢰도가 낮아 반드시 확인해주세요."
        reply += "\n\n맞으면 '저장', 고치려면 '수정'을 선택해주세요."
        return JSONResponse(kakao_adapter.build_simple_text_response(reply, ["저장", "수정", "확인"]))

    # 이미지가 아닌 텍스트 발화 처리 (예: "이번달", "신고파일")
    utterance = payload.get("userRequest", {}).get("utterance", "").strip()
    if utterance == "확인":
        pending = storage.get_pending_receipt(user_id)
        text = (
            "현재 확인 중인 영수증입니다.\n\n" + _format_receipt(pending)
            if pending
            else "확인 중인 영수증이 없어요. 먼저 영수증 사진을 보내주세요."
        )
        return JSONResponse(kakao_adapter.build_simple_text_response(text, ["저장", "수정"] if pending else None))

    if utterance == "수정":
        if not storage.get_pending_receipt(user_id):
            text = "수정할 영수증이 없어요. 먼저 영수증 사진을 보내주세요."
        else:
            text = (
                "수정할 내용을 아래 형식으로 보내주세요.\n"
                "수정 상호명=새 상호명; 금액=5000; 날짜=2026-07-20; "
                "카테고리=소모품비; 구분=사업\n"
                "바꿀 항목만 입력하면 됩니다."
            )
        return JSONResponse(kakao_adapter.build_simple_text_response(text))

    if utterance.startswith("수정 "):
        if not storage.get_pending_receipt(user_id):
            return JSONResponse(kakao_adapter.build_simple_text_response("수정할 영수증이 없어요."))
        try:
            changes = _parse_corrections(utterance)
        except ValueError as exc:
            return JSONResponse(kakao_adapter.build_simple_text_response(str(exc)))
        pending = storage.update_pending_receipt(user_id, changes)
        text = "수정했습니다. 다시 확인해주세요.\n\n" + _format_receipt(pending)
        return JSONResponse(kakao_adapter.build_simple_text_response(text, ["저장", "수정", "확인"]))

    if utterance == "저장":
        saved = storage.confirm_pending_receipt(user_id)
        text = (
            "저장 완료했어요. ✅\n\n" + _format_receipt(saved)
            if saved
            else "저장할 영수증이 없어요. 먼저 영수증 사진을 보내주세요."
        )
        return JSONResponse(kakao_adapter.build_simple_text_response(text))

    if utterance in ("이번달", "이번 달", "요약"):
        yyyy_mm = datetime.now(UTC).strftime("%Y-%m")
        text = report.build_monthly_summary_text(user_id, yyyy_mm)
        return JSONResponse(kakao_adapter.build_simple_text_response(text))

    if utterance in ("신고파일", "신고철", "엑셀"):
        try:
            url = _signed_report_url(request, user_id)
        except RuntimeError:
            return JSONResponse(
                kakao_adapter.build_simple_text_response("신고파일 링크 설정이 아직 완료되지 않았어요.")
            )
        ttl_minutes = max(1, int(os.environ.get("REPORT_LINK_TTL_SECONDS", "600")) // 60)
        text = f"신고용 엑셀 파일을 준비했어요. 아래 링크는 {ttl_minutes}분 후 만료됩니다.\n{url}"
        return JSONResponse(kakao_adapter.build_simple_text_response(text))

    return JSONResponse(
        kakao_adapter.build_simple_text_response(
            "영수증 사진을 보내주시면 자동으로 정리해드려요! '이번달'이라고 보내면 요약도 볼 수 있어요."
        )
    )


@app.get("/report/{user_id}/excel")
def download_excel(user_id: str, expires: int, signature: str, month: str = ""):
    now = int(datetime.now(UTC).timestamp())
    if expires < now:
        raise HTTPException(status_code=410, detail="download link expired")
    if expires > now + 3600:
        raise HTTPException(status_code=400, detail="invalid expiration")
    try:
        expected = _report_signature(user_id, month, expires)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail="report signing is not configured") from exc
    if not hmac.compare_digest(signature, expected):
        raise HTTPException(status_code=403, detail="invalid signature")

    safe_name = hashlib.sha256(user_id.encode()).hexdigest()[:20]
    out_path = Path(__file__).resolve().parent.parent / "data" / "reports" / f"{safe_name}_report.xlsx"
    report.export_to_excel(user_id, out_path, yyyy_mm=month or None)
    return FileResponse(
        out_path,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename=out_path.name,
    )


@app.get("/health")
def health():
    return {"status": "ok"}
