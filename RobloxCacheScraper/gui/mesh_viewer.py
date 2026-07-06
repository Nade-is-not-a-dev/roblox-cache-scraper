"""Simple 3D mesh viewer widget using PyQt6 OpenGL."""

import math
import numpy as np
from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel
from PyQt6.QtOpenGLWidgets import QOpenGLWidget
from OpenGL.GL import *


class MeshGLWidget(QOpenGLWidget):
    """OpenGL widget for displaying OBJ mesh data."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMinimumSize(200, 200)

        self.vertices = []
        self.colors = []
        self.faces = []
        self.normals = []
        self.face_normals = []

        self.rot_x = 20.0
        self.rot_y = -30.0
        self.zoom = -5.0
        self.last_pos = None
        self.show_grid = True
        self.show_wireframe = False
        self.display_list = 0
        self.needs_rebuild = True

        self.timer = QTimer()
        self.timer.timeout.connect(self.update)
        self.timer.start(16)

    def load_obj(self, obj_content: str):
        """Load OBJ content."""
        self.vertices = []
        self.colors = []
        self.faces = []
        self.normals = []
        self.face_normals = []

        for line in obj_content.splitlines():
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            parts = line.split()
            if not parts:
                continue
            if parts[0] == 'v':
                x, y, z = float(parts[1]), float(parts[2]), float(parts[3])
                self.vertices.append([x, y, z])
                if len(parts) >= 7:
                    self.colors.append([float(parts[4]), float(parts[5]), float(parts[6])])
                else:
                    self.colors.append([0.7, 0.7, 0.7])
            elif parts[0] == 'vn':
                self.normals.append([float(parts[1]), float(parts[2]), float(parts[3])])
            elif parts[0] == 'f':
                vs = []
                ns = []
                for p in parts[1:]:
                    idx = p.split('/')
                    vs.append(int(idx[0]) - 1)
                    if len(idx) >= 3 and idx[2]:
                        ns.append(int(idx[2]) - 1)
                if len(vs) >= 3:
                    self.faces.append({'v': vs, 'n': ns})

        if self.vertices:
            self._normalize()
            self._compute_normals()
        self.needs_rebuild = True
        self.update()

    def _normalize(self):
        arr = np.array(self.vertices)
        center = arr.mean(axis=0)
        arr -= center
        max_dim = np.abs(arr).max()
        if max_dim > 0:
            arr /= max_dim
        self.vertices = arr.tolist()

    def _compute_normals(self):
        self.face_normals = []
        for face in self.faces:
            vi = face['v']
            if len(vi) >= 3:
                v0 = np.array(self.vertices[vi[0]])
                v1 = np.array(self.vertices[vi[1]])
                v2 = np.array(self.vertices[vi[2]])
                n = np.cross(v1 - v0, v2 - v0)
                norm = np.linalg.norm(n)
                self.face_normals.append((n / norm).tolist() if norm > 0 else [0, 1, 0])
            else:
                self.face_normals.append([0, 1, 0])

    def initializeGL(self):
        glEnable(GL_DEPTH_TEST)
        glEnable(GL_LIGHTING)
        glEnable(GL_LIGHT0)
        glEnable(GL_LIGHT1)
        glEnable(GL_COLOR_MATERIAL)
        glEnable(GL_NORMALIZE)
        glColorMaterial(GL_FRONT_AND_BACK, GL_AMBIENT_AND_DIFFUSE)
        glLightModelfv(GL_LIGHT_MODEL_TWO_SIDE, GL_TRUE)
        glLightfv(GL_LIGHT0, GL_POSITION, [1, 1, 1, 0])
        glLightfv(GL_LIGHT0, GL_AMBIENT, [0.2, 0.2, 0.2, 1])
        glLightfv(GL_LIGHT0, GL_DIFFUSE, [0.8, 0.8, 0.8, 1])
        glLightfv(GL_LIGHT1, GL_POSITION, [-1, 0.5, -1, 0])
        glLightfv(GL_LIGHT1, GL_DIFFUSE, [0.3, 0.3, 0.3, 1])
        glClearColor(0.15, 0.15, 0.18, 1)
        glShadeModel(GL_SMOOTH)

    def resizeGL(self, w, h):
        glViewport(0, 0, w, h)
        glMatrixMode(GL_PROJECTION)
        glLoadIdentity()
        aspect = w / h if h > 0 else 1
        gluPerspective(45, aspect, 0.1, 100)
        glMatrixMode(GL_MODELVIEW)

    def paintGL(self):
        glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
        glLoadIdentity()
        glTranslatef(0, 0, self.zoom)
        glRotatef(self.rot_x, 1, 0, 0)
        glRotatef(self.rot_y, 0, 1, 0)

        if self.vertices and self.faces:
            if self.needs_rebuild:
                self._build_list()
            if self.display_list:
                glCallList(self.display_list)

        if self.show_grid:
            self._draw_grid()

    def _build_list(self):
        if self.display_list:
            glDeleteLists(self.display_list, 1)
        self.display_list = glGenLists(1)
        glNewList(self.display_list, GL_COMPILE)
        glBegin(GL_TRIANGLES)
        for i, face in enumerate(self.faces):
            vi = face['v']
            if len(vi) < 3:
                continue
            if not face['n'] and i < len(self.face_normals):
                glNormal3fv(self.face_normals[i])
            for j, v_idx in enumerate(vi):
                if v_idx < len(self.vertices):
                    if self.colors and v_idx < len(self.colors):
                        glColor3fv(self.colors[v_idx])
                    if face['n'] and j < len(face['n']) and face['n'][j] < len(self.normals):
                        glNormal3fv(self.normals[face['n'][j]])
                    glVertex3fv(self.vertices[v_idx])
        glEnd()
        glEndList()
        self.needs_rebuild = False

    def _draw_grid(self):
        glPushAttrib(GL_ALL_ATTRIB_BITS)
        glDisable(GL_LIGHTING)
        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
        glColor4f(1, 1, 1, 0.08)
        glBegin(GL_LINES)
        for i in range(-8, 9):
            v = i * 0.25
            glVertex3f(v, -1, -2)
            glVertex3f(v, -1, 2)
            glVertex3f(-2, -1, v)
            glVertex3f(2, -1, v)
        glEnd()
        glPopAttrib()

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
            self.update()
        self.last_pos = event.pos()

    def wheelEvent(self, event):
        self.zoom += event.angleDelta().y() / 120.0
        self.zoom = max(-50, min(-0.1, self.zoom))
        self.update()

    def reset_view(self):
        self.rot_x = 20.0
        self.rot_y = -30.0
        self.zoom = -5.0
        self.update()

    def clear(self):
        if self.display_list:
            try:
                glDeleteLists(self.display_list, 1)
            except Exception:
                pass
            self.display_list = 0
        self.vertices = []
        self.colors = []
        self.faces = []
        self.normals = []
        self.face_normals = []
        self.needs_rebuild = True
        self.update()

    def closeEvent(self, event):
        self.timer.stop()
        super().closeEvent(event)


def gluPerspective(fov, aspect, near, far):
    """Manual gluPerspective implementation."""
    f = 1.0 / math.tan(math.radians(fov) / 2)
    glMultMatrixf([
        f / aspect, 0, 0, 0,
        0, f, 0, 0,
        0, 0, (far + near) / (near - far), -1,
        0, 0, 2 * far * near / (near - far), 0,
    ])


class MeshViewerPanel(QWidget):
    """Panel with 3D viewer and controls."""

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)

        self.viewer = MeshGLWidget()
        layout.addWidget(self.viewer, stretch=1)

        controls = QHBoxLayout()
        reset_btn = QPushButton('Reset View')
        reset_btn.clicked.connect(self.viewer.reset_view)
        controls.addWidget(reset_btn)

        grid_btn = QPushButton('Toggle Grid')
        grid_btn.clicked.connect(self._toggle_grid)
        controls.addWidget(grid_btn)

        controls.addStretch()
        self.stats = QLabel('')
        controls.addWidget(self.stats)
        layout.addLayout(controls)
        self.setLayout(layout)

    def _toggle_grid(self):
        self.viewer.show_grid = not self.viewer.show_grid
        self.viewer.update()

    def load_obj(self, obj_content: str):
        self.viewer.load_obj(obj_content)
        self.stats.setText(f'{len(self.viewer.vertices)} verts, {len(self.viewer.faces)} faces')

    def clear(self):
        self.viewer.clear()
        self.stats.setText('')
