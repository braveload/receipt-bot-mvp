"""kakao_adapter.extract_image_url()의 secureimage 파싱 회귀 테스트.

실제 카카오 '이미지 보안전송 플러그인' payload는 순수 URL이 아니라
JSON 문자열이고, 그 안의 secureUrls 필드도 List(...) 래핑 문자열이다.
이 형태를 그대로 URL로 취급하면 다운로드가 항상 실패한다 —
실제 카카오톡 채널에서 재현된 버그 (2026-07-24).
"""
from app import kakao_adapter


def _payload_with_secureimage(secureimage_value):
    return {
        "userRequest": {"user": {"properties": {"plusfriendUserKey": "test-user"}}},
        "action": {"params": {"secureimage": secureimage_value}},
    }


def test_extract_image_url_parses_real_secureimage_payload():
    """카카오 공식 문서 예시와 동일한 형태의 실제 payload."""
    raw = (
        '{"privacyAgreement":"Y","imageQuantity":"1",'
        '"secureUrls":"List(http://secure.kakaocdn.net/dna/O5UOr/K6auLPnoAf/XXX/'
        'img.jpg?credential=Kq0eSbCrZgKIq51jh41Uf1jLsUh7VWcz&expires=1542358548'
        '&allow_ip=&allow_referer=&signature=fDuwSKWhQP%2FJdp0nKdunC4XDW%2BM%3D)",'
        '"expire":"1970-01-19T05:25:58+0900"}'
    )
    payload = _payload_with_secureimage(raw)

    url = kakao_adapter.extract_image_url(payload)

    assert url == (
        "http://secure.kakaocdn.net/dna/O5UOr/K6auLPnoAf/XXX/img.jpg"
        "?credential=Kq0eSbCrZgKIq51jh41Uf1jLsUh7VWcz&expires=1542358548"
        "&allow_ip=&allow_referer=&signature=fDuwSKWhQP%2FJdp0nKdunC4XDW%2BM%3D"
    )


def test_extract_image_url_takes_first_of_multiple_secure_urls():
    raw = (
        '{"privacyAgreement":"Y","imageQuantity":"2",'
        '"secureUrls":"List(https://secure.kakaocdn.net/a.jpg, '
        'https://secure.kakaocdn.net/b.jpg)","expire":"2026-07-24T00:00:00+0900"}'
    )
    payload = _payload_with_secureimage(raw)

    url = kakao_adapter.extract_image_url(payload)

    assert url == "https://secure.kakaocdn.net/a.jpg"


def test_extract_image_url_still_accepts_plain_url_for_backward_compat():
    """과거 코드/기존 테스트가 가정했던 '순수 URL' 형태도 계속 지원."""
    payload = _payload_with_secureimage("https://example.com/receipt.jpg")

    url = kakao_adapter.extract_image_url(payload)

    assert url == "https://example.com/receipt.jpg"


def test_extract_image_url_returns_none_when_secure_urls_missing():
    raw = '{"privacyAgreement":"N","imageQuantity":"0"}'
    payload = _payload_with_secureimage(raw)

    assert kakao_adapter.extract_image_url(payload) is None
