from pathlib import Path
from unittest.mock import patch

from app.utils.html_localize import localize_html_resources
from app.utils.ssrf import is_blocked_url


def test_private_and_local_urls_are_blocked():
    assert is_blocked_url("http://127.0.0.1/secret")
    assert is_blocked_url("http://localhost/secret")
    assert is_blocked_url("http://10.0.0.5/x")
    assert is_blocked_url("http://169.254.169.254/latest/meta-data/")
    assert is_blocked_url("file:///etc/passwd")
    assert is_blocked_url("http://metadata.google.internal/")


def test_private_image_urls_are_stripped(tmp_path: Path):
    html = b'<html><body><img src="http://127.0.0.1/internal.png"></body></html>'
    out = localize_html_resources(html, "https://example.com/page", tmp_path / "assets")
    text = out.decode("utf-8")
    assert "127.0.0.1" not in text
    assert "internal.png" not in text
    assert '<img src="">' in text


def test_file_scheme_resources_are_stripped(tmp_path: Path):
    html = b'<html><body><img src="file:///C:/Windows/win.ini"></body></html>'
    out = localize_html_resources(html, "https://example.com/page", tmp_path / "assets")
    assert b"file:" not in out.lower()
    assert b"win.ini" not in out


def test_public_image_is_rewritten_to_assets(tmp_path: Path):
    html = b'<html><body><img src="https://cdn.example.com/logo.png"></body></html>'
    dest = tmp_path / "assets"

    def fake_fetch(url: str):
        if url == "https://cdn.example.com/logo.png":
            return b"\x89PNG", "image/png"
        return None

    with patch("app.utils.html_localize.try_fetch_public_resource", side_effect=fake_fetch):
        out = localize_html_resources(html, "https://example.com/page", dest)

    text = out.decode("utf-8")
    assert "cdn.example.com" not in text
    assert 'src="assets/' in text
    assert ".png" in text
    saved = list(dest.glob("*.png"))
    assert len(saved) == 1
    assert saved[0].read_bytes() == b"\x89PNG"


def test_css_url_to_link_local_is_stripped(tmp_path: Path):
    html = (
        b"<html><head><style>"
        b"body { background: url(http://169.254.169.254/latest/meta-data/); }"
        b"</style></head><body></body></html>"
    )
    out = localize_html_resources(html, "https://example.com/page", tmp_path / "assets")
    text = out.decode("utf-8")
    assert "169.254.169.254" not in text
    assert "meta-data" not in text
    assert "url()" in text


def test_stylesheet_is_fetched_and_nested_css_urls_stay_local(tmp_path: Path):
    dest = tmp_path / "assets"
    html = b'<html><head><link rel="stylesheet" href="https://cdn.example.com/app.css"></head></html>'

    def fake_fetch(url: str):
        if url == "https://cdn.example.com/app.css":
            return (
                b'body { background: url("https://cdn.example.com/bg.png"); }',
                "text/css",
            )
        if url == "https://cdn.example.com/bg.png":
            return b"PNGDATA", "image/png"
        return None

    with patch("app.utils.html_localize.try_fetch_public_resource", side_effect=fake_fetch):
        out = localize_html_resources(html, "https://example.com/page", dest)

    text = out.decode("utf-8")
    assert "cdn.example.com" not in text
    assert 'href="assets/' in text
    css_files = list(dest.glob("*.css"))
    assert len(css_files) == 1
    css = css_files[0].read_text(encoding="utf-8")
    assert "cdn.example.com" not in css
    assert "url(" in css
    assert "assets/" not in css
    pngs = list(dest.glob("*.png"))
    assert len(pngs) == 1
    assert pngs[0].name in css
