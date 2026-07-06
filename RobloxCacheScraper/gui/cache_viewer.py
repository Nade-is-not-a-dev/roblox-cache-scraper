"""Asset cache viewer table with search, filter, and preview integration."""

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QTableWidget,
    QTableWidgetItem, QLabel, QLineEdit, QHeaderView, QMessageBox,
    QMenu, QFileDialog, QCheckBox, QGroupBox,
)
from PyQt6.QtGui import QAction, QPixmap, QImage
from pathlib import Path
import io
import gzip
import threading

from ..scraper.cache_manager import CacheManager, ASSET_TYPES
from ..utils.formats import format_size, format_count
from .audio_player import AudioPlayerWidget
from .mesh_viewer import MeshViewerPanel
from .animation_viewer import AnimationViewerPanel
from .texturepack_viewer import TexturePackViewer
from ..converters import mesh_processing
from ..converters.ktx_to_png import convert as ktx_convert


class NumericItem(QTableWidgetItem):
    """Table item that sorts numerically."""
    def __init__(self, num_val, text):
        super().__init__(text)
        self._num = num_val

    def __lt__(self, other):
        if isinstance(other, NumericItem):
            return self._num < other._num
        return super().__lt__(other)


class CacheViewerTab(QWidget):
    """Tab for viewing and managing cached Roblox assets."""

    def __init__(self, cache_manager: CacheManager, cache_scraper=None, parent=None):
        super().__init__(parent)
        self.cache_manager = cache_manager
        self.cache_scraper = cache_scraper
        self._filter_types: set = set()
        self._preview_widgets: dict = {}

        self._setup_ui()
        self._refresh_timer = QTimer()
        self._refresh_timer.timeout.connect(self._check_updates)
        self._refresh_timer.start(3000)

    def _setup_ui(self):
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)

        # Filters
        filter_group = QGroupBox('Filters')
        fl = QHBoxLayout()

        fl.addWidget(QLabel('Search:'))
        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText('Search by ID, type, name...')
        self.search_box.textChanged.connect(self._on_search)
        fl.addWidget(self.search_box)

        self.filter_btn = QPushButton('Type: All Types')
        self.filter_btn.clicked.connect(self._show_type_filter)
        fl.addWidget(self.filter_btn)

        fl.addWidget(QLabel('|'))

        self.scraper_cb = QCheckBox('Enable Cache Scraper')
        if self.cache_scraper:
            self.scraper_cb.setChecked(self.cache_scraper.enabled)
            self.scraper_cb.toggled.connect(self._toggle_scraper)
        fl.addWidget(self.scraper_cb)

        fl.addStretch()
        self.stats = QLabel('Total: 0 assets | Size: 0 B')
        fl.addWidget(self.stats)
        filter_group.setLayout(fl)
        layout.addWidget(filter_group)

        # Table
        self.table = QTableWidget()
        self.table.setColumnCount(7)
        self.table.setHorizontalHeaderLabels(['#', 'Hash/Name', 'Asset ID', 'Type', 'Size', 'Cached At', 'Content Hash'])
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(0, 40)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.ExtendedSelection)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.setSortingEnabled(True)
        self.table.itemSelectionChanged.connect(self._on_selection)
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._context_menu)
        layout.addWidget(self.table)

        # Actions
        actions = QHBoxLayout()
        delete_btn = QPushButton('Delete Selected')
        delete_btn.clicked.connect(self._delete_selected)
        actions.addWidget(delete_btn)

        clear_btn = QPushButton('Clear All')
        clear_btn.clicked.connect(self._clear_all)
        actions.addWidget(clear_btn)

        export_btn = QPushButton('Export Selected')
        export_btn.clicked.connect(self._export_selected)
        actions.addWidget(export_btn)

        actions.addStretch()

        open_btn = QPushButton('Open Cache Folder')
        open_btn.clicked.connect(self._open_cache)
        actions.addWidget(open_btn)

        layout.addLayout(actions)

        self.setLayout(layout)

    def _check_updates(self):
        """Check for new assets periodically."""
        try:
            stats = self.cache_manager.get_stats()
            self.stats.setText(f'Total: {stats["total"]} assets | Size: {format_size(stats["size"])}')
        except Exception:
            pass

    def _refresh(self):
        """Refresh the asset table."""
        search = self.search_box.text().strip().lower()
        assets = self.cache_manager.list_assets(self._filter_types if self._filter_types else None)

        # Apply search filter
        if search:
            filtered = []
            for a in assets:
                if (search in str(a.get('id', '')).lower() or
                    search in a.get('type_name', '').lower() or
                    search in a.get('hash', '').lower() or
                    search in a.get('url', '').lower()):
                    filtered.append(a)
            assets = filtered

        self.table.setSortingEnabled(False)
        self.table.setRowCount(len(assets))

        for row, asset in enumerate(assets):
            num = NumericItem(row, str(row + 1))
            num.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(row, 0, num)

            name = asset.get('hash', '')[:20]
            self.table.setItem(row, 1, QTableWidgetItem(name))
            self.table.setItem(row, 2, QTableWidgetItem(str(asset.get('id', ''))))

            type_name = self.cache_manager.get_asset_type_name(asset.get('type', 0))
            self.table.setItem(row, 3, QTableWidgetItem(type_name))

            size = asset.get('size', 0)
            size_item = NumericItem(size, format_size(size))
            self.table.setItem(row, 4, size_item)

            cached = asset.get('cached_at', '')[:19]
            self.table.setItem(row, 5, QTableWidgetItem(cached))

            self.table.setItem(row, 6, QTableWidgetItem(asset.get('hash', '')[:16]))

            # Store asset data in first column's UserRole
            self.table.item(row, 0).setData(Qt.ItemDataRole.UserRole, asset)

        self.table.setSortingEnabled(True)
        self.stats.setText(f'Total: {len(assets)} assets')

    def _on_search(self):
        QTimer.singleShot(300, self._refresh)

    def _show_type_filter(self):
        """Show asset type filter popup."""
        menu = QMenu(self)
        self._filter_types.clear()

        # Group by categories
        categories = {
            'Images': [1, 13, 63],
            'Audio': [3],
            'Meshes': [4, 39, 40],
            'Animations': [24, 48, 49, 50, 51, 52, 53, 54, 55, 56, 61, 78],
            'Clothing': [2, 11, 12],
            'Accessories': [8, 17, 18, 41, 42, 43, 44, 45, 46, 47, 57, 58, 64, 65, 66, 67, 68, 69, 70, 71, 72, 76, 77],
            'Places/Models': [9, 10],
            'Scripts/Data': [5, 6, 7, 37, 38, 73, 74, 80],
            'Other': [16, 19, 21, 22, 25, 26, 27, 28, 29, 30, 31, 32, 33, 34, 35, 59, 62, 75, 79],
        }

        def _make_handler(cat_types):
            def _handler():
                if self._filter_types == cat_types:
                    self._filter_types.clear()
                else:
                    self._filter_types = cat_types
                count = len(self._filter_types)
                if count == 0:
                    self.filter_btn.setText('Type: All Types')
                else:
                    names = [ASSET_TYPES.get(t, str(t)) for t in cat_types]
                    self.filter_btn.setText(f'Type: {names[0]}...' if len(names) == 1 else f'{count} types')
                self._refresh()
            return _handler

        for cat, type_ids in categories.items():
            action = menu.addAction(cat)
            action.triggered.connect(_make_handler(set(type_ids)))

        menu.addSeparator()
        all_action = menu.addAction('All Types')
        all_action.triggered.connect(lambda: (self._filter_types.clear(), self.filter_btn.setText('Type: All Types'), self._refresh()))

        menu.exec(self.filter_btn.mapToGlobal(self.filter_btn.rect().bottomLeft()))

    def _toggle_scraper(self, enabled: bool):
        if self.cache_scraper:
            self.cache_scraper.set_enabled(enabled)

    def _on_selection(self):
        """Handle asset selection for preview."""
        rows = self.table.selectedItems()
        if not rows:
            return

        asset = None
        for item in rows:
            data = item.data(Qt.ItemDataRole.UserRole)
            if data and isinstance(data, dict):
                asset = data
                break

        if not asset:
            return

        asset_id = asset.get('id', '')
        asset_type = asset.get('type', 0)
        self._emit_preview(asset_id, asset_type)

    def _emit_preview(self, asset_id, asset_type):
        """Show preview for the selected asset."""
        # Just mark it - parent window will handle preview display
        pass

    def get_selected_asset(self) -> dict | None:
        """Get the currently selected asset data."""
        items = self.table.selectedItems()
        if not items:
            return None
        for item in items:
            data = item.data(Qt.ItemDataRole.UserRole)
            if data and isinstance(data, dict):
                return data
        return None

    def _context_menu(self, pos):
        """Show right-click context menu."""
        item = self.table.itemAt(pos)
        if not item:
            return

        asset_data = item.data(Qt.ItemDataRole.UserRole)
        if not asset_data:
            return

        asset_id = str(asset_data.get('id', ''))
        asset_type = asset_data.get('type', 0)

        menu = QMenu(self)

        copy_id = menu.addAction(f'Copy Asset ID: {asset_id}')
        copy_id.triggered.connect(lambda: self._copy_text(asset_id))

        export = menu.addAction('Export Asset')
        export.triggered.connect(lambda: self._export_asset(asset_id, asset_type))

        delete = menu.addAction('Delete Asset')
        delete.triggered.connect(lambda: self._delete_asset(asset_id, asset_type))

        menu.addSeparator()

        preview_act = menu.addAction('Open in Preview')
        preview_act.triggered.connect(lambda: self._emit_preview(asset_id, asset_type))

        menu.exec(self.table.mapToGlobal(pos))

    def _copy_text(self, text: str):
        from PyQt6.QtGui import QGuiApplication
        QGuiApplication.clipboard().setText(text)

    def _export_asset(self, asset_id, asset_type):
        data = self.cache_manager.get_asset(asset_id, asset_type)
        if not data:
            return

        path, _ = QFileDialog.getSaveFileName(self, 'Export Asset', f'{asset_id}.bin')
        if path:
            Path(path).write_bytes(data)

    def _delete_asset(self, asset_id, asset_type):
        self.cache_manager.delete_asset(asset_id, asset_type)
        self._refresh()

    def _delete_selected(self):
        rows = set()
        for item in self.table.selectedItems():
            rows.add(item.row())

        assets = []
        for row in rows:
            data = self.table.item(row, 0).data(Qt.ItemDataRole.UserRole)
            if data:
                assets.append((data['id'], data['type']))

        if not assets:
            return

        msg = QMessageBox.question(self, 'Delete Assets',
                                    f'Delete {len(assets)} asset(s)?',
                                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if msg == QMessageBox.StandardButton.Yes:
            self.cache_manager.delete_assets_batch(assets)
            self._refresh()

    def _clear_all(self):
        msg = QMessageBox.question(self, 'Clear All',
                                    'Delete all cached assets?',
                                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if msg == QMessageBox.StandardButton.Yes:
            self.cache_manager.clear_cache()
            self._refresh()

    def _export_selected(self):
        dir_path = QFileDialog.getExistingDirectory(self, 'Select Export Directory')
        if not dir_path:
            return

        rows = set()
        for item in self.table.selectedItems():
            rows.add(item.row())

        exported = 0
        for row in rows:
            data = self.table.item(row, 0).data(Qt.ItemDataRole.UserRole)
            if data:
                aid = str(data['id'])
                atype = data['type']
                asset_data = self.cache_manager.get_asset(aid, atype)
                if asset_data:
                    Path(dir_path, f'{aid}.bin').write_bytes(asset_data)
                    exported += 1

        QMessageBox.information(self, 'Export Complete', f'Exported {exported} asset(s)')

    def _open_cache(self):
        import subprocess, sys, os
        path = str(self.cache_manager.cache_dir)
        if sys.platform == 'win32':
            os.startfile(path)
        elif sys.platform == 'darwin':
            subprocess.run(['open', path])
        else:
            subprocess.run(['xdg-open', path])
