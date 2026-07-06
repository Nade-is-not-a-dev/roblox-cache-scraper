"""Application paths and constants."""

import sys
from pathlib import Path

APP_NAME = 'RobloxCacheScraper'
APP_VERSION = '1.0.0'

def get_app_dir() -> Path:
    """Get the application data directory."""
    if sys.platform == 'win32':
        base = Path.home() / 'AppData' / 'Local'
    elif sys.platform == 'darwin':
        base = Path.home() / 'Library' / 'Application Support'
    else:
        base = Path.home() / '.local' / 'share'
    return base / APP_NAME

APP_DIR = get_app_dir()
CACHE_DIR = APP_DIR / 'Cache'
EXPORT_DIR = APP_DIR / 'Exports'
CONFIG_DIR = APP_DIR
LOG_FILE = APP_DIR / 'logs' / 'scraper.log'
CA_DIR = APP_DIR / 'proxy_ca'
TEXTPACK_SLOTS_DIR = CACHE_DIR / 'texpack_slots'

ASSET_DELIVERY_HOST = 'assetdelivery.roblox.com'
CDN_HOSTS = frozenset({'fts.rbxcdn.com', 'contentdelivery.roblox.com'})
GAMEJOIN_HOST = 'gamejoin.roblox.com'
INTERCEPT_HOSTS = frozenset({ASSET_DELIVERY_HOST, GAMEJOIN_HOST} | CDN_HOSTS)
