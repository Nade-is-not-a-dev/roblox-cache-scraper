# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec for RobloxCacheScraper.

Build on any platform:
    pyinstaller RobloxCacheScraper.spec

This produces:
  - Windows: single-file .exe in dist/
  - macOS:   .app bundle in dist/
  - Linux:   single-file executable in dist/

Prerequisites:
    pip install -r requirements.txt
    pip install pyinstaller
"""

import importlib.util
import os
import re
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_all, collect_submodules


# ── Version from __init__.py ─────────────────────────────────────────────
# SPEC is automatically set by PyInstaller to the spec file path.
_spec_path = Path(SPEC) if 'SPEC' in dir() else Path.cwd() / 'RobloxCacheScraper.spec'
_init_py = _spec_path.resolve().parent / '__init__.py'
_version_match = re.search(
    r"__version__\s*=\s*['\"]([^'\"]+)['\"]",
    _init_py.read_text(encoding='utf-8'),
)
_version = _version_match.group(1) if _version_match else '1.0.0'

# ── Platform detection ───────────────────────────────────────────────────
_is_win = sys.platform == 'win32'
_is_macos = sys.platform == 'darwin'
_is_linux = sys.platform.startswith('linux')

# macOS target arch (set MACOS_TARGET_ARCH=arm64/x86_64 for single-arch build)
_macos_target_arch = os.environ.get('MACOS_TARGET_ARCH', 'universal2') if _is_macos else None


# ── Data files ───────────────────────────────────────────────────────────
datas = []

# ── Binary files ─────────────────────────────────────────────────────────
binaries = []

# ── Hidden imports ───────────────────────────────────────────────────────
hiddenimports = []


# ═══════════════════════════════════════════════════════════════════════════
#  COLLECT ALL DEPENDENCIES
# ═══════════════════════════════════════════════════════════════════════════

# cryptography (Rust/C binary extensions)
tmp = collect_all('cryptography')
datas += tmp[0]; binaries += tmp[1]; hiddenimports += tmp[2]

# certifi (bundled CA certificates for SSL)
tmp = collect_all('certifi')
datas += tmp[0]; binaries += tmp[1]; hiddenimports += tmp[2]

# numpy (C extensions)
tmp = collect_all('numpy')
datas += tmp[0]; binaries += tmp[1]; hiddenimports += tmp[2]

# PyQt6 (many sub-packages — collect_all ensures nothing is missed)
tmp = collect_all('PyQt6')
datas += tmp[0]; binaries += tmp[1]; hiddenimports += tmp[2]

# PyOpenGL — resolves platform backends dynamically at runtime.
# Ensure GLX, EGL, and win32 backends are bundled so the 3D viewers work
# regardless of the user's display server.
hiddenimports += collect_submodules('OpenGL.arrays')
hiddenimports += [
    'OpenGL.platform.glx',
    'OpenGL.platform.egl',
    'OpenGL.platform.win32',
]

# Pillow (image processing — format plugins)
tmp = collect_all('PIL')
datas += tmp[0]; binaries += tmp[1]; hiddenimports += tmp[2]

# requests + urllib3 (HTTP client for Roblox API calls)
hiddenimports += collect_submodules('requests')
hiddenimports += collect_submodules('urllib3')

# orjson (fast JSON — compiled C extension)
hiddenimports += collect_submodules('orjson')

# zstandard (CDN payload decompression — compiled C extension)
tmp = collect_all('zstandard')
datas += tmp[0]; binaries += tmp[1]; hiddenimports += tmp[2]

# lz4 (compression support)
tmp = collect_all('lz4')
datas += tmp[0]; binaries += tmp[1]; hiddenimports += tmp[2]

# python-dateutil (date parsing)
tmp = collect_all('dateutil')
datas += tmp[0]; binaries += tmp[1]; hiddenimports += tmp[2]

# platformdirs (cross-platform directory discovery)
tmp = collect_all('platformdirs')
datas += tmp[0]; binaries += tmp[1]; hiddenimports += tmp[2]

# sounddevice + soundfile (audio playback — explicit hidden imports for safety)
hiddenimports += ['sounddevice', 'soundfile']
for audio_runtime_pkg in ('_sounddevice_data', '_soundfile_data'):
    spec = importlib.util.find_spec(audio_runtime_pkg)
    if spec is not None:
        tmp = collect_all(audio_runtime_pkg)
        datas += tmp[0]; binaries += tmp[1]; hiddenimports += tmp[2]


# ═══════════════════════════════════════════════════════════════════════════
#  PLATFORM-SPECIFIC
# ═══════════════════════════════════════════════════════════════════════════

if _is_win:
    hiddenimports += [
        'win32api', 'win32con', 'win32crypt', 'win32event',
        'win32gui', 'win32net', 'win32process', 'win32security',
        'win32service', 'win32shell', 'win32ts', 'win32ver',
        'win32wnet', 'pywintypes', 'winreg',
    ]
    tmp = collect_all('win11toast')
    datas += tmp[0]; binaries += tmp[1]; hiddenimports += tmp[2]

elif _is_macos:
    tmp = collect_all('browser_cookie3')
    datas += tmp[0]; binaries += tmp[1]; hiddenimports += tmp[2]
    tmp = collect_all('Cryptodome')
    datas += tmp[0]; binaries += tmp[1]; hiddenimports += tmp[2]

elif _is_linux:
    tmp = collect_all('browser_cookie3')
    datas += tmp[0]; binaries += tmp[1]; hiddenimports += tmp[2]


# ═══════════════════════════════════════════════════════════════════════════
#  ENTRY-POINT ANALYSIS
# ═══════════════════════════════════════════════════════════════════════════
#
# pathex: MUST point to the **parent** of the RobloxCacheScraper/ package
# directory so that `from RobloxCacheScraper.xxx import yyy` resolves.
# The spec file lives inside RobloxCacheScraper/, so __file__.parent.parent
# is the correct value.

# spec directory = parent of the spec file path
_spec_dir = _spec_path.resolve().parent             # RobloxCacheScraper/
_package_parent = str(_spec_dir.parent)              # parent directory

a = Analysis(
    ['launcher.py'],
    pathex=[_package_parent],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # GUI frameworks not used
        'PySide6', 'PyQt5', 'PyQt4', 'tkinter',

        # Data-science packages not used
        'matplotlib', 'scipy', 'pandas', 'notebook', 'jupyter', 'IPython',

        # Qt modules not used by the app (saves ~60 MB)
        'PyQt6.QtQml',
        'PyQt6.QtQuick',
        'PyQt6.QtWebEngine',
        'PyQt6.QtWebEngineWidgets',
        'PyQt6.QtWebChannel',
        'PyQt6.QtBluetooth',
        'PyQt6.QtNfc',
        'PyQt6.QtPositioning',
        'PyQt6.QtSensors',
        'PyQt6.QtSerialPort',
        'PyQt6.QtSql',
        'PyQt6.QtTest',
        'PyQt6.QtXml',
        'PyQt6.QtXmlPatterns',
        'PyQt6.QtMultimedia',      # not used — we use sounddevice
        'PyQt6.QtMultimediaWidgets',

        # mitmproxy deps — not used (replaced by custom proxy/server.py)
        'mitmproxy', 'mitmproxy_rs', 'wsproto', 'h2', 'hyperframe',
    ],
    noarchive=False,
    optimize=0,
)


# ═══════════════════════════════════════════════════════════════════════════
#  LINUX: STRIP BUNDLED AUDIO BACKENDS
# ═══════════════════════════════════════════════════════════════════════════
# The sounddevice hook collects the BUILD machine's PortAudio + audio
# backend stack (ALSA, PulseAudio, PipeWire, JACK).  Bundling those .so
# files can silence audio on other distros because the build machine's
# libraries may not match the target's audio server.  The GUI player must
# use the HOST audio libraries at runtime.

if _is_linux:
    _host_audio_prefixes = (
        'libportaudio.so',
        'libasound.so',
        'libjack.so',
        'libpulse.so',
        'libpulsecommon-',
        'libpipewire-',
    )
    a.binaries = [
        entry for entry in a.binaries
        if not any(
            Path(str(part)).name.startswith(_host_audio_prefixes)
            for part in entry[:2]
        )
    ]


# ═══════════════════════════════════════════════════════════════════════════
#  BUILD TARGETS
# ═══════════════════════════════════════════════════════════════════════════

pyz = PYZ(a.pure)

# ── Executable ───────────────────────────────────────────────────────────
#
# Icon files (place in RobloxCacheScraper/ directory):
#   Windows:  RobloxCacheScraper.ico
#   macOS:    RobloxCacheScraper.icns
#
# uac_admin is intentionally NOT set.  The app handles elevation at
# runtime (if the user declines UAC, the app continues in read-only mode
# with proxy features disabled).

_icon_path = _spec_dir / 'RobloxCacheScraper.ico' if _is_win else (
    _spec_dir / 'RobloxCacheScraper.icns' if _is_macos else None
)

exe = EXE(
    pyz,
    a.scripts,
    [] if _is_macos else a.binaries,
    [] if _is_macos else a.datas,
    [],
    name=f'RobloxCacheScraper-v{_version}',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[
        # Qt6 DLLs — UPX-compressing them rarely saves space and can trigger
        # false-positive antivirus detections.
        'Qt6Core.dll',
        'Qt6Gui.dll',
        'Qt6Widgets.dll',
        'Qt6Network.dll',
        'Qt6OpenGL.dll',
        'Qt6OpenGLWidgets.dll',
        'Qt6Svg.dll',
        'libEGL.dll',
        'libGLESv2.dll',
        'd3dcompiler_*.dll',
        # NumPy extensions — UPX can corrupt some .pyd files
        'numpy.core._multiarray_umath*',
        'numpy.core.multiarray*',
        # Cryptography Rust extensions
        'cryptography.hazmat.bindings._rust*',
    ],
    runtime_tmpdir=None,
    console=False,                      # Windowed GUI (no terminal)
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=_macos_target_arch,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(_icon_path) if _icon_path and _icon_path.exists() else None,
)


# ── macOS: COLLECT + BUNDLE → .app ──────────────────────────────────────

if _is_macos:
    coll = COLLECT(
        exe,
        a.binaries,
        a.datas,
        strip=False,
        upx=True,
        name='RobloxCacheScraper',
    )
    app = BUNDLE(
        coll,
        name='RobloxCacheScraper.app',
        icon=str(_icon_path) if _icon_path and _icon_path.exists() else None,
        bundle_identifier='com.robloxcachesraper.app',
        info_plist={
            'CFBundleDisplayName': 'RobloxCacheScraper',
            'CFBundleName': 'RobloxCacheScraper',
            'CFBundleShortVersionString': _version,
            'CFBundleVersion': _version,
            # LSUIElement is omitted (defaults to False) so the app
            # appears in the Dock — this is a windowed GUI application.
            'NSHighResolutionCapable': True,
        },
    )
