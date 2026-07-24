"""영수증 이미지 -> 정형 데이터 추출기.

설계서(비즈니스 모델)의 "OCR + LLM" 파이프라인을 하나로 합쳤다.
전통적인 방식(OCR API로 텍스트 추출 -> 별도 LLM으로 분류)은 벤더가 2개 필요하지만,
Claude처럼 비전(이미지 이해)이 되는 LLM 한 번 호출로 추출 + 카테고리 분류까지 동시에
끝낼 수 있어 MVP 단계에서는 이 방식을 권장한다.

MockReceiptExtractor:
    - 외부 API 키 없이 데모/테스트가 가능하도록 만든 가짜 추출기.
    - 실제 이미지 내용을 보지 않고, 호출 순서에 따라 미리 준비된 샘플을 순환 반환한다.

ClaudeVisionExtractor:
    - 실서비스 전환 시 사용. ANTHROPIC_API_KEY 필요, 유료(크레딧 소진 시 호출 실패).
    - 이미지 URL을 다운로드해 base64로 인코딩 후 Claude에 "이 영수증에서 정보를 뽑아
      아래 JSON 스키마로만 답하라"는 프롬프트와 함께 전달한다.

GoogleVisionExtractor:
    - Anthropic API 크레딧 없이도 쓸 수 있는 무료 대안. GOOGLE_VISION_API_KEY 필요
      (Google Cloud Vision API, 월 1,000건까지 무료 티어).
    - Claude Vision과 달리 "OCR + 분류"를 한 번에 하지 못한다 (Vision API는 텍스트만
      뽑아준다). 그래서 OCR로 뽑은 텍스트를 정규식/키워드 규칙(parse_receipt_text)으로
      파싱해 같은 ReceiptData 스키마로 맞춘다.
    - 정확도는 Claude Vision보다 낮을 수 있다: 특히 상호명 추출(영수증 레이아웃이
      제각각이라 "첫 줄 = 상호명" 휴리스틱이 항상 맞진 않음)과 카테고리 분류(키워드
      사전에 없는 업종은 전부 "기타"로 빠짐)가 약점이다. confidence를 0.5로 고정해
      사용자에게 "확인 필요" 안내가 항상 붙도록 했다 (main.py의 confidence < 0.6 체크).
"""
from __future__ import annotations

import base64
import ipaddress
import json
import os
import re
import socket
from abc import ABC, abstractmethod
from datetime import UTC, datetime
from itertools import cycle
from typing import Optional
from urllib.parse import urlsplit

from .models import ReceiptData


class ExtractionError(Exception):
    """영수증 추출 실패 (모델 응답 파싱 실패, 이미지 다운로드 실패 등)."""


MAX_IMAGE_BYTES = 10 * 1024 * 1024
ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp"}


def _validate_public_image_url(image_url: str) -> None:
    parsed = urlsplit(image_url)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise ExtractionError("이미지는 공개 HTTPS 주소로만 전송할 수 있습니다.")

    try:
        addresses = {
            info[4][0]
            for info in socket.getaddrinfo(parsed.hostname, parsed.port or 443, type=socket.SOCK_STREAM)
        }
    except socket.gaierror as exc:
        raise ExtractionError("이미지 서버 주소를 확인할 수 없습니다.") from exc

    for address in addresses:
        ip = ipaddress.ip_address(address)
        if not ip.is_global:
            raise ExtractionError("내부 네트워크 이미지 주소는 사용할 수 없습니다.")


def _download_image(image_url: str) -> tuple[bytes, str]:
    import httpx

    _validate_public_image_url(image_url)
    try:
        response = httpx.get(image_url, timeout=15)
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise ExtractionError("이미지를 내려받지 못했습니다.") from exc

    content_type = response.headers.get("content-type", "").split(";", 1)[0].lower()
    if content_type not in ALLOWED_IMAGE_TYPES:
        raise ExtractionError("JPEG, PNG, WebP 이미지만 사용할 수 있습니다.")
    if len(response.content) > MAX_IMAGE_BYTES:
        raise ExtractionError("이미지는 10MB 이하여야 합니다.")
    return response.content, content_type


def download_private_image(image_url: str) -> tuple[bytes, str]:
    """검증된 원본 이미지를 비공개 저장용으로 내려받는다."""
    return _download_image(image_url)

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
    """실서비스용. Anthropic API로 이미지 한 장에서 바로 추출+분류. (유료)"""

    def __init__(self, model: str = "claude-sonnet-5", api_key: Optional[str] = None) -> None:
        try:
            import anthropic
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError("pip install anthropic 필요") from exc

        self._anthropic = anthropic
        self._client = anthropic.Anthropic(api_key=api_key or os.environ.get("ANTHROPIC_API_KEY"))
        self._model = model

    def _download_image_b64(self, image_url: str) -> tuple[str, str]:
        image, content_type = _download_image(image_url)
        return base64.b64encode(image).decode("utf-8"), content_type

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


# ---------------------------------------------------------------------------
# Google Cloud Vision (무료 티어) 기반 추출기
# ---------------------------------------------------------------------------

_AMOUNT_KEYWORDS = (
    "합계", "총액", "결제금액", "받을금액", "카드승인금액", "승인금액", "판매금액",
    "Total", "Net Amount", "Amount Due", "Grand Total",
)
_AMOUNT_PATTERN = re.compile(r"[\d][\d,]{2,}")
_DATE_PATTERN = re.compile(r"(20\d{2})\s*[.\-/년]\s*(\d{1,2})\s*[.\-/월]\s*(\d{1,2})")
_BIZ_REG_PATTERN = re.compile(r"\d{3}-\d{2}-\d{5}")
_NON_MERCHANT_LINE = re.compile(r"^[\d\s\-.,:()원₩*=~]+$")

_CATEGORY_KEYWORDS = {
    "접대비": ["카페", "커피", "스타벅스", "이디야", "투썸", "레스토랑", "식당", "술집", "호프"],
    "통신비": ["텔레콤", "kt", "skt", "lg유플러스", "통신", "인터넷"],
    "교통비": ["택시", "주유", "주유소", "주차", "고속도로", "지하철", "카카오티", "티맵"],
    "소모품비": ["문구", "다이소", "교보문고", "오피스", "이마트", "홈플러스"],
    "식비": ["배달", "배달의민족", "요기요", "쿠팡이츠", "김밥", "분식", "편의점", "gs25", "cu", "세븐일레븐", "이마트24"],
}


def _guess_merchant(text: str) -> str:
    for line in text.splitlines():
        stripped = line.strip()
        if stripped and not _NON_MERCHANT_LINE.match(stripped):
            return stripped[:30]
    return "알수없음"


def _guess_amount(text: str) -> int:
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if any(keyword in line for keyword in _AMOUNT_KEYWORDS):
            nums = _AMOUNT_PATTERN.findall(line)
            if not nums and i + 1 < len(lines):
                # 열(column) 레이아웃 영수증은 Vision API가 라벨과 값을 다른 줄로
                # 나눠 인식하는 경우가 흔하다 (실제 테스트에서 "Net Amount" 다음
                # 줄에 "185.00"만 단독으로 찍힌 사례로 발견). 다음 줄도 확인한다.
                nums = _AMOUNT_PATTERN.findall(lines[i + 1])
            if nums:
                return int(nums[-1].replace(",", ""))
    # 키워드 매칭 실패 시 최후 수단: 텍스트 전체에서 가장 큰 숫자를 금액으로 추정.
    # 단, 콤마 없는 7자리 이상 숫자(전화번호/사업자번호/영수증 일련번호 등)는 제외한다 —
    # 실제 테스트에서 하단의 고객센터 전화번호(9880123123)가 "9,880,123,123원"으로
    # 잘못 뽑힌 사례를 발견해서 고쳤다. 금액은 보통 콤마로 구분 표기되므로, 콤마가
    # 없는 숫자는 7자리(약 999만원)까지만 금액 후보로 인정한다.
    candidates = [
        int(n.replace(",", ""))
        for n in _AMOUNT_PATTERN.findall(text)
        if "," in n or len(n) <= 7
    ]
    return max(candidates) if candidates else 0


def _guess_date(text: str) -> str:
    match = _DATE_PATTERN.search(text)
    if match:
        year, month, day = match.groups()
        try:
            return f"{int(year):04d}-{int(month):02d}-{int(day):02d}"
        except ValueError:
            pass
    return datetime.now(UTC).strftime("%Y-%m-%d")


def _guess_category(text: str, merchant: str) -> str:
    haystack = f"{merchant} {text}".lower()
    for category, keywords in _CATEGORY_KEYWORDS.items():
        for keyword in keywords:
            # "kt", "cu"처럼 2글자 이하인 짧은 키워드는 단순 부분 문자열 매칭 시
            # 다른 단어 안에 우연히 포함되어 오탐될 수 있다 (예: 실제 테스트에서
            # 영수증 번호 "SI37482-MKT-90/81"의 "MKT" 안 "kt"가 통신사 "kt"로 잘못
            # 매칭되어 통신비로 분류된 사례 발견). 짧은 키워드는 단어 경계로 감싸서
            # 정확히 일치할 때만 인정한다.
            if len(keyword) <= 2:
                if re.search(rf"\b{re.escape(keyword.lower())}\b", haystack):
                    return category
            elif keyword.lower() in haystack:
                return category
    return "기타"


def _guess_doc_type(text: str) -> str:
    if "세금계산서" in text:
        return "세금계산서"
    if "현금영수증" in text:
        return "현금영수증"
    if "간이영수증" in text:
        return "간이영수증"
    return "카드전표"


def parse_receipt_text(text: str) -> ReceiptData:
    """OCR로 뽑은 순수 텍스트를 정규식/키워드 규칙으로 ReceiptData로 변환.

    Claude Vision과 달리 이미지를 직접 보고 판단하지 못하므로, 레이아웃이 특이한
    영수증(세로 영수증, 손글씨, 다국어 혼용 등)에서는 정확도가 떨어질 수 있다.
    그래서 confidence를 항상 0.5로 고정해 카카오톡 응답에 "확인 필요" 안내가
    붙도록 한다 (main.py: confidence < 0.6 체크).
    """
    if not text.strip():
        raise ExtractionError("OCR 결과가 비어있음 (텍스트를 인식하지 못함)")

    merchant = _guess_merchant(text)
    biz_reg_match = _BIZ_REG_PATTERN.search(text)

    return ReceiptData(
        merchant=merchant,
        amount=_guess_amount(text),
        date=_guess_date(text),
        doc_type=_guess_doc_type(text),
        category=_guess_category(text, merchant),
        biz_or_personal="사업" if biz_reg_match else "개인",
        biz_reg_no=biz_reg_match.group(0) if biz_reg_match else None,
        confidence=0.5,
    )


class GoogleVisionExtractor(ReceiptExtractor):
    """Google Cloud Vision OCR(무료 티어) + 규칙 기반 파싱.

    Claude Vision과 달리 OCR과 분류가 분리되어 있어, 이미지 -> 텍스트(Vision API)
    -> 정형 데이터(parse_receipt_text, 규칙 기반) 2단계로 동작한다.
    """

    def __init__(self, api_key: Optional[str] = None) -> None:
        self._api_key = api_key or os.environ.get("GOOGLE_VISION_API_KEY")
        if not self._api_key:
            raise RuntimeError("GOOGLE_VISION_API_KEY 환경변수 필요")

    def _download_image_b64(self, image_url: str) -> str:
        image, _ = _download_image(image_url)
        return base64.b64encode(image).decode("utf-8")

    def _ocr_text(self, image_b64: str) -> str:
        import httpx

        url = f"https://vision.googleapis.com/v1/images:annotate?key={self._api_key}"
        payload = {
            "requests": [
                {
                    "image": {"content": image_b64},
                    "features": [{"type": "TEXT_DETECTION"}],
                    "imageContext": {"languageHints": ["ko"]},
                }
            ]
        }
        resp = httpx.post(url, json=payload, timeout=20)
        resp.raise_for_status()
        data = resp.json()

        response0 = (data.get("responses") or [{}])[0]
        if "error" in response0:
            raise ExtractionError(f"Vision API 오류: {response0['error']}")

        full_text = response0.get("fullTextAnnotation", {}).get("text", "")
        if not full_text:
            raise ExtractionError("Vision API가 텍스트를 찾지 못함 (이미지가 흐리거나 영수증이 아닐 수 있음)")
        return full_text

    def extract(self, image_url: str) -> ReceiptData:
        image_b64 = self._download_image_b64(image_url)
        text = self._ocr_text(image_b64)
        return parse_receipt_text(text)


_EXTRACTOR_SINGLETON: Optional[ReceiptExtractor] = None


def get_extractor() -> ReceiptExtractor:
    """환경변수 EXTRACTOR=claude|google|mock 로 전환. 기본값은 mock (키 없이 바로 데모 가능).

    요청마다 새로 만들지 않고 프로세스당 하나만 재사용한다. (MockReceiptExtractor는
    내부 cycle 상태를 갖고 있어서, 매 요청 새로 만들면 항상 첫 샘플만 반환되는 버그가 생긴다.)
    """
    global _EXTRACTOR_SINGLETON
    if _EXTRACTOR_SINGLETON is None:
        mode = os.environ.get("EXTRACTOR", "mock").lower()
        if mode == "claude":
            _EXTRACTOR_SINGLETON = ClaudeVisionExtractor()
        elif mode == "google":
            _EXTRACTOR_SINGLETON = GoogleVisionExtractor()
        else:
            _EXTRACTOR_SINGLETON = MockReceiptExtractor()
    return _EXTRACTOR_SINGLETON
