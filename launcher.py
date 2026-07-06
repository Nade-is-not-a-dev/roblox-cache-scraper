#!/usr/bin/env python3
"""PyInstaller entry point for RobloxCacheScraper executable.

This launcher is the entry point used by the PyInstaller spec file.
It imports and runs the RobloxCacheScraper application directly.
"""

import sys
from pathlib import Path


# Ensure the parent directory is on sys.path so that
# `from RobloxCacheScraper.xxx import yyy` resolves correctly.
_pkg_root = Path(__file__).resolve().parent  # RobloxCacheScraper/
_parent = _pkg_root.parent                   # parent of RobloxCacheScraper/
if str(_parent) not in sys.path:
    sys.path.insert(0, str(_parent))


if __name__ == '__main__':
    from RobloxCacheScraper.main import Application

    app = Application()
    app.run()
