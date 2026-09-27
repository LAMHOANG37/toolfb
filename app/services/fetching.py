"""Bounded public-HTTP fetching. Validate every redirect before following it."""
import ipaddress
import socket
from urllib.parse import urlparse, urljoin
import httpx


def validate_url(url, resolve=False):
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("URL phải là HTTP(S) công khai, không chứa tài khoản.")
    if parsed.port not in (None, 80, 443):
        raise ValueError("Chỉ hỗ trợ cổng HTTP(S) tiêu chuẩn.")
    host = parsed.hostname.lower()
    if host == "localhost" or host.endswith((".localhost", ".local", ".internal")):
        raise ValueError("Không được truy cập địa chỉ nội bộ.")
    try:
        addresses = [ipaddress.ip_address(host)]
    except ValueError:
        addresses = []
    if resolve:
        addresses += [ipaddress.ip_address(item[4][0]) for item in socket.getaddrinfo(host, parsed.port or 443, type=socket.SOCK_STREAM)]
    if any(not address.is_global for address in addresses):
        raise ValueError("Nguồn phải trỏ đến địa chỉ Internet công khai.")
    return url


def fetch_bytes(url):
    with httpx.Client(timeout=10, follow_redirects=False, trust_env=False, headers={"User-Agent": "AI-Newsroom/0.2"}) as client:
        for _ in range(5):
            validate_url(url, resolve=True)
            with client.stream("GET", url) as response:
                if response.status_code in (301, 302, 303, 307, 308):
                    url = urljoin(url, response.headers["location"])
                    continue
                response.raise_for_status()
                chunks, total = [], 0
                for chunk in response.iter_bytes():
                    total += len(chunk)
                    if total > 2_000_000:
                        raise ValueError("Nguồn vượt quá giới hạn 2 MB.")
                    chunks.append(chunk)
                return b"".join(chunks)
    raise ValueError("Nguồn chuyển hướng quá nhiều lần.")
