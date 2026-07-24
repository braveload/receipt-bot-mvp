"""공통 데이터 모델."""
from dataclasses import dataclass, asdict
from typing import Optional


@dataclass
class ReceiptData:
    """영수증 한 건에서 추출된 정형 데이터."""

    merchant: str                # 상호명
    amount: int                  # 금액 (원)
    date: str                    # YYYY-MM-DD
    doc_type: str                # "간이영수증" | "세금계산서" | "현금영수증" | "카드전표"
    category: str                # 지출 카테고리 (예: 접대비, 소모품비, 통신비, 교통비 등)
    biz_or_personal: str         # "사업" | "개인"
    biz_reg_no: Optional[str] = None   # 사업자등록번호 (있는 경우)
    confidence: float = 0.0      # 추출 신뢰도 0~1 (수동 검수 트리거용)
    supply_amount: Optional[int] = None
    vat_amount: Optional[int] = None

    def to_dict(self) -> dict:
        return asdict(self)
