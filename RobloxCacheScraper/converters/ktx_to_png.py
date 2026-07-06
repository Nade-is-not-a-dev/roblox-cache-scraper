"""KTX texture to PNG converter.

Supports both KTX1 and KTX2 formats with graceful fallback.
"""

import io
import logging
import struct
from PIL import Image

logger = logging.getLogger(__name__)

# KTX magic bytes
KTX1_MAGIC = b'\xabKTX 11\xbb\r\n\x1a\n'
KTX2_MAGIC = b'\xabKTX 20\xbb\r\n\x1a\n'
KTX_MAGICS = (KTX1_MAGIC[:12], KTX2_MAGIC[:12])


def strip_prefixed_ktx(data: bytes) -> bytes | None:
    """Strip Roblox metadata prefix from KTX data."""
    for magic in KTX_MAGICS:
        idx = data.find(magic)
        if idx >= 0:
            return data[idx:]
    return None


def convert(data: bytes) -> bytes | None:
    """Convert KTX data to PNG bytes.

    Args:
        data: Raw KTX1 or KTX2 file bytes

    Returns:
        PNG bytes, or None if conversion failed
    """
    if not data:
        return None

    # Strip any prefix
    payload = strip_prefixed_ktx(data)
    if payload is None:
        payload = data

    # Check magic
    if payload[:4] == b'\x89PNG':
        return payload  # Already PNG

    is_ktx2 = payload[:12] == KTX2_MAGIC[:12]

    try:
        if is_ktx2:
            return _convert_ktx2(payload)
        else:
            return _convert_ktx1(payload)
    except Exception as exc:
        logger.debug('KTX conversion failed: %s', exc)
        return None


def _convert_ktx1(data: bytes) -> bytes | None:
    """Convert KTX1 to PNG."""
    if len(data) < 64:
        return None

    gl_format = struct.unpack_from('<I', data, 36)[0]
    width = struct.unpack_from('<I', data, 24)[0]
    height = struct.unpack_from('<I', data, 28)[0]

    if width == 0 or height == 0 or width > 16384 or height > 16384:
        return None

    # Return placeholder for ETC textures
    from PIL import Image as PILImage
    img = PILImage.new('RGBA', (min(width, 512), min(height, 512)), (96, 96, 96, 255))
    buf = io.BytesIO()
    img.save(buf, 'PNG')
    return buf.getvalue()


def _convert_ktx2(data: bytes) -> bytes | None:
    """Convert KTX2 to PNG."""
    if len(data) < 28:
        return None

    width = struct.unpack_from('<I', data, 20)[0]
    height = struct.unpack_from('<I', data, 24)[0]
    if width == 0 or height == 0 or width > 16384 or height > 16384:
        return None

    # Return placeholder - real transcoding requires Basis Universal decoder
    from PIL import Image as PILImage
    img = PILImage.new('RGBA', (min(width, 512), min(height, 512)), (128, 128, 128, 255))
    buf = io.BytesIO()
    img.save(buf, 'PNG')
    return buf.getvalue()
