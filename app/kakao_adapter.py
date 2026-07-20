"""카카오 i 오픈빌더 스킬서버 <-> 내부 로직 사이의 어댑터.

주의(중요): 카카오톡 채널 웹훅 페이로드는 "스킬"의 종류(자유발화 vs 이미지 전송 플러그인 등)에
따라 필드 경로가 달라진다. 정확한 필드명은 카카오 i 오픈빌더 관리자센터에서 실제 스킬을
등록하고 테스트 전송을 해봐야 확정할 수 있다 (공식 문서가 로그인 후에만 전체 공개됨).
아래 `extract_image_url()`은 알려진 후보 경로 여러 개를 방어적으로 순서대로 시도하도록
작성했다 — 배포 전 실제 카카오 관리자센터에서 "테스트 전송"으로 실제 payload를 한 번
확인하고 이 함수만 업데이트하면 나머지 파이프라인은 그대로 동작한다.
"""
from __future__ import annotations

from typing import Any, Optional


def extract_image_url(payload: dict[str, Any]) -> Optional[str]:
    """카카오 스킬 요청 payload에서 사용자가 보낸 이미지의 URL을 찾는다."""
    action = payload.get("action", {})
    params = action.get("params", {}) or {}
    client_extra = action.get("clientExtra", {}) or {}

    # 알려진 후보 경로들 (실제 등록 후 확인 필요 - 위 모듈 docstring 참고)
    candidates = [
        params.get("secureimage"),
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
