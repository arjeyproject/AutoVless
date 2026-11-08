"""Preserve WebSocket bytes coalesced with the HTTP upgrade response.

Some servers return ``101 Switching Protocols`` and the first WebSocket frame
in one TCP read. The ping tester parses the HTTP status first, so bytes after
its header terminator must be replayed to the WebSocket frame parser.
"""
from __future__ import annotations

import re
from typing import Any


_STATUS_LINE = re.compile(rb"^HTTP/\d(?:\.\d)?\s+(\d{3})(?:\s|$)", re.IGNORECASE)


class UpgradeBufferedReader:
    """Reader adapter that returns complete 101 headers and buffers the tail."""

    def __init__(self, reader: Any) -> None:
        self._reader = reader
        self._pending = bytearray()
        self._checked_first_read = False

    async def read(self, n: int = -1) -> bytes:
        if self._pending:
            return self._take_pending(n)
        if self._checked_first_read:
            return await self._reader.read(n)

        self._checked_first_read = True
        data = bytearray(await self._reader.read(n))
        if not data.startswith(b"HTTP/"):
            return bytes(data)

        # A stream may split the status line or the header terminator across
        # reads. Read through the complete header before exposing a 101 to the
        # caller, while preserving any frame bytes that followed it.
        while b"\r\n\r\n" not in data:
            first_line = bytes(data).split(b"\r\n", 1)[0]
            match = _STATUS_LINE.match(first_line)
            if match and match.group(1) != b"101":
                return bytes(data)
            chunk = await self._reader.read(n)
            if not chunk:
                return bytes(data)
            data.extend(chunk)

        marker = data.find(b"\r\n\r\n")
        end = marker + 4
        first_line = bytes(data).split(b"\r\n", 1)[0]
        if _STATUS_LINE.match(first_line) and _STATUS_LINE.match(first_line).group(1) == b"101":
            self._pending.extend(data[end:])
            return bytes(data[:end])
        return bytes(data)

    async def readexactly(self, n: int) -> bytes:
        if n < 0:
            raise ValueError("readexactly size can not be negative")
        if len(self._pending) >= n:
            return self._take_pending(n)
        prefix = bytes(self._pending)
        self._pending.clear()
        if not prefix:
            return await self._reader.readexactly(n)
        return prefix + await self._reader.readexactly(n - len(prefix))

    def _take_pending(self, n: int) -> bytes:
        if n < 0 or n >= len(self._pending):
            data = bytes(self._pending)
            self._pending.clear()
            return data
        data = bytes(self._pending[:n])
        del self._pending[:n]
        return data

    def __getattr__(self, name: str) -> Any:
        return getattr(self._reader, name)


def install(module: Any) -> None:
    """Wrap pingtest.dial once, keeping the public pingtest API unchanged."""
    if getattr(module, "_upgrade_buffer_installed", False):
        return
    original_dial = module.dial

    async def buffered_dial(*args: Any, **kwargs: Any):
        reader, writer = await original_dial(*args, **kwargs)
        return UpgradeBufferedReader(reader), writer

    module.dial = buffered_dial
    module._upgrade_buffer_installed = True
