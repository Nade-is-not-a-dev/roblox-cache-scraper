"""CacheScraper: intercepts and caches Roblox assets from proxy traffic."""

import base64
import gzip
import logging
from concurrent.futures import ThreadPoolExecutor
from threading import Lock
from typing import Optional

logger = logging.getLogger(__name__)

ASSET_DELIVERY_HOST = 'assetdelivery.roblox.com'
CDN_HOSTS = frozenset({'fts.rbxcdn.com', 'contentdelivery.roblox.com'})

try:
    import orjson
    def _loads(data):
        return orjson.loads(data)
except ImportError:
    import json
    def _loads(data):
        return json.loads(data)


def _normalize_asset_id(asset_id):
    if isinstance(asset_id, bool):
        return asset_id
    if isinstance(asset_id, int):
        return asset_id
    if isinstance(asset_id, str) and asset_id.isdigit():
        try:
            return int(asset_id)
        except ValueError:
            return asset_id
    return asset_id


class CacheScraper:
    """Caches Roblox assets as they are intercepted by the proxy."""

    def __init__(self, cache_manager):
        self.cache_manager = cache_manager
        self.enabled = False
        self._lock = Lock()
        self._cache_logs: dict = {}
        self._url_to_asset: dict[str, list] = {}
        self._url_to_texpack_slot: dict[str, tuple[int, int, int]] = {}
        self._texpack_slot_quality: dict[tuple[int, int], int] = {}
        self._texpack_subasset_lookup: dict[int, tuple[int, int]] = {}
        self._executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix='cache_api')

    def set_enabled(self, enabled: bool):
        self.enabled = enabled

    def clear_tracking(self):
        with self._lock:
            self._cache_logs.clear()
            self._url_to_asset.clear()

    # ── Stage 1: Asset discovery from batch responses ──

    def process_batch_response(self, req_body: bytes, resp_body: bytes):
        """Extract asset IDs and CDN locations from batch response."""
        if not self.enabled or not req_body or not resp_body:
            return
        try:
            req_json = _loads(req_body)
            res_json = _loads(resp_body)
        except Exception:
            return

        if not isinstance(req_json, list) or not isinstance(res_json, list):
            return

        tracked = 0
        with self._lock:
            for idx, item in enumerate(req_json):
                if not isinstance(item, dict) or 'assetId' not in item:
                    continue
                asset_id = item['assetId']
                if idx >= len(res_json):
                    continue
                res_item = res_json[idx]
                if not isinstance(res_item, dict):
                    continue
                location = res_item.get('location')
                asset_type = res_item.get('assetTypeId')
                if location is None:
                    continue
                if asset_type is None:
                    asset_type = self._cache_logs.get(asset_id, {}).get('assetTypeId')
                if asset_type is None:
                    continue

                base_url = location.split('?')[0]
                if base_url in self._url_to_asset:
                    continue

                if asset_id not in self._cache_logs:
                    self._cache_logs[asset_id] = {
                        'location': location,
                        'assetTypeId': asset_type,
                    }
                url_list = self._url_to_asset.setdefault(base_url, [])
                url_list.append(asset_id)
                tracked += 1

        if tracked > 0:
            logger.info('Tracking %d asset(s) for caching', tracked)

    # ── Stage 2: CDN response caching ──

    def process_cdn_response(self, full_url: str, path: str, body: bytes, content_type: str):
        """Cache the actual CDN asset bytes."""
        if not self.enabled or not body:
            return
        base_url = full_url.split('?')[0]

        with self._lock:
            tp_slot = self._url_to_texpack_slot.get(base_url)
            asset_ids = self._url_to_asset.get(base_url)
            if not asset_ids and not tp_slot:
                return

            pending: list[tuple[int, int]] = []
            if asset_ids:
                for aid in asset_ids:
                    info = self._cache_logs.get(aid)
                    if info and 'cached' not in info:
                        info['cached'] = True
                        pending.append((aid, info.get('assetTypeId', 0)))

        if not pending and not tp_slot:
            return

        metadata = {
            'url': base_url,
            'content_type': content_type,
            'content_length': len(body),
            'hash': path.rsplit('/', 1)[-1],
        }

        # Decompress inner bytes for inspection
        inner = body
        if body[:2] == b'\x1f\x8b':
            try:
                inner = gzip.decompress(body)
            except Exception:
                inner = body

        # Store/convert each pending asset
        for asset_id, asset_type in pending:
            needs_conversion = (
                (asset_type in (1, 13) and inner[:8] in (b'\xabKTX 20\xbb', b'\xabKTX 11\xbb'))
                or asset_type == 63
            )

            if needs_conversion:
                self._executor.submit(
                    self._fetch_and_convert, asset_id, asset_type, base_url, metadata, body, inner,
                )
            else:
                self._executor.submit(
                    self._store_asset, asset_id, asset_type, inner, base_url, metadata,
                )

    # ── Background workers ──

    def _store_asset(self, asset_id: int, asset_type: int, data: bytes, url: str, metadata: dict):
        try:
            success = self.cache_manager.store_asset(
                str(asset_id), asset_type, data, url=url, metadata=metadata,
            )
            if success:
                type_name = self.cache_manager.get_asset_type_name(asset_type)
                logger.info('Cached %s: %s (%d bytes)', type_name, asset_id, len(data))
        except Exception as exc:
            logger.error('Cache store error: %s', exc)

    def _fetch_and_convert(self, asset_id: int, asset_type: int, url: str,
                           metadata: dict, original: bytes, inner: bytes):
        """Fetch converted version from Roblox API and cache it."""
        try:
            # Try local KTX→PNG conversion first
            if asset_type in (1, 13) and inner:
                from ..converters.ktx_to_png import convert as ktx_convert
                try:
                    png = ktx_convert(inner)
                except Exception:
                    png = None
                if png and png[:4] == b'\x89PNG':
                    metadata['content_length'] = len(png)
                    self.cache_manager.store_asset(
                        str(asset_id), asset_type, png, url=url, metadata=metadata,
                    )
                    logger.info('KTX→PNG (local): %s', asset_id)
                    return

            # Fallback: fetch from API
            import requests
            api_url = f'https://{ASSET_DELIVERY_HOST}/v1/asset/?id={asset_id}'
            try:
                resp = requests.get(api_url, headers={
                    'User-Agent': 'Roblox/WinInet',
                    'Accept-Encoding': 'gzip, deflate',
                }, timeout=15)
                if resp.status_code == 200 and resp.content:
                    api_data = resp.content
                    is_valid = False
                    if asset_type in (1, 13) and api_data[:4] == b'\x89PNG':
                        is_valid = True
                    elif asset_type == 63 and b'<roblox>' in api_data[:100]:
                        is_valid = True

                    if is_valid:
                        metadata['content_length'] = len(api_data)
                        self.cache_manager.store_asset(
                            str(asset_id), asset_type, api_data, url=url, metadata=metadata,
                        )
                        type_name = self.cache_manager.get_asset_type_name(asset_type)
                        logger.info('Converted %s: %s', type_name, asset_id)
                        return
            except Exception as exc:
                logger.debug('API fetch error for %s: %s', asset_id, exc)

            # Raw fallback
            self.cache_manager.store_asset(
                str(asset_id), asset_type, original, url=url, metadata=metadata,
            )
            logger.info('Cached (raw): %s', asset_id)
        except Exception as exc:
            logger.error('Conversion error for %s: %s', asset_id, exc)
            try:
                self.cache_manager.store_asset(
                    str(asset_id), asset_type, original, url=url, metadata=metadata,
                )
            except Exception:
                pass
