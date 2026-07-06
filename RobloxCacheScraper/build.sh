#!/usr/bin/env bash
# ===========================================================================
#  RobloxCacheScraper - Linux/macOS Build Script
#  Builds a standalone executable using PyInstaller
# ===========================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo ""
echo "============================================"
echo " RobloxCacheScraper Build Script"
echo "============================================"
echo ""

# Check Python
if ! command -v python3 &> /dev/null; then
    echo "[ERROR] Python 3 not found. Please install Python 3.12 or later."
    exit 1
fi

PYTHON="python3"

# Use uv if available, otherwise pip
if command -v uv &> /dev/null; then
    echo "[INFO] Using uv package manager..."
    PKG_MGR="uv pip install"
else
    echo "[INFO] uv not found, using pip..."
    PKG_MGR="pip install"
fi

echo "[STEP 1/4] Installing dependencies..."
$PKG_MGR -r requirements.txt
$PKG_MGR pyinstaller

echo ""
echo "[STEP 2/4] Cleaning previous builds..."
rm -rf dist build

echo ""
echo "[STEP 3/4] Building executable..."
echo ""
pyinstaller RobloxCacheScraper.spec

echo ""
echo "[STEP 4/4] Build complete!"
echo ""
echo "============================================"
echo " Output: dist/"
echo "============================================"
echo ""

if [[ "$(uname)" == "Darwin" ]]; then
    echo "macOS app bundle: dist/RobloxCacheScraper.app"
    echo ""
    echo "To run: open dist/RobloxCacheScraper.app"
elif [[ "$(uname)" == "Linux" ]]; then
    echo "Linux executable: dist/RobloxCacheScraper-v*"
    echo ""
    echo "To run: ./dist/RobloxCacheScraper-v*"
fi

echo ""
echo "Build successful!"
