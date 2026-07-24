"""웹앱/안드로이드 앱용 REST API (카카오봇과 완전히 독립적인 인터페이스).

- 인증: 자체 계정(이메일/비밀번호) + JWT (app/auth.py)
- 데이터: 카카오봇과 동일한 receipts 테이블을 공유한다 (owner_id만 다름).
- 로직: extractor/storage/report의 기존 함수를 그대로 재사용해 중복을 피한다.
"""
from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, EmailStr, Field

from . import auth, report, storage
from .extractor import (
    MAX_IMAGE_BYTES,
    ExtractionError,
    _sniff_image_media_type,
    get_extractor,
)
from .models import EDITABLE_RECEIPT_FIELDS, VALID_CATEGORIES, VALID_DOC_TYPES

router = APIRouter(prefix="/api")


# --------------------------------------------------------------------------
# 인증
# --------------------------------------------------------------------------

class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class AuthResponse(BaseModel):
    token: str
    user: dict


@router.post("/auth/register", response_model=AuthResponse, status_code=201)
def register(payload: RegisterRequest) -> AuthResponse:
    password_hash = auth.hash_password(payload.password)
    try:
        user_id = storage.create_user(payload.email.lower(), password_hash)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail="이미 등록된 이메일입니다.") from exc
    token = auth.create_access_token(user_id, payload.email.lower())
    return AuthResponse(token=token, user={"id": user_id, "email": payload.email.lower()})


@router.post("/auth/login", response_model=AuthResponse)
def login(payload: LoginRequest) -> AuthResponse:
    user = storage.get_user_by_email(payload.email.lower())
    if user is None or not auth.verify_password(payload.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="이메일 또는 비밀번호가 올바르지 않습니다.")
    token = auth.create_access_token(user["id"], user["email"])
    return AuthResponse(token=token, user={"id": user["id"], "email": user["email"]})


@router.get("/me")
def me(user_id: int = Depends(auth.get_current_user_id)) -> dict:
    user = storage.get_user_by_id(user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다.")
    return {"id": user["id"], "email": user["email"]}


# --------------------------------------------------------------------------
# 영수증
# --------------------------------------------------------------------------

def _receipt_to_dict(row) -> dict:
    return {
        "id": row["id"],
        "merchant": row["merchant"],
        "amount": row["amount"],
        "date": row["date"],
        "doc_type": row["doc_type"],
        "category": row["category"],
        "biz_or_personal": row["biz_or_personal"],
        "biz_reg_no": row["biz_reg_no"],
        "confidence": row["confidence"],
        "supply_amount": row["supply_amount"],
        "vat_amount": row["vat_amount"],
        "status": row["status"],
    }


def _tax_total_error(row) -> str | None:
    supply = row["supply_amount"]
    vat = row["vat_amount"]
    if supply is not None and vat is not None and supply + vat != row["amount"]:
        return (
            f"공급가액({supply:,}원)과 부가세({vat:,}원)의 합계가 "
            f"총액({row['amount']:,}원)과 다릅니다."
        )
    return None


@router.post("/receipts/upload")
async def upload_receipt(
    file: UploadFile,
    user_id: int = Depends(auth.get_current_user_id),
) -> dict:
    content = await file.read()
    if len(content) > MAX_IMAGE_BYTES:
        raise HTTPException(status_code=400, detail="이미지는 10MB 이하여야 합니다.")
    media_type = _sniff_image_media_type(content)
    if media_type is None:
        raise HTTPException(status_code=400, detail="JPEG, PNG, WebP 이미지만 사용할 수 있습니다.")

    owner_id = auth.owner_id_for_user(user_id)
    duplicate = storage.find_receipt_by_image(owner_id, content)
    if duplicate is not None:
        return {"duplicate": True, "receipt": _receipt_to_dict(duplicate)}

    try:
        data = get_extractor().extract_bytes(content, media_type)
    except ExtractionError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    storage.create_draft_receipt(
        owner_id, data, image_content=content, image_content_type=media_type
    )
    pending = storage.get_pending_receipt(owner_id)
    return {"duplicate": False, "receipt": _receipt_to_dict(pending)}


@router.get("/receipts/pending")
def get_pending(user_id: int = Depends(auth.get_current_user_id)) -> dict | None:
    owner_id = auth.owner_id_for_user(user_id)
    pending = storage.get_pending_receipt(owner_id)
    return _receipt_to_dict(pending) if pending else None


class CorrectionRequest(BaseModel):
    changes: dict[str, object]


def _validate_changes(changes: dict[str, object]) -> dict[str, object]:
    validated: dict[str, object] = {}
    for field, value in changes.items():
        if field not in EDITABLE_RECEIPT_FIELDS:
            raise ValueError(f"수정할 수 없는 항목입니다: {field}")
        if field in {"amount", "supply_amount", "vat_amount"}:
            try:
                value = int(value)
            except (TypeError, ValueError) as exc:
                raise ValueError(f"{field}는 숫자여야 합니다.") from exc
            minimum = 1 if field == "amount" else 0
            if value < minimum:
                raise ValueError(f"{field} 값이 올바르지 않습니다.")
        elif field == "date":
            try:
                datetime.strptime(str(value), "%Y-%m-%d")
            except ValueError as exc:
                raise ValueError("날짜는 YYYY-MM-DD 형식이어야 합니다.") from exc
        elif field == "doc_type" and value not in VALID_DOC_TYPES:
            raise ValueError(f"증빙유형은 {', '.join(sorted(VALID_DOC_TYPES))} 중 하나여야 합니다.")
        elif field == "category" and value not in VALID_CATEGORIES:
            raise ValueError(f"카테고리는 {', '.join(sorted(VALID_CATEGORIES))} 중 하나여야 합니다.")
        elif field == "biz_or_personal" and value not in {"사업", "개인"}:
            raise ValueError("구분은 '사업' 또는 '개인'이어야 합니다.")
        validated[field] = value
    return validated


@router.patch("/receipts/pending")
def correct_pending(
    payload: CorrectionRequest,
    user_id: int = Depends(auth.get_current_user_id),
) -> dict:
    owner_id = auth.owner_id_for_user(user_id)
    if not storage.get_pending_receipt(owner_id):
        raise HTTPException(status_code=404, detail="수정할 영수증이 없습니다.")
    try:
        changes = _validate_changes(payload.changes)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    updated = storage.update_pending_receipt(owner_id, changes)
    return _receipt_to_dict(updated)


@router.delete("/receipts/pending")
def discard_pending(user_id: int = Depends(auth.get_current_user_id)) -> dict:
    owner_id = auth.owner_id_for_user(user_id)
    discarded = storage.discard_pending_receipt(owner_id)
    return {"discarded": discarded}


@router.post("/receipts/confirm")
def confirm_receipt(user_id: int = Depends(auth.get_current_user_id)) -> dict:
    owner_id = auth.owner_id_for_user(user_id)
    pending = storage.get_pending_receipt(owner_id)
    if pending is None:
        raise HTTPException(status_code=404, detail="저장할 영수증이 없습니다.")
    tax_error = _tax_total_error(pending)
    if tax_error:
        raise HTTPException(status_code=422, detail=tax_error)
    saved = storage.confirm_pending_receipt(owner_id)
    return _receipt_to_dict(saved)


@router.get("/receipts")
def list_receipts(
    month: str | None = None,
    user_id: int = Depends(auth.get_current_user_id),
) -> list[dict]:
    owner_id = auth.owner_id_for_user(user_id)
    rows = (
        storage.get_receipts_for_month(owner_id, month)
        if month
        else storage.get_all_receipts(owner_id)
    )
    return [_receipt_to_dict(r) for r in rows]


@router.get("/receipts/summary")
def monthly_summary(
    month: str | None = None,
    user_id: int = Depends(auth.get_current_user_id),
) -> dict:
    owner_id = auth.owner_id_for_user(user_id)
    yyyy_mm = month or datetime.now(UTC).strftime("%Y-%m")
    return report.build_monthly_summary_data(owner_id, yyyy_mm)


@router.get("/receipts/export")
def export_excel(
    month: str | None = None,
    user_id: int = Depends(auth.get_current_user_id),
) -> FileResponse:
    owner_id = auth.owner_id_for_user(user_id)
    safe_name = f"user{user_id}"
    out_path = Path(__file__).resolve().parent.parent / "data" / "reports" / f"{safe_name}_report.xlsx"
    report.export_to_excel(owner_id, out_path, yyyy_mm=month)
    return FileResponse(
        out_path,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename=f"영수증_{month or 'all'}.xlsx",
    )


@router.delete("/receipts/latest")
def delete_latest(user_id: int = Depends(auth.get_current_user_id)) -> dict:
    owner_id = auth.owner_id_for_user(user_id)
    deleted = storage.delete_latest_receipt(owner_id)
    if deleted is None:
        raise HTTPException(status_code=404, detail="삭제할 영수증이 없습니다.")
    return {"deleted": True, "receipt": _receipt_to_dict(deleted)}
