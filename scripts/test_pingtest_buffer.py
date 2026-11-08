#!/usr/bin/env python3
"""Regression tests for HTTP 101 + WebSocket data arriving in one read."""
from __future__ import annotations

import asyncio
import unittest

from bot.pingtest_buffer import UpgradeBufferedReader


class FakeReader:
    def __init__(self, *chunks: bytes) -> None:
        self.chunks = list(chunks)
        self.data = bytearray()

    async def read(self, n: int = -1) -> bytes:
        if not self.data and self.chunks:
            self.data.extend(self.chunks.pop(0))
        if n < 0:
            n = len(self.data)
        result = bytes(self.data[:n])
        del self.data[:n]
        return result

    async def readexactly(self, n: int) -> bytes:
        while len(self.data) < n and self.chunks:
            self.data.extend(self.chunks.pop(0))
        if len(self.data) < n:
            raise asyncio.IncompleteReadError(bytes(self.data), n)
        result = bytes(self.data[:n])
        del self.data[:n]
        return result


class UpgradeBufferedReaderTests(unittest.IsolatedAsyncioTestCase):
    async def test_preserves_frame_coalesced_with_101(self) -> None:
        frame = b"\x82\x04pong"
        reader = UpgradeBufferedReader(
            FakeReader(b"HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\n\r\n" + frame)
        )
        headers = await reader.read(2048)
        self.assertTrue(headers.endswith(b"\r\n\r\n"))
        self.assertIn(b"101", headers.split(b"\r\n", 1)[0])
        self.assertEqual(await reader.readexactly(len(frame)), frame)

    async def test_handles_fragmented_101_headers(self) -> None:
        frame = b"\x82\x04pong"
        reader = UpgradeBufferedReader(
            FakeReader(
                b"HTTP/1.1 101 Switching",
                b" Protocols\r\nUpgrade: websocket\r\n\r\n" + frame,
            )
        )
        headers = await reader.read(2048)
        self.assertTrue(headers.endswith(b"\r\n\r\n"))
        self.assertEqual(await reader.readexactly(len(frame)), frame)

    async def test_non_101_response_is_unchanged(self) -> None:
        response = b"HTTP/1.1 403 Forbidden\r\n\r\nblocked"
        reader = UpgradeBufferedReader(FakeReader(response))
        self.assertEqual(await reader.read(2048), response)

    async def test_pending_bytes_can_be_read_in_small_chunks(self) -> None:
        frame = b"\x82\x05hello"
        reader = UpgradeBufferedReader(FakeReader(b"HTTP/1.1 101 OK\r\n\r\n" + frame))
        await reader.read(2048)
        self.assertEqual(await reader.read(2), frame[:2])
        self.assertEqual(await reader.read(20), frame[2:])


if __name__ == "__main__":
    unittest.main()
