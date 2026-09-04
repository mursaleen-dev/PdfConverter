import ipaddress
import re
import socket
from urllib.parse import urljoin, urlparse

import requests

from app.errors import ConversionError

ALLOWED_SCHEMES = {"http", "https"}
MAX_REDIRECTS = 5
FETCH_TIMEOUT_SECONDS = 10
MAX_HTML_BYTES = 5 * 1024 * 1024
MAX_RESOURCE_BYTES = 2 * 1024 * 1024
BLOCKED_HOST_SUFFIXES = (
    ".localhost",
    ".internal",
    ".local",
    ".lan",
    ".home",
    ".corp",
)
BLOCKED_HOSTS = {
    "localhost",
    "localhost.localdomain",
    "metadata.google.internal",
    "metadata",
}

_IPV4_MAPPED = re.compile(r"^::ffff:(\d+\.\d+\.\d+\.\d+)$", re.I)


def _is_public_ip(ip_str: str) -> bool:
    mapped = _IPV4_MAPPED.match(ip_str.strip())
    if mapped:
        ip_str = mapped.group(1)
    ip = ipaddress.ip_address(ip_str)
    if ip.version == 6 and getattr(ip, "ipv4_mapped", None) is not None:
        ip = ip.ipv4_mapped
    if not ip.is_global:
        return False
    # Shared CGNAT space is globally routed at some ISPs but not public origin.
    if ip.version == 4 and ip in ipaddress.ip_network("100.64.0.0/10"):
        return False
    return True


def _hostname_blocked(hostname: str) -> bool:
    host = (hostname or "").strip(".").lower()
    if not host or host in BLOCKED_HOSTS:
        return True
    return any(host.endswith(suffix) for suffix in BLOCKED_HOST_SUFFIXES)


def _validate_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in ALLOWED_SCHEMES:
        raise ConversionError(400, "invalid_url", "Only http and https URLs are supported.")
    if parsed.username or parsed.password:
        raise ConversionError(400, "invalid_url", "URLs with credentials are not supported.")
    if not parsed.hostname:
        raise ConversionError(400, "invalid_url", "The URL must include a hostname.")
    if _hostname_blocked(parsed.hostname):
        raise ConversionError(
            400, "invalid_url", "This URL points to a restricted network address."
        )

    try:
        addrinfo = socket.getaddrinfo(parsed.hostname, None)
    except socket.gaierror as exc:
        raise ConversionError(
            400, "invalid_url", "The URL's hostname could not be resolved."
        ) from exc

    resolved_ips = {info[4][0] for info in addrinfo}
    if not resolved_ips or not all(_is_public_ip(ip) for ip in resolved_ips):
        raise ConversionError(
            400, "invalid_url", "This URL points to a restricted network address."
        )


def is_blocked_url(url: str) -> bool:
    try:
        _validate_url(url)
        return False
    except ConversionError:
        return True


def safe_fetch_bytes(url: str, max_bytes: int = MAX_HTML_BYTES) -> tuple[bytes, str]:
    """Fetch http(s) bytes after blocking private/loopback/link-local targets.

    Re-checks DNS on every hop so redirects cannot land on an internal address.
    """
    current_url = url
    for _ in range(MAX_REDIRECTS):
        _validate_url(current_url)
        try:
            response = requests.get(
                current_url, timeout=FETCH_TIMEOUT_SECONDS, allow_redirects=False, stream=True
            )
        except requests.RequestException as exc:
            raise ConversionError(400, "fetch_failed", "Could not fetch the URL.") from exc

        if response.is_redirect or response.status_code in (301, 302, 303, 307, 308):
            location = response.headers.get("Location")
            response.close()
            if not location:
                raise ConversionError(400, "fetch_failed", "The URL redirected without a location.")
            current_url = urljoin(current_url, location)
            continue

        if response.status_code != 200:
            response.close()
            raise ConversionError(
                400, "fetch_failed", f"The URL returned status {response.status_code}."
            )

        content_type = (response.headers.get("Content-Type") or "").split(";", 1)[0].strip()
        content = bytearray()
        for chunk in response.iter_content(chunk_size=65536):
            content.extend(chunk)
            if len(content) > max_bytes:
                response.close()
                raise ConversionError(400, "fetch_failed", "The page is too large to convert.")
        response.close()
        return bytes(content), content_type

    raise ConversionError(400, "fetch_failed", "Too many redirects.")


def safe_fetch_html(url: str) -> bytes:
    """Fetch a URL's HTML while guarding against SSRF."""
    body, _content_type = safe_fetch_bytes(url, MAX_HTML_BYTES)
    return body


def try_fetch_public_resource(url: str) -> tuple[bytes, str] | None:
    """Same SSRF rules as the page fetch; returns None instead of failing the conversion."""
    if is_blocked_url(url):
        return None
    try:
        return safe_fetch_bytes(url, MAX_RESOURCE_BYTES)
    except ConversionError:
        return None
