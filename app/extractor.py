"""영수증 이미지 -> 정형 데이터 추출기.

설계서(비즈니스 모델)의 "OCR + LLM" 파이프라인을 하나로 합쳤다.
전통적인 방식(OCR API로 텍스트 추출 -> 별도 LLM으로 분류)은 벤더가 2개 필요하지만,
Claude처럼 비전(이미지 이해)이 되는 LLM 한 번 호출로 추출 + 카테고리 분류까지 동시에
끝낼 수 있어 MVP 단계에서는 이 방식을 권장한다.

MockReceiptExtractor:
    - 외부 API 키 없이 데모/테스트가 가능하도록 만든 가짜 추출기.
    - 실제 이미지 내용을 보지 않고, 호출 순서에 따라 미리 준비된 샘플을 순환 반환한다.

ClaudeVisionExtractor:
    - 실서비스 전환 시 사용. ANTHROPIC_API_KEY 필요.
    - 이미지 URL을 다운로드해 base64로 인코딩 후 Claude에 "이 영수증에서 정보를 뽑아
      아래 JSON 스키마로만 답하라"는 프롬프트와 함께 전달한다.
"""
from __future__ import annotations

import base64
import json
import os
from abc import ABC, abstractmethod
from itertools import cycle
from typing import Optional

from .models import ReceiptData


class ExtractionError(Exception):
    """영수증 추출 실패 (모델 응답 파싱 실패, 이미지 다운로드 실패 등)."""

RECEIPT_JSON_SCHEMA_PROMPT = """\
당신은 한국 영수증/세금계산서 이미지를 읽고 정형 데이터로 변환하는 전문가입니다.
이미지를 보고 아래 JSON 스키마에 맞춰 **JSON만** 출력하세요. 설명 문장은 절대 추가하지 마세요.

{
  "merchant": "상호명 (문자열)",
  "amount": 결제금액 (정수, 원 단위, 쉼표/기호 제외),
  "date": "YYYY-MM-DD",
  "doc_type": "간이영수증" | "세금계산서" | "현금영수증" | "카드전표" 중 하나,
  "category": "광고비" | "접대비" | "소모품비" | "통신비" | "교통비" | "식비" | "임차료" | "기타" 중 가장 적절한 값,
  "biz_or_personal": "사업" | "개인" 중 하나 (카페/식당의 소액 결제는 접대비 가능성 고려, 애매하면 "개인"),
  "biz_reg_no": "사업자등록번호 (하이픈 포함, 없으면 null)",
  "confidence": 0.0~1.0 사이 실수 (추출 확신도)
}
"""


class ReceiptExtractor(ABC):
    @abstractmethod
    def extract(self, image_url: str) -> ReceiptData:
        ...


class MockReceiptExtractor(ReceiptExtractor):
    """API 키 없이 파이프라인 전체 흐름을 검증하기 위한 더미 추출기."""

    _SAMPLES = [
        ReceiptData("스타벅스 강남점", 4500, "2026-07-03", "카드전표", "접대비", "사업", None, 0.92),
        ReceiptData("네이버클라우드", 33000, "2026-07-05", "세금계산서", "통신비", "사업", "220-81-62517", 0.98),
        ReceiptData("GS25 역삼점", 3200, "2026-07-08", "간이영수증", "기타", "개인", None, 0.75),
        ReceiptData("배달의민족", 18900, "2026-07-12", "현금영수증", "식비", "개인", None, 0.81),
        ReceiptData("교보문고", 27000, "2026-07-15", "카드전표", "소모품비", "사업", "120-81-47521", 0.9),
    ]

    def __init__(self) -> None:
        self._cycle = cycle(self._SAMPLES)

    def extract(self, image_url: str) -> ReceiptData:  # noqa: ARG002 (url 미사용, 데모용)
        return next(self._cycle)


class ClaudeVisionExtractor(ReceiptExtractor):
    """실서비스용. Anthropic API로 이미지 한 장에서 바로 추출+분류."""

    def __init__(self, model: str = "claude-sonnet-5", api_key: Optional[str] = None) -> None:
        try:
            import anthropic
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError("pip install anthropic 필요") from exc

        self._anthropic = anthropic
        self._client = anthropic.Anthropic(api_key=api_key or os.environ.get("ANTHROPIC_API_KEY"))
        self._model = model

    def _download_image_b64(self, image_url: str) -> tuple[str, str]:
        import httpx

        resp = httpx.get(image_url, timeout=15)
        resp.raise_for_status()
        content_type = resp.headers.get("content-type", "image/jpeg").split(";")[0]
        return base64.b64encode(resp.content).decode("utf-8"), content_type

    def extract(self, image_url: str) -> ReceiptData:
        image_b64, media_type = self._download_image_b64(image_url)

        message = self._client.messages.create(
            model=self._model,
            max_tokens=500,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {"type": "base64", "media_type": media_type, "data": image_b64},
                        },
                        {"type": "text", "text": RECEIPT_JSON_SCHEMA_PROMPT},
                    ],
                }
            ],
        )

        raw_text = message.content[0].text.strip()
        # 모델이 코드블록으로 감싸는 경우 대비
        raw_text = raw_text.removeprefix("```json").removeprefix("```").removesuffix("```").strip()

        try:
            data = json.loads(raw_text)
        except json.JSONDecodeError as exc:
            raise ExtractionError(f"모델 응답이 JSON이 아님: {raw_text[:200]!r}") from exc

        try:
            return ReceiptData(
                merchant=data["merchant"],
                amount=int(data["amount"]),
                date=data["date"],
                doc_type=data["doc_type"],
                category=data["category"],
                biz_or_personal=data["biz_or_personal"],
                biz_reg_no=data.get("biz_reg_no"),
                confidence=float(data.get("confidence", 0.0)),
            )
        except (KeyError, ValueError, TypeError) as exc:
            raise ExtractionError(f"필수 필드 누락/형식 오류: {data}") from exc


_EXTRACTOR_SINGLETON: Optional[ReceiptExtractor] = None


def get_extractor() -> ReceiptExtractor:
    """환경변수 EXTRACTOR=claude|mock 로 전환. 기본값은 mock (키 없이 바로 데모 가능).

    요청마다 새로 만들지 않고 프로세스당 하나만 재사용한다. (MockReceiptExtractor는
    내부 cycle 상태를 갖고 있어서, 매 요청 새로 만들면 항상 첫 샘플만 반환되는 버그가 생긴다.)
    """
    global _EXTRACTOR_SINGLETON
    if _EXTRACTOR_SINGLETON is None:
        mode = os.environ.get("EXTRACTOR", "mock").lower()
        _EXTRACTOR_SINGLETON = ClaudeVisionExtractor() if mode == "claude" else MockReceiptExtractor()
    return _EXTRACTOR_SINGLETON
