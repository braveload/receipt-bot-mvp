"""홈페이지 문의 접수, 스팸 제한, 이메일 알림."""
from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import smtplib
import ssl
from datetime import UTC, datetime, timedelta
from email.message import EmailMessage

from fastapi import HTTPException, Request
from pydantic import BaseModel, Field, field_validator, model_validator

from . import storage


class ContactRequest(BaseModel):
    name: str = Field(min_length=2, max_length=80)
    contact: str = Field(min_length=5, max_length=120)
    message: str = Field(min_length=10, max_length=2000)
    privacy_consent: bool
    website: str = Field(default="", max_length=200)

    @field_validator("name", "contact", "message", mode="before")
    @classmethod
    def strip_required_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("필수 입력값입니다.")
        return value

    @model_validator(mode="after")
    def require_privacy_consent(self) -> "ContactRequest":
        if not self.privacy_consent:
            raise ValueError("개인정보 수집 동의가 필요합니다.")
        return self


def _client_hash(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for", "")
    address = forwarded.split(",", 1)[0].strip()
    if not address and request.client:
        address = request.client.host
    secret = os.environ.get("CONTACT_HASH_SECRET") or os.environ.get("REPORT_SIGNING_SECRET")
    if not secret:
        raise HTTPException(status_code=503, detail="contact service is not configured")
    return hmac.new(secret.encode(), address.encode(), hashlib.sha256).hexdigest()


def create_contact(payload: ContactRequest, request: Request) -> str | None:
    """문의 저장 후 사용자용 접수번호를 반환한다. 허니팟은 저장 없이 성공처럼 처리한다."""
    if payload.website.strip():
        return None

    client_hash = _client_hash(request)
    since = (datetime.now(UTC) - timedelta(hours=1)).isoformat()
    if storage.count_recent_inquiries(client_hash, since) >= 5:
        raise HTTPException(status_code=429, detail="잠시 후 다시 문의해 주세요.")

    reference = f"RW-{datetime.now(UTC):%Y%m%d}-{secrets.token_hex(4).upper()}"
    storage.create_inquiry(
        reference=reference,
        name=payload.name,
        contact=payload.contact,
        message=payload.message,
        client_hash=client_hash,
    )
    return reference


def send_notification(reference: str) -> None:
    """DB 저장이 끝난 문의를 SMTP로 알리고 발송 상태를 갱신한다."""
    inquiry = storage.get_inquiry(reference)
    if inquiry is None:
        return

    host = os.environ.get("SMTP_HOST", "smtp.naver.com")
    port = int(os.environ.get("SMTP_PORT", "465"))
    username = os.environ.get("SMTP_USERNAME", "")
    password = os.environ.get("SMTP_PASSWORD", "")
    recipient = os.environ.get("CONTACT_EMAIL_TO", "reromoon@naver.com")
    if not username or not password or not recipient:
        storage.update_inquiry_email_status(reference, "failed")
        return

    message = EmailMessage()
    message["Subject"] = f"[리로웍스 홈페이지 문의] {reference}"
    message["From"] = username
    message["To"] = recipient
    message.set_content(
        "\n".join(
            [
                "리로웍스 홈페이지에 새 문의가 접수되었습니다.",
                "",
                f"접수번호: {reference}",
                f"이름 또는 업체명: {inquiry['name']}",
                f"연락처: {inquiry['contact']}",
                "",
                "문의 내용",
                str(inquiry["message"]),
            ]
        )
    )

    try:
        with smtplib.SMTP_SSL(host, port, context=ssl.create_default_context(), timeout=10) as smtp:
            smtp.login(username, password)
            smtp.send_message(message)
        storage.update_inquiry_email_status(reference, "sent")
    except Exception as exc:  # SMTP 상세 오류와 개인정보는 로그에 기록하지 않는다.
        storage.update_inquiry_email_status(reference, "failed")
        print(f"[contact-email] reference={reference} status=failed type={type(exc).__name__}")
