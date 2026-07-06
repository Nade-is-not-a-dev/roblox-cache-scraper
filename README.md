# RobloxCacheScraper

A standalone Windows application for intercepting and caching Roblox game assets in real-time through a local MITM proxy.

## Features

- **MITM Proxy** - Runs a local HTTPS proxy that intercepts Roblox asset traffic
- **Automatic Cache** - Captures all assets as Roblox downloads them (images, audio, meshes, animations, texture packs, and more)
- **Live Preview** - Preview assets directly in the app:
  - Images & Decals (PNG)
  - Audio playback (OGG/MP3)
  - 3D Mesh viewer (OpenGL)
  - Animation viewer (R15/R6 rigs)
  - TexturePack viewer
- **Filter by Type** - Filter cached assets by category (Images, Audio, Meshes, Animations, etc.)
- **Search** - Search by asset ID, type, or hash
- **Export** - Export individual assets or batch export

## Requirements

- Windows 10+ (also works on macOS/Linux)
- Administrator privileges (for proxy port 443 and hosts file)
- Roblox installed

## Installation

```bash
# Install dependencies
pip install -r requirements.txt

# Run the application
python main.py
```

## Usage

1. **Start the Proxy** - Click "Start Proxy" to begin the MITM proxy on port 443
2. **Configure Hosts** - Add hosts file entries (requires admin):
   - `127.0.0.1 assetdelivery.roblox.com`
   - `127.0.0.1 fts.rbxcdn.com`
   - `127.0.0.1 contentdelivery.roblox.com`
3. **Install CA Certificate** - Install `proxy_ca/ca.crt` into Roblox's SSL trust store
4. **Enable Scraper** - Click "Enable Scraper" to start capturing assets
5. **Play Roblox** - Launch Roblox and play a game; assets will appear automatically
6. **Browse & Preview** - Click on any asset to see a preview

## Architecture

```
RobloxCacheScraper/
├── main.py              # Entry point
├── proxy/
│   ├── server.py        # MITM TLS proxy server (asyncio)
│   ├── upstream.py      # Upstream connection management
│   └── certs.py         # CA and leaf certificate generation
├── scraper/
│   ├── cache_scraper.py # Asset interception and caching logic
│   └── cache_manager.py # Asset storage and indexing
├── gui/
│   ├── main_window.py   # Main window with split table/preview
│   ├── cache_viewer.py  # Asset table with search and filter
│   ├── audio_player.py  # Audio playback widget
│   ├── mesh_viewer.py   # 3D OpenGL mesh viewer
│   ├── animation_viewer.py  # R15/R6 animation player
│   └── texturepack_viewer.py  # Texture pack viewer
├── converters/
│   ├── ktx_to_png.py    # KTX texture to PNG conversion
│   └── mesh_processing.py  # Roblox mesh to OBJ conversion
└── utils/
    ├── paths.py         # Application path constants
    ├── logging.py       # Log buffer
    └── formats.py       # Formatting helpers
```

## License

This project is provided as-is for educational and personal use.
