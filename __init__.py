"""RobloxCacheScraper - A standalone cache scraper for Roblox assets.

Usage:
    python -m RobloxCacheScraper
"""

import sys
from pathlib import Path

# Ensure the package directory is on sys.path for absolute imports
_pkg_dir = str(Path(__file__).resolve().parent)
if _pkg_dir not in sys.path:
    sys.path.insert(0, str(Path(_pkg_dir).parent))

__version__ = '1.0.0'


def main():
    """Run the application."""
    from RobloxCacheScraper.main import main as _main
    _main()


if __name__ == '__main__':
    main()
