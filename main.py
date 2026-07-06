#!/usr/bin/env python3
"""RobloxCacheScraper - Main entry point.

A standalone application that intercepts Roblox asset traffic through a local
MITM proxy, caches all downloaded assets, and provides a GUI to browse, filter,
and preview them.

Usage:
    python -m RobloxCacheScraper.main
       or
    python -m RobloxCacheScraper
"""

import asyncio
import logging
import sys
import threading
from pathlib import Path

from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QApplication, QMessageBox

from RobloxCacheScraper import __version__
from RobloxCacheScraper.gui.main_window import MainWindow
from RobloxCacheScraper.scraper.cache_manager import CacheManager
from RobloxCacheScraper.scraper.cache_scraper import CacheScraper
from RobloxCacheScraper.proxy.certs import generate_ca, generate_multi_host_cert
from RobloxCacheScraper.proxy.upstream import UpstreamConnector
from RobloxCacheScraper.proxy.server import ProxyServer, INTERCEPT_HOSTS
from RobloxCacheScraper.utils.paths import (
    APP_DIR, CACHE_DIR, CA_DIR, LOG_FILE,
)
from RobloxCacheScraper.utils.logging import log_buffer, setup_file_logging

logger = logging.getLogger(__name__)


class Application:
    """Main application orchestrator."""

    def __init__(self):
        self.app = QApplication(sys.argv)
        self.app.setApplicationName('RobloxCacheScraper')
        self.app.setApplicationDisplayName('RobloxCacheScraper')
        self.app.setQuitOnLastWindowClosed(False)

        # Create directories
        APP_DIR.mkdir(parents=True, exist_ok=True)
        CACHE_DIR.mkdir(parents=True, exist_ok=True)

        # Setup logging
        setup_file_logging(LOG_FILE)

        # Core components
        self.cache_manager = CacheManager(CACHE_DIR)
        self.cache_scraper = CacheScraper(self.cache_manager)
        self.upstream = UpstreamConnector()
        self.proxy_server = None
        self._proxy_task = None
        self._loop = None
        self._proxy_running = False

        # Main window
        self.window = MainWindow(self.cache_manager, self.cache_scraper, self)
        self.window.set_proxy_running(False)

        # Wire up proxy toggle
        try:
            self.window.start_btn.clicked.disconnect()
        except TypeError:
            pass
        self.window.start_btn.clicked.connect(self._toggle_proxy)

        # Start async event loop in background
        self._start_async_loop()

        log_buffer.log('App', f'RobloxCacheScraper v{__version__} started')
        logger.info('Application started v%s', __version__)

    def quit(self):
        """Clean shutdown."""
        self._stop_proxy()
        if self._loop and not self._loop.is_closed():
            self._loop.call_soon_threadsafe(self._loop.stop)
        self.app.quit()

    def _start_async_loop(self):
        """Start the asyncio event loop in a background thread."""
        self._loop = asyncio.new_event_loop()

        def run_loop():
            asyncio.set_event_loop(self._loop)
            self._loop.run_forever()

        t = threading.Thread(target=run_loop, daemon=True)
        t.start()

    def _toggle_proxy(self):
        """Start or stop the proxy server."""
        if self._proxy_running:
            self._stop_proxy()
        else:
            self._start_proxy()

    def _start_proxy(self):
        """Start the MITM proxy server."""
        try:
            # Generate CA cert
            ca_cert, ca_key = generate_ca(CA_DIR)
            logger.info('CA certificate ready: %s', ca_cert)

            # Generate host certs for each intercepted host
            host_certs = {}
            for host in INTERCEPT_HOSTS:
                host_certs[host] = generate_multi_host_cert(
                    [host], ca_cert, ca_key, CA_DIR,
                )
            # Generate multi-host default cert
            default_cert = generate_multi_host_cert(
                list(INTERCEPT_HOSTS), ca_cert, ca_key, CA_DIR,
            )

            # Create proxy server
            self.proxy_server = ProxyServer(
                on_batch_response=self.cache_scraper.process_batch_response,
                on_cdn_response=self.cache_scraper.process_cdn_response,
                host_certs=host_certs,
                default_cert=default_cert,
                port=443,
                upstream_connect=self.upstream.connect,
            )

            # Start in event loop
            async def start():
                await self.proxy_server.start()
                log_buffer.log('Proxy', 'Proxy started on 127.0.0.1:443')
                logger.info('Proxy listening on 127.0.0.1:443')

            if self._loop and not self._loop.is_closed():
                future = asyncio.run_coroutine_threadsafe(start(), self._loop)
                future.result(timeout=10)
                self._proxy_running = True
                self.window.set_proxy_running(True)
                log_buffer.log('Proxy', 'MITM proxy is now active')

                # Warn about hosts file
                self._show_hosts_info()
        except Exception as exc:
            logger.exception('Failed to start proxy')
            log_buffer.log('Proxy', f'Failed to start proxy: {exc}')
            QMessageBox.critical(
                self.window, 'Proxy Error',
                f'Failed to start proxy server:\n\n{exc}\n\n'
                'Make sure port 443 is not in use and you have admin rights.',
            )

    def _show_hosts_info(self):
        """Show information about hosts file requirements."""
        msg = QMessageBox(self.window)
        msg.setWindowTitle('Hosts File Required')
        msg.setIcon(QMessageBox.Icon.Information)
        msg.setText('Proxy is running on port 443.')
        msg.setInformativeText(
            'For the proxy to intercept Roblox traffic, you need to add these '
            'entries to your hosts file (requires administrator privileges):\n\n'
            '127.0.0.1  assetdelivery.roblox.com\n'
            '127.0.0.1  fts.rbxcdn.com\n'
            '127.0.0.1  contentdelivery.roblox.com\n'
            '127.0.0.1  gamejoin.roblox.com\n\n'
            'Also install the CA certificate at:\n'
            f'{CA_DIR / "ca.crt"}\n\n'
            'Into Roblox SSL trust store (ssl/cacert.pem).\n\n'
            'On Windows, run this program as Administrator for automatic setup.'
        )
        msg.exec()

    def _stop_proxy(self):
        """Stop the proxy server."""
        if not self._proxy_running or not self.proxy_server:
            return

        async def stop():
            await self.proxy_server.stop()
            log_buffer.log('Proxy', 'Proxy stopped')

        if self._loop and not self._loop.is_closed():
            future = asyncio.run_coroutine_threadsafe(stop(), self._loop)
            try:
                future.result(timeout=10)
            except Exception as exc:
                logger.error('Error stopping proxy: %s', exc)

        self._proxy_running = False
        self.window.set_proxy_running(False)
        log_buffer.log('Proxy', 'Proxy stopped')

    def run(self):
        """Run the application."""
        self.window.show()
        sys.exit(self.app.exec())


def main():
    """Application entry point."""
    app = Application()
    app.run()


if __name__ == '__main__':
    main()
