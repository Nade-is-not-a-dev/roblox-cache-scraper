@echo off
REM ===========================================================================
REM  RobloxCacheScraper - Windows Build Script
REM  Builds a standalone .exe using PyInstaller
REM ===========================================================================
TITLE RobloxCacheScraper Build

echo.
echo ============================================
echo  RobloxCacheScraper Windows Build Script
echo ============================================
echo.

REM Check Python version
python --version >nul 2>&1
IF %ERRORLEVEL% NEQ 0 (
    echo [ERROR] Python not found. Please install Python 3.12 or later.
    pause
    exit /b 1
)

REM Check for uv (recommended) or pip
WHERE uv >nul 2>&1
IF %ERRORLEVEL% EQU 0 (
    echo [INFO] Using uv package manager...
    echo.
    echo [STEP 1/4] Installing dependencies...
    call uv pip install -r requirements.txt pyinstaller
    IF %ERRORLEVEL% NEQ 0 (
        echo [ERROR] Failed to install dependencies.
        pause
        exit /b 1
    )
) ELSE (
    echo [INFO] uv not found, using pip...
    echo.
    echo [STEP 1/4] Installing dependencies...
    pip install -r requirements.txt
    IF %ERRORLEVEL% NEQ 0 (
        echo [ERROR] Failed to install dependencies.
        pause
        exit /b 1
    )
    echo.
    echo [INFO] Installing PyInstaller...
    pip install pyinstaller
    IF %ERRORLEVEL% NEQ 0 (
        echo [ERROR] Failed to install PyInstaller.
        pause
        exit /b 1
    )
)

echo.
echo [STEP 2/4] Cleaning previous build artifacts...
IF EXIST dist rmdir /s /q dist
IF EXIST build rmdir /s /q build

echo.
echo [STEP 3/4] Building executable...
echo NOTE: Antivirus may temporarily quarantine the build process.
echo.
pyinstaller RobloxCacheScraper.spec
IF %ERRORLEVEL% NEQ 0 (
    echo.
    echo [ERROR] PyInstaller build failed.
    echo Possible causes:
    echo   - Missing dependencies (try: pip install -r requirements.txt)
    echo   - Antivirus blocking PyInstaller (temporarily disable real-time protection)
    echo   - Python version mismatch (need 3.12+)
    pause
    exit /b 1
)

echo.
echo [STEP 4/4] Build complete!
echo.
echo ============================================
echo  Output: dist\RobloxCacheScraper-v*.exe
echo ============================================
echo.

REM Open the dist folder
START "" "dist"

echo.
echo Build successful!
echo To distribute:
echo   1. Copy the .exe from the dist folder
echo   2. The .exe is standalone - no Python installation required
echo   3. Run as Administrator for proxy features (port 443)
echo.
pause
