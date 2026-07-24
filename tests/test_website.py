from fastapi.testclient import TestClient

from app import main


def test_website_pages_assets_and_search_files(monkeypatch):
    monkeypatch.setenv("PUBLIC_BASE_URL", "https://reroworks.example")
    client = TestClient(main.app)

    home = client.get("/")
    assert home.status_code == 200
    assert "리로웍스" in home.text
    assert "{{BASE_URL}}" not in home.text
    assert "https://reroworks.example/og.png" in home.text
    assert 'action="mailto:' not in home.text

    for path in (
        "/privacy.html",
        "/terms.html",
        "/styles.css",
        "/script.js",
        "/assets/brand/favicon.ico",
        "/assets/brand/rero-works-web-transparent.png",
        "/og.png",
    ):
        assert client.get(path).status_code == 200

    robots = client.get("/robots.txt")
    assert robots.status_code == 200
    assert "https://reroworks.example/sitemap.xml" in robots.text

    sitemap = client.get("/sitemap.xml")
    assert sitemap.status_code == 200
    assert "https://reroworks.example/privacy.html" in sitemap.text
