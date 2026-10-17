from __future__ import annotations

import asyncio
import ipaddress
import socket
from urllib.parse import urlsplit


class UnsafeUrlError(ValueError):
    pass


def _require_public_address(value: str) -> None:
    address = ipaddress.ip_address(value)
    if not address.is_global:
        raise UnsafeUrlError(f"链接解析到非公网地址：{address}")


async def validate_public_http_url(url: str) -> None:
    parsed = urlsplit(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise UnsafeUrlError("仅支持有效的 HTTP/HTTPS 视频链接")
    host = parsed.hostname.rstrip(".").lower()
    if host == "localhost" or host.endswith(".localhost"):
        raise UnsafeUrlError("不允许导入本机或内网地址")
    try:
        literal_address = ipaddress.ip_address(host)
    except ValueError:
        literal_address = None
    if literal_address is not None:
        _require_public_address(str(literal_address))
        return

    def resolve() -> set[str]:
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        return {
            item[4][0]
            for item in socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
        }

    try:
        addresses = await asyncio.to_thread(resolve)
    except OSError as exc:
        raise UnsafeUrlError(f"视频链接域名无法解析：{host}") from exc
    if not addresses:
        raise UnsafeUrlError(f"视频链接域名无法解析：{host}")
    for address in addresses:
        _require_public_address(address)
