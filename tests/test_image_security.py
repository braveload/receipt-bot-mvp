import socket

import httpx
import pytest

from app import extractor
from app.extractor import ExtractionError


def test_image_url_requires_https():
    with pytest.raises(ExtractionError, match="HTTPS"):
        extractor._validate_public_image_url("http://example.com/receipt.jpg")


def test_image_url_blocks_private_network(monkeypatch):
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *args, **kwargs: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 443))],
    )

    with pytest.raises(ExtractionError, match="내부 네트워크"):
        extractor._validate_public_image_url("https://example.com/receipt.jpg")


def test_image_url_accepts_public_network(monkeypatch):
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *args, **kwargs: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))],
    )

    extractor._validate_public_image_url("https://example.com/receipt.jpg")


def test_image_url_allows_kakao_secure_cdn_over_http(monkeypatch):
    """실제 카카오톡 채널에서 재현된 버그: 카카오 이미지 보안전송 플러그인이 발급하는
    secureUrls는 https가 아니라 http로 내려온다 (카카오 공식 문서 예시 기준). 이 도메인만
    예외적으로 http를 허용해야 하며, 그 외 임의 호스트는 계속 https만 허용해야 한다."""
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *args, **kwargs: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 80))],
    )

    extractor._validate_public_image_url(
        "http://secure.kakaocdn.net/dna/xxx/img.jpg?credential=abc&signature=def"
    )


def test_image_url_still_rejects_http_for_untrusted_host_even_if_kakao_like():
    """'kakaocdn.net' 문자열을 포함하지만 실제 kakaocdn.net의 하위 도메인이 아닌
    공격용 호스트(kakaocdn.net.attacker.com)까지 허용하면 안 된다 (suffix 검사가
    아니라 단순 포함 검사였다면 뚫렸을 케이스)."""
    with pytest.raises(ExtractionError, match="HTTPS"):
        extractor._validate_public_image_url("http://kakaocdn.net.attacker.com/x.jpg")


def _response(content: bytes, content_type: str) -> httpx.Response:
    request = httpx.Request("GET", "https://example.com/receipt.jpg")
    return httpx.Response(
        200,
        content=content,
        headers={"content-type": content_type},
        request=request,
    )


def test_download_image_rejects_non_image(monkeypatch):
    monkeypatch.setattr(extractor, "_validate_public_image_url", lambda url: None)
    monkeypatch.setattr(httpx, "get", lambda *args, **kwargs: _response(b"text", "text/plain"))

    with pytest.raises(ExtractionError, match="JPEG, PNG, WebP"):
        extractor._download_image("https://example.com/receipt.jpg")


def test_download_image_rejects_oversized_file(monkeypatch):
    monkeypatch.setattr(extractor, "_validate_public_image_url", lambda url: None)
    oversized = b"x" * (extractor.MAX_IMAGE_BYTES + 1)
    monkeypatch.setattr(httpx, "get", lambda *args, **kwargs: _response(oversized, "image/jpeg"))

    with pytest.raises(ExtractionError, match="10MB"):
        extractor._download_image("https://example.com/receipt.jpg")
