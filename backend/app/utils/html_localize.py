"""Rewrite fetched HTML so LibreOffice never loads remote or internal URLs."""
from __future__ import annotations

import hashlib
import re
from html import unescape
from pathlib import Path
from urllib.parse import urljoin, urlparse

from app.utils.ssrf import try_fetch_public_resource

MAX_LOCALIZED_RESOURCES = 24
MAX_TOTAL_RESOURCE_BYTES = 8 * 1024 * 1024
_ALLOWED_SUFFIXES = {
    ".css",
    ".gif",
    ".jpeg",
    ".jpg",
    ".png",
    ".svg",
    ".webp",
    ".woff",
    ".woff2",
    ".ttf",
    ".otf",
}
_SKIP_CONTENT_TYPES = (
    "text/html",
    "application/xhtml+xml",
    "application/javascript",
    "text/javascript",
    "application/x-javascript",
)

_TAG_STRIP_RE = re.compile(
    r"<(script|iframe|object|embed|applet|form|frame|frameset)\b[^>]*>.*?</\1\s*>",
    re.I | re.S,
)
_EMPTY_TAG_STRIP_RE = re.compile(
    r"<(script|iframe|object|embed|applet|form|frame|frameset|base|meta)\b[^>]*/?>",
    re.I,
)
_LINK_TAG_RE = re.compile(r"<link\b[^>]*>", re.I)
_MEDIA_ATTR_RE = re.compile(
    r"(<(?:img|source|video|audio|input|track|image|use|body|table|td)\b[^>]*?\s"
    r"(?:src|poster|href|xlink:href|background)\s*=\s*)"
    r"(?:\"([^\"]*)\"|'([^']*)'|([^\s>]+))",
    re.I,
)
_STYLE_URL_RE = re.compile(
    r"url\(\s*(?:\"([^\"]+)\"|'([^']+)'|([^)]+))\s*\)",
    re.I,
)
_IMPORT_RE = re.compile(
    r"@import\s+(?:url\()?[\"']?([^\"')]+)[\"']?\)?",
    re.I,
)
_SRCSET_RE = re.compile(r"(\bsrcset\s*=\s*)(?:\"([^\"]*)\"|'([^']*)')", re.I)
_STYLE_ATTR_RE = re.compile(r"(\bstyle\s*=\s*)(?:\"([^\"]*)\"|'([^']*)')", re.I)
_STYLE_TAG_RE = re.compile(r"(<style\b[^>]*>)(.*?)(</style>)", re.I | re.S)
_HREF_IN_LINK_RE = re.compile(
    r"href\s*=\s*(?:\"([^\"]*)\"|'([^']*)'|([^\s>]+))",
    re.I,
)


class _Localizer:
    def __init__(self, page_url: str, dest_dir: Path) -> None:
        self.page_url = page_url
        self.dest_dir = dest_dir
        self.dest_dir.mkdir(parents=True, exist_ok=True)
        self.saved: dict[str, str] = {}
        self.total_bytes = 0
        self.count = 0

    def localize(self, html: str) -> str:
        html = _TAG_STRIP_RE.sub("", html)
        html = _EMPTY_TAG_STRIP_RE.sub("", html)
        html = _LINK_TAG_RE.sub(self._replace_link, html)
        html = _MEDIA_ATTR_RE.sub(self._replace_media_attr, html)
        html = _SRCSET_RE.sub(self._replace_srcset, html)
        html = _STYLE_ATTR_RE.sub(self._replace_style_attr, html)
        html = _STYLE_TAG_RE.sub(self._replace_style_tag, html)
        return html

    def _html_ref(self, filename: str) -> str:
        return f"{self.dest_dir.name}/{filename}"

    def _css_ref(self, filename: str) -> str:
        return filename

    def _replace_link(self, match: re.Match[str]) -> str:
        tag = match.group(0)
        if not re.search(r"rel\s*=\s*[\"']?stylesheet", tag, re.I):
            return ""
        href = _HREF_IN_LINK_RE.search(tag)
        if not href:
            return ""
        raw = unescape(href.group(1) or href.group(2) or href.group(3) or "")
        local = self._map_url(raw, allow_css=True, from_css=False)
        if not local:
            return ""
        return f'<link rel="stylesheet" href="{local}">'

    def _replace_media_attr(self, match: re.Match[str]) -> str:
        prefix = match.group(1)
        raw = unescape(match.group(2) or match.group(3) or match.group(4) or "")
        local = self._map_url(raw, allow_css=False, from_css=False)
        return f'{prefix}"{local}"'

    def _replace_srcset(self, match: re.Match[str]) -> str:
        prefix = match.group(1)
        raw = unescape(match.group(2) or match.group(3) or "")
        parts: list[str] = []
        for item in raw.split(","):
            item = item.strip()
            if not item:
                continue
            bits = item.split()
            local = self._map_url(bits[0], allow_css=False, from_css=False)
            if not local:
                continue
            rest = " ".join(bits[1:])
            parts.append(f"{local} {rest}".strip())
        return f'{prefix}"{", ".join(parts)}"'

    def _replace_style_attr(self, match: re.Match[str]) -> str:
        prefix = match.group(1)
        css = unescape(match.group(2) or match.group(3) or "")
        return f'{prefix}"{self._rewrite_css(css, follow_import=False, from_css=False)}"'

    def _replace_style_tag(self, match: re.Match[str]) -> str:
        css = self._rewrite_css(match.group(2), follow_import=True, from_css=False)
        return f"{match.group(1)}{css}{match.group(3)}"

    def _rewrite_css(self, css: str, follow_import: bool, from_css: bool) -> str:
        def repl_url(match: re.Match[str]) -> str:
            raw = unescape((match.group(1) or match.group(2) or match.group(3) or "").strip())
            local = self._map_url(raw, allow_css=follow_import, from_css=from_css)
            if not local:
                return "url()"
            return f'url("{local}")'

        css = _STYLE_URL_RE.sub(repl_url, css)
        if follow_import:
            def repl_import(match: re.Match[str]) -> str:
                raw = unescape(match.group(1).strip())
                local = self._map_url(raw, allow_css=True, from_css=from_css)
                if not local:
                    return ""
                return f'@import url("{local}")'

            css = _IMPORT_RE.sub(repl_import, css)
        return css

    def _map_url(self, raw: str, allow_css: bool, from_css: bool) -> str:
        raw = (raw or "").strip()
        if not raw or raw.startswith("#") or raw.lower().startswith("data:"):
            return raw
        if raw.lower().startswith(("javascript:", "vbscript:", "file:", "about:")):
            return ""
        absolute = urljoin(self.page_url, raw)
        ref = self._css_ref if from_css else self._html_ref
        if absolute in self.saved:
            return ref(self.saved[absolute])
        if self.count >= MAX_LOCALIZED_RESOURCES:
            return ""
        fetched = try_fetch_public_resource(absolute)
        if fetched is None:
            return ""
        body, content_type = fetched
        ctype = (content_type or "").lower()
        if any(ctype.startswith(skip) or skip in ctype for skip in _SKIP_CONTENT_TYPES):
            return ""
        suffix = _suffix(absolute, ctype)
        is_css = ctype.startswith("text/css") or suffix == ".css"
        if is_css and not allow_css:
            return ""
        if is_css:
            nested_text = body.decode("utf-8", errors="replace")
            body = self._rewrite_css(nested_text, follow_import=False, from_css=True).encode("utf-8")
            suffix = ".css"
        if self.total_bytes + len(body) > MAX_TOTAL_RESOURCE_BYTES:
            return ""
        self.total_bytes += len(body)
        self.count += 1
        name = hashlib.sha256(absolute.encode("utf-8")).hexdigest()[:16] + suffix
        (self.dest_dir / name).write_bytes(body)
        self.saved[absolute] = name
        return ref(name)


def _suffix(url: str, content_type: str) -> str:
    path_ext = Path(urlparse(url).path).suffix.lower()
    if path_ext in _ALLOWED_SUFFIXES:
        return path_ext
    mapping = {
        "image/jpeg": ".jpg",
        "image/jpg": ".jpg",
        "image/png": ".png",
        "image/gif": ".gif",
        "image/webp": ".webp",
        "image/svg+xml": ".svg",
        "text/css": ".css",
        "font/woff2": ".woff2",
        "font/woff": ".woff",
        "font/ttf": ".ttf",
        "font/otf": ".otf",
    }
    return mapping.get(content_type.lower(), ".bin")


def localize_html_resources(html: bytes, page_url: str, dest_dir: Path) -> bytes:
    """Replace remote CSS/images with SSRF-checked local copies; drop the rest."""
    text = html.decode("utf-8", errors="replace")
    localized = _Localizer(page_url, dest_dir).localize(text)
    return localized.encode("utf-8")
