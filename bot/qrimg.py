"""QR rendering shared by every screen that shows one.

One helper instead of four copies of "qrcode.make -> BytesIO -> PNG", so the
box size, border and filename stay consistent everywhere a user scans a code -
the subscription, a single protocol link, the WARP link.

The quiet zone is 4 by spec; a tighter border scans on most phone cameras and
keeps the photo small enough for Telegram to render it crisply in-line.
"""

from __future__ import annotations

import io

import qrcode
from aiogram.types import BufferedInputFile

BOX_SIZE = 7
BORDER = 3


def png_bytes(text: str, box_size: int = BOX_SIZE, border: int = BORDER) -> bytes:
    """Render one QR code as PNG bytes. Raises on empty input like qrcode does."""
    image = qrcode.make(text, box_size=box_size, border=border)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def file_photo(text: str, filename: str = "autovless-qr.png") -> BufferedInputFile:
    return BufferedInputFile(png_bytes(text), filename=filename)
