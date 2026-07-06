"""TexturePack viewer for Roblox texture packs."""

import io
import xml.etree.ElementTree as ET
from PIL import Image
from PIL.ImageQt import ImageQt
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QScrollArea, QGroupBox,
)


class TexturePackViewer(QWidget):
    """Widget for viewing Roblox TexturePack XML contents."""

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout()
        layout.setContentsMargins(5, 5, 5, 5)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.content = QWidget()
        self.content_layout = QVBoxLayout(self.content)
        self.scroll.setWidget(self.content)
        layout.addWidget(self.scroll)
        self.setLayout(layout)

        self.images: dict[str, QLabel] = {}

    def load_texturepack(self, data: bytes):
        """Load and display TexturePack XML with textures."""
        # Clear previous
        for i in reversed(range(self.content_layout.count())):
            w = self.content_layout.itemAt(i).widget()
            if w:
                w.setParent(None)
        self.images.clear()

        # Parse XML
        xml_text = data.decode('utf-8', errors='replace')
        try:
            root = ET.fromstring(xml_text)
        except ET.ParseError:
            error_lbl = QLabel('Failed to parse TexturePack XML')
            error_lbl.setStyleSheet('color: red;')
            self.content_layout.addWidget(error_lbl)
            return

        # Extract texture maps
        found_any = False

        title = QLabel('Texture Pack Maps:')
        title.setStyleSheet('font-weight: bold; font-size: 14px;')
        self.content_layout.addWidget(title)

        for tag_name in ['Color', 'Albedo', 'Normal', 'Metalness', 'Roughness', 'Emissive', 'Height']:
            node = root.find(f'.//{tag_name}')
            if node is None:
                node = root.find(tag_name)
            if node is not None and node.text:
                texture_id = node.text.strip()
                found_any = True
                group = QGroupBox(f'{tag_name} (ID: {texture_id})')
                gl = QVBoxLayout(group)
                label = QLabel(f'Texture ID: {texture_id}')
                label.setStyleSheet('padding: 4px;')
                gl.addWidget(label)
                self.content_layout.addWidget(group)
                self.images[tag_name] = label

        if not found_any:
            # Show raw XML
            raw = QLabel(f'<pre>{xml_text[:2000]}</pre>')
            raw.setWordWrap(True)
            self.content_layout.addWidget(raw)

        self.content_layout.addStretch()

    def set_texture_image(self, map_name: str, image_data: bytes):
        """Set a texture image for a map slot."""
        if map_name not in self.images:
            return
        try:
            img = Image.open(io.BytesIO(image_data))
            img.thumbnail((128, 128), Image.LANCZOS)
            if img.mode != 'RGBA':
                img = img.convert('RGBA')
            qimage = ImageQt(img)
            pixmap = QPixmap.fromImage(qimage)
            self.images[map_name].setPixmap(pixmap)
            self.images[map_name].setFixedSize(132, 132)
        except Exception:
            pass

    def clear(self):
        for i in reversed(range(self.content_layout.count())):
            w = self.content_layout.itemAt(i).widget()
            if w:
                w.setParent(None)
        self.images.clear()
