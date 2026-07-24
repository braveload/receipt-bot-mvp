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
