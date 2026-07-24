import pytest

from app.extractor import ExtractionError, parse_receipt_text


def test_parse_google_vision_text_with_amount_on_next_line():
    data = parse_receipt_text(
        "Saathimart.com\nNet Amount\n185.00\n2026-07-19\nTEL 9880123123"
    )

    assert data.merchant == "Saathimart.com"
    assert data.amount == 185
    assert data.date == "2026-07-19"
    assert data.category == "기타"
    assert data.confidence == 0.5


def test_phone_number_is_not_used_as_fallback_amount():
    data = parse_receipt_text("Example Store\nTEL 9880123123\n품목 4,500")

    assert data.amount == 4500


def test_short_category_keyword_does_not_match_inside_another_word():
    data = parse_receipt_text("Sample Store\nSI37482-MKT-90/81\n합계 12,000")

    assert data.category == "기타"


def test_empty_ocr_result_is_rejected():
    with pytest.raises(ExtractionError):
        parse_receipt_text("   ")


def test_supply_and_vat_are_extracted_when_labeled():
    data = parse_receipt_text(
        "테스트상점\n공급가액 10,000\n부가세 1,000\n합계 11,000\n2026-07-24"
    )

    assert data.amount == 11000
    assert data.supply_amount == 10000
    assert data.vat_amount == 1000
