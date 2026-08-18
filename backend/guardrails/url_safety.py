import asyncio
import ipaddress
import socket
from collections.abc import Awaitable, Callable
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

ALLOWED_SCHEMES = {"http", "https"}


class URLSafetyError(ValueError):
    """Raised when a URL cannot be fetched safely."""


Resolver = Callable[[str, int], Awaitable[set[ipaddress.IPv4Address | ipaddress.IPv6Address]]]


async def resolve_hostname(
    hostname: str, port: int
) -> set[ipaddress.IPv4Address | ipaddress.IPv6Address]:
    loop = asyncio.get_running_loop()
    try:
        results = await loop.getaddrinfo(hostname, port, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise URLSafetyError(f"hostname could not be resolved: {hostname}") from exc

    addresses = {ipaddress.ip_address(result[4][0]) for result in results}
    if not addresses:
        raise URLSafetyError(f"hostname did not resolve to an address: {hostname}")
    return addresses


def normalize_url(url: str) -> str:
    try:
        parsed = urlsplit(url.strip())
        port = parsed.port
    except ValueError as exc:
        raise URLSafetyError("URL is malformed") from exc

    scheme = parsed.scheme.lower()
    if scheme not in ALLOWED_SCHEMES:
        raise URLSafetyError("only HTTP and HTTPS URLs are allowed")
    if not parsed.hostname:
        raise URLSafetyError("URL must include a hostname")
    if parsed.username is not None or parsed.password is not None:
        raise URLSafetyError("URLs containing credentials are not allowed")

    try:
        hostname = parsed.hostname.encode("idna").decode("ascii").lower().rstrip(".")
    except UnicodeError as exc:
        raise URLSafetyError("URL hostname is invalid") from exc
    if not hostname:
        raise URLSafetyError("URL must include a hostname")

    default_port = 80 if scheme == "http" else 443
    port_suffix = "" if port is None or port == default_port else f":{port}"
    bracketed_host = f"[{hostname}]" if ":" in hostname else hostname
    netloc = f"{bracketed_host}{port_suffix}"

    path = parsed.path or "/"
    if path != "/":
        path = path.rstrip("/") or "/"
    query = urlencode(sorted(parse_qsl(parsed.query, keep_blank_values=True)))
    return urlunsplit((scheme, netloc, path, query, ""))


def company_scope(hostname: str) -> str:
    hostname = hostname.lower().rstrip(".")
    return hostname[4:] if hostname.startswith("www.") else hostname


def is_within_scope(hostname: str, scope: str) -> bool:
    hostname = hostname.lower().rstrip(".")
    return hostname == scope or hostname == f"www.{scope}" or hostname.endswith(f".{scope}")


def _reject_unsafe_hostname(hostname: str) -> None:
    lowered = hostname.lower().rstrip(".")
    if lowered == "localhost" or lowered.endswith(".localhost"):
        raise URLSafetyError("localhost destinations are not allowed")


def reject_unsafe_addresses(
    addresses: set[ipaddress.IPv4Address | ipaddress.IPv6Address],
) -> None:
    for address in addresses:
        if not address.is_global:
            raise URLSafetyError(f"destination resolved to a non-public address: {address}")


def validate_url_reference(url: str, *, scope: str | None = None) -> str:
    """Validate a retained URL reference without resolving its hostname."""
    normalized = normalize_url(url)
    hostname = urlsplit(normalized).hostname
    assert hostname is not None
    _reject_unsafe_hostname(hostname)
    try:
        literal_address = ipaddress.ip_address(hostname)
    except ValueError:
        pass
    else:
        reject_unsafe_addresses({literal_address})
    if scope is not None and not is_within_scope(hostname, scope):
        raise URLSafetyError("destination is outside the target website scope")
    return normalized


class URLSafetyValidator:
    def __init__(self, resolver: Resolver = resolve_hostname) -> None:
        self._resolver = resolver

    async def validate(self, url: str, *, scope: str | None = None) -> str:
        normalized = normalize_url(url)
        parsed = urlsplit(normalized)
        hostname = parsed.hostname
        assert hostname is not None

        _reject_unsafe_hostname(hostname)
        try:
            literal_address = ipaddress.ip_address(hostname)
        except ValueError:
            if scope is not None and not is_within_scope(hostname, scope):
                raise URLSafetyError("destination is outside the target website scope")
            addresses = await self._resolver(
                hostname, parsed.port or (443 if parsed.scheme == "https" else 80)
            )
        else:
            addresses = {literal_address}
        reject_unsafe_addresses(addresses)
        if scope is not None and not is_within_scope(hostname, scope):
            raise URLSafetyError("destination is outside the target website scope")
        return normalized
