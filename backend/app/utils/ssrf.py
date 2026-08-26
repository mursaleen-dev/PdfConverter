import ipaddress
import socket
from urllib.parse import urljoin, urlparse

import requests

from app.errors import ConversionError

ALLOWED_SCHEMES = {"http", "https"}
MAX_REDIRECTS = 5
FETCH_TIMEOUT_SECONDS = 10
MAX_HTML_BYTES = 5 * 1024 * 1024


def _is_public_ip(ip_str: str) -> bool:
    ip = ipaddress.ip_address(ip_str)
    return not (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    )


def _validate_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in ALLOWED_SCHEMES:
        raise ConversionError(400, "invalid_url", "Only http and https URLs are supported.")
    if not parsed.hostname:
        raise ConversionError(400, "invalid_url", "The URL must include a hostname.")

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


def safe_fetch_html(url: str) -> bytes:
    """Fetch a URL's HTML while guarding against SSRF: blocks private/loopback/
    link-local targets (including via redirects), enforces http(s)-only, and caps
    response size. Resources the fetched HTML itself references (images, CSS) are
    later loaded by LibreOffice during PDF export and are not covered by this check.
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

        content = bytearray()
        for chunk in response.iter_content(chunk_size=65536):
            content.extend(chunk)
            if len(content) > MAX_HTML_BYTES:
                response.close()
                raise ConversionError(400, "fetch_failed", "The page is too large to convert.")
        response.close()
        return bytes(content)

    raise ConversionError(400, "fetch_failed", "Too many redirects.")
