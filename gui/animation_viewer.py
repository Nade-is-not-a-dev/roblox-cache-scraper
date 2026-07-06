"""Simple animation viewer for Roblox animations with R15/R6 rig support."""

import struct
import gzip
import logging
import xml.etree.ElementTree as ET
import math
import numpy as np
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QSlider
from PyQt6.QtOpenGLWidgets import QOpenGLWidget
from OpenGL.GL import *

logger = logging.getLogger(__name__)


def _detect_rig(data: bytes) -> str:
    """Detect if animation data is R15, R6, or unknown."""
    text = data.decode('utf-8', errors='replace')
    if 'UpperTorso' in text or 'LowerTorso' in text:
        return 'R15'
    if 'Torso' in text and 'UpperTorso' not in text:
        return 'R6'
    return 'unknown'


def _parse_keyframes(data: bytes) -> list:
    """Parse animation keyframes from XML."""
    text = data.decode('utf-8', errors='replace')
    if '<roblox' in text:
        try:
            root = ET.fromstring(text)
        except ET.ParseError:
            return []
    else:
        return []

    keyframes = []
    for ks in root.iter('KeyframeSequence'):
        for kf in ks.iter('Keyframe'):
            time = float(kf.get('time', 0))
            for pose in kf.iter('Pose'):
                part = pose.get('part', '')
                cf = pose.find('CoordinateFrame')
                if cf is not None:
                    # Parse CFrame: x, y, z, r00, r01, r02, r10, r11, r12, r20, r21, r22
                    vals = cf.text.strip().split() if cf.text else []
                    if len(vals) >= 12:
                        keyframes.append({
                            'time': time,
                            'part': part,
                            'pos': [float(vals[0]), float(vals[1]), float(vals[2])],
                            'rot': [
                                [float(vals[3]), float(vals[4]), float(vals[5])],
                                [float(vals[6]), float(vals[7]), float(vals[8])],
                                [float(vals[9]), float(vals[10]), float(vals[11])],
                            ],
                        })
    return keyframes


# Simple stick-figure rig positions (relative to root)
R15_PARTS = {
    'HumanoidRootPart': (0, 0, 0),
    'UpperTorso': (0, 0.5, 0),
    'LowerTorso': (0, -0.3, 0),
    'Head': (0, 1.0, 0),
    'LeftUpperArm': (-0.5, 0.4, 0),
    'LeftLowerArm': (-0.8, 0.1, 0),
    'LeftHand': (-1.0, -0.1, 0),
    'RightUpperArm': (0.5, 0.4, 0),
    'RightLowerArm': (0.8, 0.1, 0),
    'RightHand': (1.0, -0.1, 0),
    'LeftUpperLeg': (-0.2, -0.6, 0),
    'LeftLowerLeg': (-0.2, -1.1, 0),
    'LeftFoot': (-0.2, -1.5, 0),
    'RightUpperLeg': (0.2, -0.6, 0),
    'RightLowerLeg': (0.2, -1.1, 0),
    'RightFoot': (0.2, -1.5, 0),
}

R6_PARTS = {
    'HumanoidRootPart': (0, 0, 0),
    'Torso': (0, 0.3, 0),
    'Head': (0, 0.9, 0),
    'Left Arm': (-0.6, 0.3, 0),
    'Right Arm': (0.6, 0.3, 0),
    'Left Leg': (-0.2, -0.5, 0),
    'Right Leg': (0.2, -0.5, 0),
}

PART_CONNECTIONS_R15 = [
    ('HumanoidRootPart', 'UpperTorso'),
    ('HumanoidRootPart', 'LowerTorso'),
    ('UpperTorso', 'Head'),
    ('UpperTorso', 'LeftUpperArm'),
    ('LeftUpperArm', 'LeftLowerArm'),
    ('LeftLowerArm', 'LeftHand'),
    ('UpperTorso', 'RightUpperArm'),
    ('RightUpperArm', 'RightLowerArm'),
    ('RightLowerArm', 'RightHand'),
    ('LowerTorso', 'LeftUpperLeg'),
    ('LeftUpperLeg', 'LeftLowerLeg'),
    ('LeftLowerLeg', 'LeftFoot'),
    ('LowerTorso', 'RightUpperLeg'),
    ('RightUpperLeg', 'RightLowerLeg'),
    ('RightLowerLeg', 'RightFoot'),
]

PART_CONNECTIONS_R6 = [
    ('HumanoidRootPart', 'Torso'),
    ('Torso', 'Head'),
    ('Torso', 'Left Arm'),
    ('Torso', 'Right Arm'),
    ('Torso', 'Left Leg'),
    ('Torso', 'Right Leg'),
]


class AnimationGLWidget(QOpenGLWidget):
    """OpenGL widget for animating rigs."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(200, 200)
        self.keyframes = []
        self.rig_type = 'R15'
        self.current_time = 0.0
        self.is_playing = False
        self.speed = 1.0
        self.rot_x = 25.0
        self.rot_y = -45.0
        self.zoom = -8.0
        self.last_pos = None

        self.timer = QTimer()
        self.timer.timeout.connect(self._tick)
        self.timer.start(16)

    def load_animation(self, data: bytes):
        """Load animation data."""
        inner = data
        if data[:2] == b'\x1f\x8b':
            try:
                inner = gzip.decompress(data)
            except Exception:
                pass
        self.rig_type = _detect_rig(inner)
        self.keyframes = _parse_keyframes(inner)
        self.current_time = 0.0
        self.is_playing = len(self.keyframes) > 0
        logger.info('Loaded %s animation with %d keyframes', self.rig_type, len(self.keyframes))

    def _tick(self):
        if self.is_playing and self.keyframes:
            duration = max(kf['time'] for kf in self.keyframes) if self.keyframes else 1.0
            self.current_time += 0.016 * self.speed
            if self.current_time > duration:
                self.current_time = 0.0
        self.update()

    def initializeGL(self):
        glEnable(GL_DEPTH_TEST)
        glClearColor(0.15, 0.15, 0.18, 1)
        glLineWidth(3.0)

    def resizeGL(self, w, h):
        glViewport(0, 0, w, h)
        glMatrixMode(GL_PROJECTION)
        glLoadIdentity()
        aspect = w / h if h > 0 else 1
        fov = 45
        f = 1.0 / math.tan(math.radians(fov) / 2)
        near, far = 0.1, 100
        glMultMatrixf([
            f / aspect, 0, 0, 0,
            0, f, 0, 0,
            0, 0, (far + near) / (near - far), -1,
            0, 0, 2 * far * near / (near - far), 0,
        ])
        glMatrixMode(GL_MODELVIEW)

    def paintGL(self):
        glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
        glLoadIdentity()
        glTranslatef(0, -0.3, self.zoom)
        glRotatef(self.rot_x, 1, 0, 0)
        glRotatef(self.rot_y, 0, 1, 0)

        parts = R15_PARTS if self.rig_type == 'R15' else R6_PARTS
        connections = PART_CONNECTIONS_R15 if self.rig_type == 'R15' else PART_CONNECTIONS_R6

        # Get interpolated positions
        positions = {}
        for part_name, base_pos in parts.items():
            # Apply keyframe offsets
            offset = self._get_offset(part_name)
            positions[part_name] = (
                base_pos[0] + offset[0],
                base_pos[1] + offset[1],
                base_pos[2] + offset[2],
            )

        # Draw connections (skeleton)
        glDisable(GL_LIGHTING)
        glLineWidth(4.0)
        for p1, p2 in connections:
            if p1 in positions and p2 in positions:
                glBegin(GL_LINES)
                glColor3f(0.3, 0.6, 1.0)  # Blue skeleton
                glVertex3fv(positions[p1])
                glVertex3fv(positions[p2])
                glEnd()

        # Draw joint spheres
        for part_name, pos in positions.items():
            glPushMatrix()
            glTranslatef(*pos)
            glColor3f(0.2, 0.8, 0.3)  # Green joints
            self._draw_sphere(0.08, 8, 8)
            glPopMatrix()

        # Draw head slightly larger
        head_pos = positions.get('Head')
        if head_pos:
            glPushMatrix()
            glTranslatef(*head_pos)
            glColor3f(1.0, 0.8, 0.4)  # Skin color
            self._draw_sphere(0.15, 10, 10)
            glPopMatrix()

        glEnable(GL_LIGHTING)

    def _draw_sphere(self, radius, slices, stacks):
        """Draw a sphere using GL_QUADS."""
        for i in range(stacks):
            lat0 = math.pi * (-0.5 + (i / stacks))
            z0 = math.sin(lat0) * radius
            zr0 = math.cos(lat0) * radius
            lat1 = math.pi * (-0.5 + ((i + 1) / stacks))
            z1 = math.sin(lat1) * radius
            zr1 = math.cos(lat1) * radius
            glBegin(GL_QUAD_STRIP)
            for j in range(slices + 1):
                lng = 2 * math.pi * (j / slices)
                x = math.cos(lng)
                y = math.sin(lng)
                glNormal3f(x * zr0, y * zr0, z0)
                glVertex3f(x * zr0, y * zr0, z0)
                glNormal3f(x * zr1, y * zr1, z1)
                glVertex3f(x * zr1, y * zr1, z1)
            glEnd()

    def _get_offset(self, part: str) -> tuple:
        """Get interpolated keyframe offset for a part."""
        if not self.keyframes:
            return (0, 0, 0)
        part_kfs = [kf for kf in self.keyframes if kf['part'] == part]
        if not part_kfs:
            return (0, 0, 0)

        duration = max(kf['time'] for kf in self.keyframes)
        t = self.current_time % max(duration, 0.001)

        # Find surrounding keyframes
        before = None
        after = None
        for kf in part_kfs:
            if kf['time'] <= t and (before is None or kf['time'] > before['time']):
                before = kf
            if kf['time'] >= t and (after is None or kf['time'] < after['time']):
                after = kf

        if before is None and after:
            return tuple(after['pos'])
        if after is None and before:
            return tuple(before['pos'])
        if before and after:
            if after['time'] == before['time']:
                return tuple(before['pos'])
            frac = (t - before['time']) / (after['time'] - before['time'])
            return (
                before['pos'][0] + (after['pos'][0] - before['pos'][0]) * frac,
                before['pos'][1] + (after['pos'][1] - before['pos'][1]) * frac,
                before['pos'][2] + (after['pos'][2] - before['pos'][2]) * frac,
            )
        return (0, 0, 0)

    def mousePressEvent(self, event):
        self.last_pos = event.pos()

    def mouseMoveEvent(self, event):
        if self.last_pos is None:
            return
        dx = event.pos().x() - self.last_pos.x()
        dy = event.pos().y() - self.last_pos.y()
        if event.buttons() & Qt.MouseButton.LeftButton:
            self.rot_x += dy * 0.5
            self.rot_y += dx * 0.5
        self.last_pos = event.pos()

    def wheelEvent(self, event):
        self.zoom += event.angleDelta().y() / 120.0
        self.zoom = max(-50, min(-2, self.zoom))

    def clear(self):
        self.keyframes = []
        self.current_time = 0.0
        self.is_playing = False
        self.update()


class AnimationViewerPanel(QWidget):
    """Animation viewer with playback controls."""

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)

        self.viewer = AnimationGLWidget()
        layout.addWidget(self.viewer, stretch=1)

        controls = QHBoxLayout()
        self.play_btn = QPushButton('⏸' if self.viewer.is_playing else '▶')
        self.play_btn.clicked.connect(self._toggle_play)
        controls.addWidget(self.play_btn)

        controls.addWidget(QLabel('Speed:'))
        self.speed_slider = QSlider(Qt.Orientation.Horizontal)
        self.speed_slider.setRange(10, 300)
        self.speed_slider.setValue(100)
        self.speed_slider.valueChanged.connect(lambda v: setattr(self.viewer, 'speed', v / 100))
        controls.addWidget(self.speed_slider)

        reset_btn = QPushButton('Reset View')
        reset_btn.clicked.connect(lambda: self.viewer.__setattr__('rot_x', 25) or self.viewer.__setattr__('rot_y', -45) or self.viewer.__setattr__('zoom', -8))
        controls.addWidget(reset_btn)

        controls.addStretch()
        self.info = QLabel('No animation loaded')
        controls.addWidget(self.info)
        layout.addLayout(controls)
        self.setLayout(layout)

    def _toggle_play(self):
        self.viewer.is_playing = not self.viewer.is_playing
        self.play_btn.setText('⏸' if self.viewer.is_playing else '▶')

    def load_animation(self, data: bytes):
        self.viewer.load_animation(data)
        rig = self.viewer.rig_type
        kf_count = len(self.viewer.keyframes)
        self.info.setText(f'{rig} | {kf_count} keyframes')
        self.play_btn.setText('⏸' if self.viewer.is_playing else '▶')

    def clear(self):
        self.viewer.clear()
        self.info.setText('No animation loaded')
        self.play_btn.setText('▶')
