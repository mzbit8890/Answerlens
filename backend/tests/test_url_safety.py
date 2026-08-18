import asyncio
import ipaddress

import pytest

from guardrails.url_safety import URLSafetyError, URLSafetyValidator, normalize_url


async def public_resolver(hostname: str, port: int) -> set[ipaddress.IPv4Address]:
    del hostname, port
    return {ipaddress.ip_address("93.184.216.34")}


def validate(url: str) -> str:
    return asyncio.run(URLSafetyValidator(public_resolver).validate(url))


def test_valid_http_url() -> None:
    assert validate("http://example.com") == "http://example.com/"


def test_valid_https_url() -> None:
    assert validate("https://example.com/about") == "https://example.com/about"


def test_unsupported_url_scheme() -> None:
    with pytest.raises(URLSafetyError, match="only HTTP and HTTPS"):
        validate("ftp://example.com/file")


def test_localhost_is_rejected_without_dns_lookup() -> None:
    with pytest.raises(URLSafetyError, match="localhost"):
        validate("http://localhost/admin")


def test_private_ipv4_is_rejected() -> None:
    with pytest.raises(URLSafetyError, match="non-public"):
        validate("http://192.168.1.20/")


@pytest.mark.parametrize("address", ["::1", "fe80::1", "fc00::1", "::"])
def test_unsafe_ipv6_is_rejected(address: str) -> None:
    with pytest.raises(URLSafetyError, match="non-public"):
        validate(f"http://[{address}]/")


def test_hostname_resolving_to_private_address_is_rejected() -> None:
    async def private_resolver(
        hostname: str, port: int
    ) -> set[ipaddress.IPv4Address]:
        del hostname, port
        return {ipaddress.ip_address("10.0.0.8")}

    with pytest.raises(URLSafetyError, match="non-public"):
        asyncio.run(URLSafetyValidator(private_resolver).validate("https://example.com"))


def test_url_normalization_removes_duplicate_variants() -> None:
    variants = {
        normalize_url("HTTPS://EXAMPLE.COM:443/features/"),
        normalize_url("https://example.com/features#details"),
        normalize_url("https://example.com/features"),
    }

    assert variants == {"https://example.com/features"}
