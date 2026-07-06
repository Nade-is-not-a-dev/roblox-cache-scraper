"""Cache manager for storing and indexing intercepted Roblox assets."""

import gzip
import hashlib
import json
import threading
from datetime import datetime
from pathlib import Path
from typing import Optional

ASSET_TYPES = {
    1: 'Image', 2: 'TShirt', 3: 'Audio', 4: 'Mesh', 5: 'Lua',
    6: 'HTML', 7: 'Text', 8: 'Hat', 9: 'Place', 10: 'Model',
    11: 'Shirt', 12: 'Pants', 13: 'Decal', 16: 'Avatar', 17: 'Head',
    18: 'Face', 19: 'Gear', 21: 'Badge', 22: 'GroupEmblem',
    24: 'Animation', 25: 'Arms', 26: 'Legs', 27: 'Torso',
    28: 'RightArm', 29: 'LeftArm', 30: 'LeftLeg', 31: 'RightLeg',
    32: 'Package', 33: 'YouTubeVideo', 34: 'GamePass', 35: 'App',
    37: 'Code', 38: 'Plugin', 39: 'SolidModel', 40: 'MeshPart',
    41: 'HairAccessory', 42: 'FaceAccessory', 43: 'NeckAccessory',
    44: 'ShoulderAccessory', 45: 'FrontAccessory', 46: 'BackAccessory',
    47: 'WaistAccessory', 48: 'ClimbAnimation', 49: 'DeathAnimation',
    50: 'FallAnimation', 51: 'IdleAnimation', 52: 'JumpAnimation',
    53: 'RunAnimation', 54: 'SwimAnimation', 55: 'WalkAnimation',
    56: 'PoseAnimation', 57: 'EarAccessory', 58: 'EyeAccessory',
    59: 'LocalizationTableManifest', 61: 'EmoteAnimation', 62: 'Video',
    63: 'TexturePack', 64: 'TShirtAccessory', 65: 'ShirtAccessory',
    66: 'PantsAccessory', 67: 'JacketAccessory', 68: 'SweaterAccessory',
    69: 'ShortsAccessory', 70: 'LeftShoeAccessory', 71: 'RightShoeAccessory',
    72: 'DressSkirtAccessory', 73: 'FontFamily', 74: 'FontFace',
    75: 'MeshHiddenSurfaceRemoval', 76: 'EyebrowAccessory',
    77: 'EyelashAccessory', 78: 'MoodAnimation', 79: 'DynamicHead',
    80: 'CodeSnippet',
}

try:
    import orjson
    def _json_dumps(obj, **kwargs):
        return orjson.dumps(obj, option=orjson.OPT_INDENT_2).decode('utf-8')
    def _json_loads(data):
        return orjson.loads(data)
except ImportError:
    _json_dumps = json.dumps
    _json_loads = json.loads


class CacheManager:
    """Manages cached Roblox assets organized by type."""

    def __init__(self, cache_dir: Path):
        self.cache_dir = cache_dir
        self.export_dir = cache_dir.parent / 'Exports'
        self.index_file = cache_dir / 'index.json'
        self._lock = threading.Lock()
        self._index_dirty = False
        self._commit_timer: Optional[threading.Timer] = None
        self._asset_cache: dict[str, bytes] = {}
        self._asset_cache_lock = threading.Lock()
        self._asset_cache_maxsize = 128

        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.export_dir.mkdir(parents=True, exist_ok=True)
        self.index = self._load_index()

    def _load_index(self) -> dict:
        if self.index_file.exists():
            try:
                data = self.index_file.read_text(encoding='utf-8')
                return _json_loads(data)
            except Exception:
                pass
        return {'assets': {}, 'version': '1.0'}

    def _save_index(self):
        try:
            self.index_file.write_text(_json_dumps(self.index), encoding='utf-8')
        except OSError as e:
            print(f'Failed to save index: {e}')

    def _schedule_commit(self):
        if self._commit_timer is not None:
            self._commit_timer.cancel()
        self._index_dirty = True
        self._commit_timer = threading.Timer(0.5, self._flush_index)
        self._commit_timer.daemon = True
        self._commit_timer.start()

    def _flush_index(self):
        with self._lock:
            if self._index_dirty:
                self._save_index()
                self._index_dirty = False
            self._commit_timer = None

    def get_asset_type_name(self, type_id: int) -> str:
        return ASSET_TYPES.get(type_id, f'Unknown({type_id})')

    def get_asset_path(self, asset_id: str, asset_type: int) -> Path:
        type_name = self.get_asset_type_name(asset_type)
        type_dir = self.cache_dir / type_name
        type_dir.mkdir(exist_ok=True)
        return type_dir / f'{asset_id}.bin'

    def store_raw_asset(self, asset_id: str, asset_type: int, data: bytes) -> bool:
        """Store raw pre-conversion bytes as sidecar."""
        try:
            type_name = self.get_asset_type_name(asset_type)
            raw_path = self.cache_dir / type_name / f'{asset_id}.raw'
            raw_path.parent.mkdir(exist_ok=True)
            raw_path.write_bytes(data)
            with self._lock:
                key = f'{asset_type}_{asset_id}'
                if key in self.index['assets']:
                    self.index['assets'][key]['raw_size'] = len(data)
                    self._schedule_commit()
            return True
        except Exception as e:
            print(f'Failed to store raw asset {asset_id}: {e}')
            return False

    def get_raw_asset(self, asset_id: str, asset_type: int) -> Optional[bytes]:
        try:
            type_name = self.get_asset_type_name(asset_type)
            raw_path = self.cache_dir / type_name / f'{asset_id}.raw'
            if raw_path.exists():
                return raw_path.read_bytes()
        except Exception:
            pass
        return None

    def store_asset(self, asset_id: str, asset_type: int, data: bytes,
                    url: str = '', metadata: Optional[dict] = None) -> bool:
        try:
            asset_path = self.get_asset_path(asset_id, asset_type)
            compressed = False
            if len(data) > 10240:
                with gzip.open(asset_path, 'wb') as f:
                    f.write(data)
                compressed = True
            else:
                asset_path.write_bytes(data)

            file_hash = hashlib.sha256(data).hexdigest()[:16]
            type_name = self.get_asset_type_name(asset_type)

            with self._lock:
                key = f'{asset_type}_{asset_id}'
                self.index['assets'][key] = {
                    'id': asset_id,
                    'type': asset_type,
                    'type_name': type_name,
                    'url': url,
                    'size': len(data),
                    'compressed': compressed,
                    'hash': file_hash,
                    'cached_at': datetime.now().isoformat(),
                    'metadata': metadata or {},
                }
                self._schedule_commit()

            cache_key = f'{asset_type}_{asset_id}'
            with self._asset_cache_lock:
                self._asset_cache.pop(cache_key, None)
            return True
        except Exception as e:
            print(f'Failed to store asset {asset_id}: {e}')
            return False

    def get_asset(self, asset_id: str, asset_type: int) -> Optional[bytes]:
        cache_key = f'{asset_type}_{asset_id}'
        with self._asset_cache_lock:
            if cache_key in self._asset_cache:
                return self._asset_cache[cache_key]

        try:
            asset_path = self.get_asset_path(asset_id, asset_type)
            if not asset_path.exists():
                return None

            key = f'{asset_type}_{asset_id}'
            info = self.index['assets'].get(key, {})
            if info.get('compressed', False):
                with gzip.open(asset_path, 'rb') as f:
                    data = f.read()
            else:
                data = asset_path.read_bytes()

            with self._asset_cache_lock:
                if len(self._asset_cache) >= self._asset_cache_maxsize:
                    oldest = next(iter(self._asset_cache))
                    del self._asset_cache[oldest]
                self._asset_cache[cache_key] = data
            return data
        except Exception:
            return None

    def get_asset_info(self, asset_id: str, asset_type: int) -> Optional[dict]:
        key = f'{asset_type}_{asset_id}'
        return self.index['assets'].get(key)

    def list_assets(self, type_filter: Optional[set[int]] = None) -> list[dict]:
        assets = list(self.index['assets'].values())
        if type_filter:
            int_filters = {t for t in type_filter if isinstance(t, int)}
            str_filters = {t for t in type_filter if isinstance(t, str)}
            def _matches(a):
                if int_filters and a.get('type') in int_filters:
                    return True
                if str_filters and a.get('detected_type') in str_filters:
                    return True
                return False
            assets = [a for a in assets if _matches(a)]
        assets.sort(key=lambda a: a.get('cached_at', ''), reverse=True)
        return assets

    def delete_asset(self, asset_id: str, asset_type: int) -> bool:
        try:
            asset_path = self.get_asset_path(asset_id, asset_type)
            if asset_path.exists():
                asset_path.unlink()
            with self._lock:
                key = f'{asset_type}_{asset_id}'
                self.index['assets'].pop(key, None)
                self._schedule_commit()
            cache_key = f'{asset_type}_{asset_id}'
            with self._asset_cache_lock:
                self._asset_cache.pop(cache_key, None)
            return True
        except Exception:
            return False

    def delete_assets_batch(self, assets: list[tuple[str, int]]) -> tuple[int, int]:
        deleted = 0
        failed = 0
        for asset_id, asset_type in assets:
            try:
                ap = self.get_asset_path(asset_id, asset_type)
                if ap.exists():
                    ap.unlink()
                deleted += 1
            except Exception:
                failed += 1
        with self._lock:
            for asset_id, asset_type in assets:
                key = f'{asset_type}_{asset_id}'
                self.index['assets'].pop(key, None)
            if deleted > 0:
                self._schedule_commit()
        with self._asset_cache_lock:
            for asset_id, asset_type in assets:
                self._asset_cache.pop(f'{asset_type}_{asset_id}', None)
        return deleted, failed

    def clear_cache(self) -> int:
        count = 0
        to_delete = [(info['id'], info['type']) for info in self.index['assets'].values()]
        for aid, atype in to_delete:
            if self.delete_asset(aid, atype):
                count += 1
        return count

    def get_stats(self) -> dict:
        assets = list(self.index['assets'].values())
        total_size = sum(a.get('size', 0) for a in assets)
        type_counts = {}
        for a in assets:
            tn = a.get('type_name', 'Unknown')
            type_counts[tn] = type_counts.get(tn, 0) + 1
        return {'total': len(assets), 'size': total_size, 'types': type_counts}
