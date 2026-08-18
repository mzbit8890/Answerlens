import asyncio
import ipaddress
import ssl
from collections.abc import Iterable

import httpcore
import httpx
import pytest
from httpcore._backends.base import SOCKET_OPTION, AsyncNetworkBackend, AsyncNetworkStream

from guardrails.network_safety import PinnedAsyncHTTPTransport, PublicIPNetworkBackend
from guardrails.url_safety import URLSafetyError


class RecordingStream(AsyncNetworkStream):
    def __init__(self) -> None:
        self.writes: list[bytes] = []
        self.server_hostnames: list[str | None] = []
        self._reads = [
            b"HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\nContent-Length: 2\r\n\r\nOK",
            b"",
        ]

    async def read(self, max_bytes: int, timeout: float | None = None) -> bytes:
        del max_bytes, timeout
        return self._reads.pop(0)

    async def write(self, buffer: bytes, timeout: float | None = None) -> None:
        del timeout
        self.writes.append(buffer)

    async def aclose(self) -> None:
        return None

    async def start_tls(
        self,
        ssl_context: ssl.SSLContext,
        server_hostname: str | None = None,
        timeout: float | None = None,
    ) -> AsyncNetworkStream:
        del ssl_context, timeout
        self.server_hostnames.append(server_hostname)
        return self


class RecordingBackend(AsyncNetworkBackend):
    def __init__(self) -> None:
        self.connected_hosts: list[str] = []
        self.stream = RecordingStream()

    async def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: float | None = None,
        local_address: str | None = None,
        socket_options: Iterable[SOCKET_OPTION] | None = None,
    ) -> AsyncNetworkStream:
        del port, timeout, local_address, socket_options
        self.connected_hosts.append(host)
        return self.stream

    async def connect_unix_socket(
        self,
        path: str,
        timeout: float | None = None,
        socket_options: Iterable[SOCKET_OPTION] | None = None,
    ) -> AsyncNetworkStream:
        del path, timeout, socket_options
        raise AssertionError("Unix sockets must not be used")

    async def sleep(self, seconds: float) -> None:
        del seconds


def test_connection_uses_validated_numeric_ip_but_preserves_host_and_tls_name() -> None:
    recording_backend = RecordingBackend()

    async def resolver(hostname: str, port: int) -> set[ipaddress.IPv4Address]:
        assert hostname == "company.example"
        assert port == 443
        return {ipaddress.ip_address("93.184.216.34")}

    async def request() -> httpx.Response:
        network_backend = PublicIPNetworkBackend(
            resolver=resolver, backend=recording_backend
        )
        async with httpx.AsyncClient(
            transport=PinnedAsyncHTTPTransport(network_backend), trust_env=False
        ) as client:
            return await client.get("https://company.example/")

    response = asyncio.run(request())

    assert response.text == "OK"
    assert recording_backend.connected_hosts == ["93.184.216.34"]
    assert recording_backend.stream.server_hostnames == ["company.example"]
    request_bytes = b"".join(recording_backend.stream.writes).lower()
    assert b"host: company.example" in request_bytes


def test_connection_time_dns_rebinding_to_private_ip_is_rejected() -> None:
    recording_backend = RecordingBackend()

    async def rebound_resolver(
        hostname: str, port: int
    ) -> set[ipaddress.IPv4Address]:
        del hostname, port
        return {ipaddress.ip_address("127.0.0.1")}

    async def request() -> None:
        network_backend = PublicIPNetworkBackend(
            resolver=rebound_resolver, backend=recording_backend
        )
        async with httpx.AsyncClient(
            transport=PinnedAsyncHTTPTransport(network_backend), trust_env=False
        ) as client:
            await client.get("https://company.example/")

    with pytest.raises(URLSafetyError, match="non-public address"):
        asyncio.run(request())

    assert recording_backend.connected_hosts == []


def test_all_dns_answers_must_be_public_before_any_connection() -> None:
    recording_backend = RecordingBackend()

    async def mixed_resolver(hostname: str, port: int):
        del hostname, port
        return {
            ipaddress.ip_address("93.184.216.34"),
            ipaddress.ip_address("10.0.0.5"),
        }

    backend = PublicIPNetworkBackend(resolver=mixed_resolver, backend=recording_backend)

    with pytest.raises(URLSafetyError, match="non-public address"):
        asyncio.run(backend.connect_tcp("company.example", 443))

    assert recording_backend.connected_hosts == []
