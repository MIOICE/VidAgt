import socket

import pytest

from app.services.url_safety import UnsafeUrlError, validate_public_http_url


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1/video.mp4",
        "http://localhost/video.mp4",
        "http://10.1.2.3/video.mp4",
        "http://169.254.169.254/latest/meta-data",
        "http://[::1]/video.mp4",
    ],
)
async def test_private_and_local_urls_are_rejected(url: str) -> None:
    with pytest.raises(UnsafeUrlError):
        await validate_public_http_url(url)


async def test_public_literal_ip_is_allowed() -> None:
    await validate_public_http_url("https://8.8.8.8/video.mp4")


async def test_domain_resolving_to_private_ip_is_rejected(monkeypatch) -> None:
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *_args, **_kwargs: [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("192.168.1.10", 443))
        ],
    )

    with pytest.raises(UnsafeUrlError):
        await validate_public_http_url("https://video.example.test/file.mp4")
