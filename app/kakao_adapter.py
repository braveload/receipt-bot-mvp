"""카카오 i 오픈빌더 스킬서버 <-> 내부 로직 사이의 어댑터.

주의(중요): 카카오톡 채널 웹훅 페이로드는 "스킬"의 종류(자유발화 vs 이미지 전송 플러그인 등)에
따라 필드 경로가 달라진다. 정확한 필드명은 카카오 i 오픈빌더 관리자센터에서 실제 스킬을
등록하고 테스트 전송을 해봐야 확정할 수 있다 (공식 문서가 로그인 후에만 전체 공개됨).
아래 `extract_image_url()`은 알려진 후보 경로 여러 개를 방어적으로 순서대로 시도하도록
작성했다 — 배포 전 실제 카카오 관리자센터에서 "테스트 전송"으로 실제 payload를 한 번
확인하고 이 함수만 업데이트하면 나머지 파이프라인은 그대로 동작한다.
"""
from __future__ import annotations

import json
import re
from typing import Any, Optional


def _extract_url_from_secure_urls(secure_urls_value: str) -> Optional[str]:
    """이미지 보안전송 플러그인의 secureUrls는 실제 URL 문자열이 아니라
    "List(url1, url2, ...)" 형태로 내려온다 (카카오 공식 문서 예시 기준).
    여러 장을 보내도 MVP는 첫 번째 이미지만 사용한다."""
    match = re.match(r"^List\((.*)\)$", secure_urls_value.strip())
    inner = match.group(1) if match else secure_urls_value
    first = inner.split(", ")[0].strip()
    return first or None


def _parse_secureimage_param(raw: Any) -> Optional[str]:
    """secureimage 파라미터 값을 파싱해 실제 이미지 URL을 반환한다.

    실제 카카오 페이로드에서는 JSON 문자열
    '{"privacyAgreement":"Y","imageQuantity":"1",
      "secureUrls":"List(https://secure.kakaocdn.net/...)","expire":"..."}'
    형태로 내려온다 (카카오 "이미지 보안전송 플러그인" 개발 문서 기준). secureUrls 자체도
    순수 URL이 아니라 List(...) 로 감싸져 있어 한 번 더 벗겨내야 한다.
    이 형태를 그대로 URL로 취급해 다운로드를 시도하면 항상 실패한다 — 실제 발생했던 버그:
    사용자가 사진을 보내면 항상 "영수증을 읽는 데 실패했어요"가 나갔던 원인이 바로 이것.
    과거 코드/테스트에서는 순수 URL 문자열을 그대로 넣기도 하므로 JSON 파싱이 실패하면
    입력값 자체를 URL로 간주해 하위 호환을 유지한다.
    """
    if not raw:
        return None
    if not isinstance(raw, str):
        return None
    try:
        parsed = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return raw  # 이미 순수 URL인 경우 (테스트/과거 호환)

    if not isinstance(parsed, dict):
        return None
    secure_urls = parsed.get("secureUrls")
    if not secure_urls:
        return None
    return _extract_url_from_secure_urls(secure_urls)


def extract_image_url(payload: dict[str, Any]) -> Optional[str]:
    """카카오 스킬 요청 payload에서 사용자가 보낸 이미지의 URL을 찾는다."""
    action = payload.get("action", {})
    params = action.get("params", {}) or {}
    client_extra = action.get("clientExtra", {}) or {}

    # 알려진 후보 경로들 (실제 등록 후 확인 필요 - 위 모듈 docstring 참고)
    candidates = [
        _parse_secureimage_param(params.get("secureimage")),
        params.get("image"),
        params.get("photo"),
        client_extra.get("image_url"),
        payload.get("userRequest", {}).get("params", {}).get("media", {}).get("url"),
    ]
    for c in candidates:
        if c:
            return c
    return None


def extract_user_id(payload: dict[str, Any]) -> str:
    """카카오톡 채널 사용자 고유 식별자 (plusfriendUserKey)."""
    return (
        payload.get("userRequest", {})
        .get("user", {})
        .get("properties", {})
        .get("plusfriendUserKey", "unknown-user")
    )


def build_simple_text_response(text: str, quick_replies: list[str] | None = None) -> dict[str, Any]:
    """카카오 스킬 응답 2.0 포맷 (simpleText) — 이 포맷은 공식 문서 기준 안정적으로 문서화되어 있음."""
    response = {
        "version": "2.0",
        "template": {"outputs": [{"simpleText": {"text": text}}]},
    }
    if quick_replies:
        response["template"]["quickReplies"] = [
            {"action": "message", "label": label, "messageText": label}
            for label in quick_replies
        ]
    return response
