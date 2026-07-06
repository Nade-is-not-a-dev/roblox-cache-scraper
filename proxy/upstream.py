"""Upstream connection management for the proxy server."""

import asyncio
import logging
import socket
import ssl
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class UpstreamConnectResult:
    reader: Optional[asyncio.StreamReader] = None
    writer: Optional[asyncio.StreamWriter] = None
    error: Optional[str] = None


class UpstreamConnector:
    """Manages upstream connections to Roblox servers."""

    def __init__(self, real_ips: dict[str, list[str]] | None = None):
        self._real_ips = real_ips or {}
        self._ssl_ctx = ssl.create_default_context()
        self._ssl_ctx.check_hostname = False
        self._ssl_ctx.verify_mode = ssl.CERT_NONE
        self._ssl_ctx.set_alpn_protocols(['http/1.1'])
        self._dns_cache: dict[str, list[str]] = {}

    def set_real_ips(self, ips: dict[str, list[str]]) -> None:
        self._real_ips = ips

    async def resolve_host(self, host: str) -> list[str]:
        """Resolve a hostname to IP addresses."""
        if host in self._real_ips and self._real_ips[host]:
            return self._real_ips[host]
        if host in self._dns_cache:
            return self._dns_cache[host]
        try:
            _, _, addrs = await asyncio.get_event_loop().getaddrinfo(
                host, 443, family=socket.AF_UNSPEC, type=socket.SOCK_STREAM
            )
            ips = list(dict.fromkeys(addr[4][0] for addr in addrs))  # deduplicate
            self._dns_cache[host] = ips
            return ips
        except Exception as exc:
            logger.error('DNS resolution failed for %s: %s', host, exc)
            return []

    async def connect(
        self, host: str, timeout: float = 10.0
    ) -> UpstreamConnectResult:
        """Connect to upstream server for the given host."""
        ips = await self.resolve_host(host)
        if not ips:
            return UpstreamConnectResult(error=f'Could not resolve {host}')

        last_error = None
        for ip in ips:
            try:
                raw_sock = socket.create_connection((ip, 443), timeout=timeout)
                ssl_sock = self._ssl_ctx.wrap_socket(raw_sock, server_hostname=host)
                reader = asyncio.StreamReader()
                protocol = asyncio.StreamReaderProtocol(reader)
                transport, _ = await asyncio.get_event_loop().create_connection(
                    lambda: protocol, sock=ssl_sock
                )
                writer = asyncio.StreamWriter(transport, protocol, reader, asyncio.get_event_loop())
                return UpstreamConnectResult(reader=reader, writer=writer)
            except Exception as exc:
                last_error = str(exc)
                logger.debug('Failed to connect to %s (%s): %s', host, ip, exc)
                continue

        return UpstreamConnectResult(
            error=f'All connection attempts to {host} failed: {last_error}'
        )
