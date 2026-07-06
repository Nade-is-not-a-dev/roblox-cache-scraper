"""Main application window with integrated cache viewer and preview panel."""

import io
import gzip
import logging
from pathlib import Path

from PIL import Image
from PIL.ImageQt import ImageQt
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPixmap, QImage, QAction
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QSplitter,
    QLabel, QPushButton, QTextEdit, QScrollArea,
    QMessageBox, QMenu, QMenuBar,
)

from RobloxCacheScraper.scraper.cache_manager import CacheManager
from RobloxCacheScraper.utils.logging import log_buffer
from RobloxCacheScraper.utils.formats import format_size
from RobloxCacheScraper.utils.paths import CACHE_DIR
from .cache_viewer import CacheViewerTab
from .audio_player import AudioPlayerWidget
from .mesh_viewer import MeshViewerPanel
from .animation_viewer import AnimationViewerPanel
from .texturepack_viewer import TexturePackViewer
from ..converters import mesh_processing
from ..converters.ktx_to_png import convert as ktx_convert

logger = logging.getLogger(__name__)

_KTX_MAGICS = (b'\xabKTX 11\xbb', b'\xabKTX 20\xbb')


class PreviewPanel(QWidget):
    """Panel for previewing selected assets."""

    def __init__(self, cache_manager: CacheManager, parent=None):
        super().__init__(parent)
        self.cache_manager = cache_manager
        self._current_asset = None
        self._audio_player = None
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout()
        layout.setContentsMargins(5, 5, 5, 5)

        self.title = QLabel('Select an asset to preview')
        self.title.setStyleSheet('font-weight: bold; font-size: 14px; padding: 4px;')
        layout.addWidget(self.title)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.content = QWidget()
        self.content_layout = QVBoxLayout(self.content)
        self.scroll.setWidget(self.content)
        layout.addWidget(self.scroll, stretch=1)

        self.close_btn = QPushButton('Close Preview')
        self.close_btn.clicked.connect(self.clear)
        layout.addWidget(self.close_btn)

        self.setLayout(layout)

    def show_asset(self, asset_id: str, asset_type: int):
        """Show preview for the given asset."""
        self.clear()
        self._current_asset = {'id': asset_id, 'type': asset_type}

        data = self.cache_manager.get_asset(asset_id, asset_type)
        if not data:
            self._add_info(f'Asset {asset_id} not found in cache')
            return

        type_name = self.cache_manager.get_asset_type_name(asset_type)
        self.title.setText(f'Preview: {type_name} #{asset_id}')

        # Decompress if needed
        inner = data
        if data[:2] == b'\x1f\x8b':
            try:
                inner = gzip.decompress(data)
            except Exception:
                pass

        try:
            if asset_type in (1, 13):  # Image / Decal
                self._show_image(inner)
            elif asset_type == 3:  # Audio
                self._show_audio(data)
            elif asset_type == 4 or asset_type == 40:  # Mesh / MeshPart
                self._show_mesh(inner)
            elif asset_type == 24 or (48 <= asset_type <= 56) or asset_type == 61 or asset_type == 78:  # Animation
                self._show_animation(data)
            elif asset_type == 63:  # TexturePack
                self._show_texturepack(inner)
            elif asset_type == 39:  # SolidModel
                self._show_mesh(inner)
            else:
                try:
                    text = inner.decode('utf-8', errors='replace')
                    if len(text) < 50000:
                        self._add_text(text[:20000])
                    else:
                        self._add_info(f'Binary data: {format_size(len(data))}')
                except Exception:
                    self._add_info(f'Binary data: {format_size(len(data))}')
        except Exception as exc:
            self._add_info(f'Preview error: {exc}')
            logger.exception('Preview error for %s', asset_id)

    def _show_image(self, data: bytes):
        """Display image preview."""
        if data[:8] in _KTX_MAGICS:
            png = ktx_convert(data)
            if png:
                data = png

        try:
            img = Image.open(io.BytesIO(data))
            img.thumbnail((400, 400), Image.LANCZOS)
            if img.mode not in ('RGB', 'RGBA'):
                img = img.convert('RGBA')
            elif img.mode == 'RGB':
                img = img.convert('RGBA')

            qimage = QImage(img.tobytes(), img.width, img.height,
                          QImage.Format.Format_RGBA8888)
            pixmap = QPixmap.fromImage(qimage)
            label = QLabel()
            label.setPixmap(pixmap)
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            label.setStyleSheet('background-color: #222; padding: 10px;')
            info = QLabel(f'{img.width} x {img.height} px')
            info.setAlignment(Qt.AlignmentFlag.AlignCenter)
            info.setStyleSheet('color: #888; padding: 2px;')
            self.content_layout.addWidget(info)
            self.content_layout.addWidget(label)
        except Exception as exc:
            self._add_info(f'Image load failed: {exc}')

    def _show_audio(self, data: bytes):
        """Display audio player."""
        player = AudioPlayerWidget(data)
        self.content_layout.addWidget(player)
        self._audio_player = player

    def _show_mesh(self, data: bytes):
        """Display 3D mesh viewer."""
        obj = mesh_processing.convert(data)
        if obj:
            viewer = MeshViewerPanel()
            viewer.load_obj(obj)
            self.content_layout.addWidget(viewer, stretch=1)
        else:
            self._add_info('Mesh conversion failed')

    def _show_animation(self, data: bytes):
        """Display animation viewer."""
        viewer = AnimationViewerPanel()
        viewer.load_animation(data)
        self.content_layout.addWidget(viewer, stretch=1)

    def _show_texturepack(self, data: bytes):
        """Display TexturePack viewer."""
        viewer = TexturePackViewer()
        viewer.load_texturepack(data)
        self.content_layout.addWidget(viewer, stretch=1)

    def _add_info(self, text: str):
        label = QLabel(text)
        label.setWordWrap(True)
        label.setStyleSheet('padding: 8px; color: #aaa;')
        self.content_layout.addWidget(label)

    def _add_text(self, text: str):
        text_w = QTextEdit()
        text_w.setReadOnly(True)
        text_w.setPlainText(text)
        text_w.setStyleSheet('background-color: #1e1e1e; color: #d4d4d4; font-family: monospace;')
        self.content_layout.addWidget(text_w)

    def clear(self):
        """Clear preview."""
        # Stop audio if playing
        if self._audio_player:
            try:
                self._audio_player.stop()
            except Exception:
                pass
            self._audio_player = None

        self._current_asset = None
        self.title.setText('Select an asset to preview')
        for i in reversed(range(self.content_layout.count())):
            w = self.content_layout.itemAt(i).widget()
            if w:
                w.setParent(None)


class MainWindow(QMainWindow):
    """Main application window."""

    def __init__(self, cache_manager: CacheManager, cache_scraper=None, app=None):
        super().__init__()
        self.cache_manager = cache_manager
        self.cache_scraper = cache_scraper
        self._app = app

        self.setWindowTitle('RobloxCacheScraper')
        self.setMinimumSize(1000, 600)

        # Menu bar
        menubar = self.menuBar()
        file_menu = menubar.addMenu('&File')

        exit_action = QAction('E&xit', self)
        exit_action.setShortcut('Ctrl+Q')
        exit_action.triggered.connect(self._exit_app)
        file_menu.addAction(exit_action)

        help_menu = menubar.addMenu('&Help')
        about_action = QAction('&About', self)
        about_action.triggered.connect(self._show_about)
        help_menu.addAction(about_action)

        # Central widget
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)

        # Status bar at top
        status_bar = QHBoxLayout()
        self.status_label = QLabel('Proxy: Stopped | Scraper: Disabled')
        self.status_label.setStyleSheet('padding: 4px 8px; background-color: #333; color: #ccc;')
        status_bar.addWidget(self.status_label)
        status_bar.addStretch()
        layout.addLayout(status_bar)

        # Splitter: table + preview
        self.splitter = QSplitter(Qt.Orientation.Horizontal)

        self.cache_viewer = CacheViewerTab(cache_manager, cache_scraper)
        self.splitter.addWidget(self.cache_viewer)

        self.preview = PreviewPanel(cache_manager)
        self.splitter.addWidget(self.preview)

        self.splitter.setSizes([600, 300])
        layout.addWidget(self.splitter, stretch=1)

        # Bottom action bar
        actions = QHBoxLayout()
        actions.setContentsMargins(8, 4, 8, 4)

        self.start_btn = QPushButton('Start Proxy')
        actions.addWidget(self.start_btn)

        self.scraper_btn = QPushButton('Enable Scraper')
        self.scraper_btn.clicked.connect(self._toggle_scraper)
        actions.addWidget(self.scraper_btn)

        actions.addStretch()

        layout.addLayout(actions)

        # Wire up selection
        self.cache_viewer.table.itemSelectionChanged.connect(self._on_selection)

    def _on_selection(self):
        """Show preview for selected asset."""
        asset = self.cache_viewer.get_selected_asset()
        if asset:
            self.preview.show_asset(str(asset['id']), asset['type'])
        else:
            self.preview.clear()

    def _toggle_scraper(self):
        if self.cache_scraper:
            enabled = not self.cache_scraper.enabled
            self.cache_scraper.set_enabled(enabled)
            self.scraper_btn.setText('Disable Scraper' if enabled else 'Enable Scraper')
            self._update_status()

    def _update_status(self):
        proxy = 'Running' if getattr(self, '_proxy_running', False) else 'Stopped'
        scraper = 'Enabled' if (self.cache_scraper and self.cache_scraper.enabled) else 'Disabled'
        self.status_label.setText(f'Proxy: {proxy} | Scraper: {scraper}')

    def set_proxy_running(self, running: bool):
        self._proxy_running = running
        self.start_btn.setText('Stop Proxy' if running else 'Start Proxy')
        self._update_status()

    def _exit_app(self):
        """Clean application exit."""
        if self._app and hasattr(self._app, 'quit'):
            self._app.quit()
        else:
            self.close()

    def _show_about(self):
        from RobloxCacheScraper import __version__
        QMessageBox.about(self, 'About RobloxCacheScraper',
                          f'<h3>RobloxCacheScraper v{__version__}</h3>'
                          '<p>A standalone cache scraper for Roblox assets.</p>'
                          '<p>Intercepts and caches Roblox asset traffic through a local MITM proxy.</p>'
                          '<p>Built with PyQt6 + PyOpenGL</p>')
