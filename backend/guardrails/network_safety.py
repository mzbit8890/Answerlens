import ipaddress
from collections.abc import Iterable

import httpcore
import httpx
from httpcore._backends.auto import AutoBackend
from httpcore._backends.base import SOCKET_OPTION, AsyncNetworkBackend, AsyncNetworkStream

from guardrails.url_safety import Resolver, URLSafetyError, reject_unsafe_addresses, resolve_hostname


class PublicIPNetworkBackend(AsyncNetworkBackend):
    """Resolve, validate, and connect to the same numeric public address."""

    def __init__(
        self,
        *,
        resolver: Resolver = resolve_hostname,
        backend: AsyncNetworkBackend | None = None,
    ) -> None:
        self._resolver = resolver
        self._backend = backend or AutoBackend()

    async def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: float | None = None,
        local_address: str | None = None,
        socket_options: Iterable[SOCKET_OPTION] | None = None,
    ) -> AsyncNetworkStream:
        try:
            literal_address = ipaddress.ip_address(host)
        except ValueError:
            addresses = await self._resolver(host, port)
        else:
            addresses = {literal_address}

        reject_unsafe_addresses(addresses)
        last_error: Exception | None = None
        for address in sorted(addresses, key=lambda value: (value.version, int(value))):
            try:
                return await self._backend.connect_tcp(
                    str(address),
                    port,
                    timeout=timeout,
                    local_address=local_address,
                    socket_options=socket_options,
                )
            except (httpcore.ConnectError, httpcore.ConnectTimeout) as exc:
                last_error = exc

        if last_error is not None:
            raise last_error
        raise URLSafetyError(f"hostname did not resolve to an address: {host}")

    async def connect_unix_socket(
        self,
        path: str,
        timeout: float | None = None,
        socket_options: Iterable[SOCKET_OPTION] | None = None,
    ) -> AsyncNetworkStream:
        del path, timeout, socket_options
        raise URLSafetyError("Unix socket connections are not allowed")

    async def sleep(self, seconds: float) -> None:
        await self._backend.sleep(seconds)


class PinnedAsyncHTTPTransport(httpx.AsyncHTTPTransport):
    """HTTPX transport whose HTTPCore pool uses public-IP-pinned sockets."""

    def __init__(self, network_backend: AsyncNetworkBackend | None = None) -> None:
        # HTTPX 0.28.1 and HTTPCore 1.0.9 are pinned because the network backend is
        # configured at the HTTPCore pool boundary rather than through HTTPX's API.
        self._pool = httpcore.AsyncConnectionPool(
            ssl_context=httpx.create_ssl_context(verify=True, trust_env=False),
            network_backend=network_backend or PublicIPNetworkBackend(),
        )
