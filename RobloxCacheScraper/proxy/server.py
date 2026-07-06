"""Simplified asyncio TLS proxy server for Roblox asset interception."""

import asyncio
import gzip
import logging
import ssl
from pathlib import Path
from typing import Callable, Optional

logger = logging.getLogger(__name__)

_GZIP_MAGIC = b'\x1f\x8b'
_ZSTD_MAGIC = b'\x28\xb5\x2f\xfd'
ASSET_DELIVERY_HOST = 'assetdelivery.roblox.com'
CDN_HOSTS = frozenset({'fts.rbxcdn.com', 'contentdelivery.roblox.com'})
GAMEJOIN_HOST = 'gamejoin.roblox.com'
INTERCEPT_HOSTS = frozenset({ASSET_DELIVERY_HOST, GAMEJOIN_HOST} | CDN_HOSTS)

# Headers that must not be forwarded
_HOP_BY_HOP = frozenset({
    b'connection', b'proxy-connection', b'proxy-authenticate',
    b'proxy-authorization', b'transfer-encoding', b'keep-alive',
    b'te', b'trailer', b'upgrade',
})


def _decompress(body: bytes) -> bytes:
    """Decompress gzip or zstd body."""
    if not body:
        return body
    if body[:2] == _GZIP_MAGIC:
        try:
            return gzip.decompress(body)
        except Exception:
            return body
    if body[:4] == _ZSTD_MAGIC:
        try:
            import zstandard
            return zstandard.ZstdDecompressor().decompress(body, max_output_size=64 * 1024 * 1024)
        except Exception:
            return body
    return body


def _parse_headers(data: bytes) -> tuple[bytes, dict[bytes, bytes], bytes]:
    """Parse HTTP headers from raw bytes."""
    lines = data.split(b'\r\n')
    if not lines:
        return b'', {}, b''
    first_line = lines[0]
    headers: dict[bytes, bytes] = {}
    idx = 1
    for line in lines[1:]:
        if not line or line == b'':
            idx += 1
            break
        if b':' in line:
            k, _, v = line.partition(b':')
            headers[k.strip().lower()] = v.strip()
        idx += 1
    raw_block = b'\r\n'.join(lines[:idx])
    return first_line, headers, raw_block


async def _read_headers(reader: asyncio.StreamReader) -> Optional[tuple[bytes, dict[bytes, bytes], bytes]]:
    """Read HTTP headers from stream."""
    raw = bytearray()
    while True:
        try:
            line = await asyncio.wait_for(reader.readline(), timeout=15.0)
        except Exception:
            return None
        if not line:
            return None
        raw += line
        if line in (b'\r\n', b'\n'):
            break
        if len(raw) > 65536:
            raise ValueError('Headers too large')
    return _parse_headers(bytes(raw))


async def _read_body(reader: asyncio.StreamReader, headers: dict[bytes, bytes]) -> bytes:
    """Read HTTP body based on Content-Length or Transfer-Encoding."""
    if b'chunked' in headers.get(b'transfer-encoding', b'').lower():
        body = bytearray()
        while True:
            line = await reader.readline()
            if not line:
                break
            size_str = line.strip().split(b';')[0]
            try:
                chunk_size = int(size_str, 16)
            except ValueError:
                break
            if chunk_size == 0:
                await reader.readline()
                break
            chunk = await reader.readexactly(chunk_size)
            body += chunk
            await reader.readexactly(2)
        return bytes(body)

    cl = headers.get(b'content-length', b'')
    if cl:
        try:
            length = int(cl)
        except ValueError:
            return b''
        if length <= 0:
            return b''
        try:
            return await reader.readexactly(length)
        except asyncio.IncompleteReadError as exc:
            return exc.partial
    return b''


def _build_response(status_code: int, headers: dict[bytes, bytes], body: bytes) -> bytes:
    """Build HTTP response, stripping hop-by-hop headers."""
    reason = {200: b'OK', 302: b'Found', 404: b'Not Found', 502: b'Bad Gateway'}.get(status_code, b'OK')
    lines = [f'HTTP/1.1 {status_code} '.encode() + reason]
    for k, v in headers.items():
        if k not in _HOP_BY_HOP:
            lines.append(k + b': ' + v)
    lines.append(b'content-length: ' + str(len(body)).encode())
    return b'\r\n'.join(lines) + b'\r\n\r\n' + body


def _make_error(status: int, msg: str) -> bytes:
    """Build an error response."""
    body = msg.encode()
    return (
        f'HTTP/1.1 {status} '.encode() +
        {400: b'Bad Request', 502: b'Bad Gateway', 503: b'Service Unavailable'}.get(status, b'Error') +
        b'\r\nContent-Type: text/plain\r\nContent-Length: ' + str(len(body)).encode() +
        b'\r\nConnection: close\r\n\r\n' + body
    )


def _forward_headers(headers: dict[bytes, bytes], body: bytes) -> list[bytes]:
    """Build header lines for forwarding, excluding hop-by-hop headers."""
    lines = []
    connection_hdrs = set()
    conn_val = headers.get(b'connection', b'')
    for h in conn_val.split(b','):
        connection_hdrs.add(h.strip().lower())

    for k, v in headers.items():
        if k in _HOP_BY_HOP or k in connection_hdrs:
            continue
        lines.append(k + b': ' + v)

    if body or b'content-length' in headers or b'transfer-encoding' in headers:
        lines.append(b'content-length: ' + str(len(body)).encode())
    return lines


class ProxyServer:
    """Simplified MITM proxy server for Roblox asset traffic."""

    def __init__(
        self,
        on_batch_response: Callable,
        on_cdn_response: Callable,
        host_certs: dict[str, tuple[Path, Path]],
        default_cert: tuple[Path, Path],
        port: int = 443,
        upstream_connect=None,
    ):
        self.port = port
        self._on_batch_response = on_batch_response
        self._on_cdn_response = on_cdn_response
        self._upstream_connect = upstream_connect
        self._server = None
        self._v6_server = None

        # Build per-host SSL contexts
        self._host_ctxs = {}
        for host, (cp, kp) in host_certs.items():
            ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            ctx.load_cert_chain(str(cp), str(kp))
            ctx.verify_mode = ssl.CERT_NONE
            ctx.minimum_version = ssl.TLSVersion.TLSv1_2
            ctx.set_alpn_protocols(['http/1.1'])
            self._host_ctxs[host] = ctx

        # Default SSL context with SNI callback
        dc_path, dk_path = default_cert
        self._server_ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        self._server_ctx.load_cert_chain(str(dc_path), str(dk_path))
        self._server_ctx.verify_mode = ssl.CERT_NONE
        self._server_ctx.minimum_version = ssl.TLSVersion.TLSv1_2
        self._server_ctx.set_alpn_protocols(['http/1.1'])
        self._server_ctx.set_servername_callback(self._sni_callback)

        # Upstream SSL context
        self._upstream_ctx = ssl.create_default_context()
        self._upstream_ctx.check_hostname = False
        self._upstream_ctx.verify_mode = ssl.CERT_NONE
        self._upstream_ctx.set_alpn_protocols(['http/1.1'])

    def _sni_callback(self, ssl_obj, server_name, initial_ctx):
        name = (server_name or '').lower()
        if name in self._host_ctxs:
            ssl_obj.context = self._host_ctxs[name]

    async def start(self):
        self._server = await asyncio.start_server(
            self._handle_client,
            host='127.0.0.1',
            port=self.port,
            ssl=self._server_ctx,
            backlog=256,
            reuse_address=True,
        )
        logger.info('Proxy listening on 127.0.0.1:%d', self.port)

        try:
            self._v6_server = await asyncio.start_server(
                self._handle_client,
                host='::1',
                port=self.port,
                ssl=self._server_ctx,
                backlog=256,
                reuse_address=True,
            )
            logger.info('Proxy listening on [::1]:%d', self.port)
        except OSError:
            self._v6_server = None

    async def stop(self):
        servers = [s for s in [self._server, self._v6_server] if s is not None]
        for s in servers:
            s.close()
        for s in servers:
            try:
                await asyncio.wait_for(s.wait_closed(), timeout=3.0)
            except Exception:
                pass
        self._server = None
        self._v6_server = None

    async def _connect_upstream(self, host, timeout=10.0):
        if self._upstream_connect:
            return await self._upstream_connect(host, timeout)
        raise RuntimeError('No upstream connector configured')

    async def _handle_client(self, reader, writer):
        up_reader = None
        up_writer = None
        try:
            await self._proxy_session(reader, writer)
        except (ConnectionResetError, BrokenPipeError, asyncio.IncompleteReadError):
            pass
        except Exception as exc:
            logger.debug('Session error: %s', exc)
        finally:
            if up_writer is not None:
                try:
                    up_writer.close()
                except Exception:
                    pass
            try:
                writer.close()
            except Exception:
                pass

    async def _proxy_session(self, reader, writer):
        up_reader = None
        up_writer = None

        while True:
            result = await _read_headers(reader)
            if result is None:
                break
            req_first, req_headers, _ = result
            host_hdr = req_headers.get(b'host', b'').decode(errors='replace').lower()
            host = host_hdr.split(':')[0].strip()

            if host not in INTERCEPT_HOSTS:
                break

            req_body = await _read_body(reader, req_headers)
            parts = req_first.split(b' ', 2)
            path = parts[1].decode(errors='replace') if len(parts) > 1 else '/'
            is_batch = (host == ASSET_DELIVERY_HOST and b'/v1/assets/batch' in req_first)
            is_cdn = host in CDN_HOSTS

            # Connect upstream
            if up_reader is None or up_writer is None or up_writer.is_closing():
                conn = await self._connect_upstream(host)
                if conn.writer is None:
                    writer.write(_make_error(502, f'Cannot connect to {host}'))
                    await writer.drain()
                    break
                up_reader = conn.reader
                up_writer = conn.writer

            # Forward request with clean headers
            lines = [req_first]
            lines.extend(_forward_headers(req_headers, req_body))
            up_writer.write(b'\r\n'.join(lines) + b'\r\n\r\n' + req_body)
            try:
                await up_writer.drain()
            except Exception:
                break

            # Read response
            resp_result = await _read_headers(up_reader)
            if resp_result is None:
                break
            resp_first, resp_headers, _ = resp_result
            resp_body = await _read_body(up_reader, resp_headers)

            # Process with scraper
            if is_batch and self._on_batch_response:
                self._on_batch_response(req_body, _decompress(resp_body))
            if is_cdn and self._on_cdn_response:
                ct = resp_headers.get(b'content-type', b'').decode(errors='replace')
                self._on_cdn_response(f'https://{host}{path}', path, _decompress(resp_body), ct)

            # Forward response with clean headers
            resp_lines = [resp_first]
            resp_lines.extend(_forward_headers(resp_headers, resp_body))
            writer.write(b'\r\n'.join(resp_lines) + b'\r\n\r\n' + resp_body)
            try:
                await writer.drain()
            except Exception:
                break

            # Check keep-alive
            if b'close' in req_headers.get(b'connection', b'').lower():
                break
            if b'close' in resp_headers.get(b'connection', b'').lower():
                break
