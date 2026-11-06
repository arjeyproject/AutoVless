"""BLAKE3 hashing for Cloudflare Pages direct uploads.

The Pages asset upload API keys every file by ``blake3(base64(contents) +
extension)`` - the exact algorithm wrangler implements in
``@cloudflare/deploy-helpers``. The ``blake3`` PyPI wheel covers the common
platforms, but a bot box without a wheel for its interpreter would fail at
import time and every build with it, so this module carries a complete
pure-Python implementation of the same function and uses it whenever the
native package is unavailable. The pure version only has to be correct, not
fast: a worker bundle is roughly 100 KB, which hashes in well under a second.
"""

from __future__ import annotations

import base64
import struct

CHUNK_LEN = 1024
BLOCK_LEN = 64

CHUNK_START = 1 << 0
CHUNK_END = 1 << 1
PARENT = 1 << 2
ROOT = 1 << 3

IV = (
    0x6A09E667, 0xBB67AE85, 0x3C6EF372, 0xA54FF53A,
    0x510E527F, 0x9B05688C, 0x1F83D9AB, 0x5BE0CD19,
)
MSG_PERMUTATION = (2, 6, 3, 10, 7, 0, 4, 13, 1, 11, 12, 5, 9, 14, 15, 8)
MASK = 0xFFFFFFFF


def _rotr(value: int, bits: int) -> int:
    return ((value >> bits) | (value << (32 - bits))) & MASK


def _mix(state: list, a: int, b: int, c: int, d: int, mx: int, my: int) -> None:
    state[a] = (state[a] + state[b] + mx) & MASK
    state[d] = _rotr(state[d] ^ state[a], 16)
    state[c] = (state[c] + state[d]) & MASK
    state[b] = _rotr(state[b] ^ state[c], 12)
    state[a] = (state[a] + state[b] + my) & MASK
    state[d] = _rotr(state[d] ^ state[a], 8)
    state[c] = (state[c] + state[d]) & MASK
    state[b] = _rotr(state[b] ^ state[c], 7)


def _round(state: list, words: list) -> None:
    _mix(state, 0, 4, 8, 12, words[0], words[1])
    _mix(state, 1, 5, 9, 13, words[2], words[3])
    _mix(state, 2, 6, 10, 14, words[4], words[5])
    _mix(state, 3, 7, 11, 15, words[6], words[7])
    _mix(state, 0, 5, 10, 15, words[8], words[9])
    _mix(state, 1, 6, 11, 12, words[10], words[11])
    _mix(state, 2, 7, 8, 13, words[12], words[13])
    _mix(state, 3, 4, 9, 14, words[14], words[15])


def _compress(
    input_cv: list,
    block_words: list,
    counter: int,
    block_len: int,
    flags: int,
) -> list:
    state = list(input_cv) + list(IV) + [
        counter & MASK,
        (counter >> 32) & MASK,
        block_len,
        flags,
    ]
    words = list(block_words)
    for _ in range(7):
        _round(state, words)
        words = [words[MSG_PERMUTATION[i]] for i in range(16)]
    for i in range(8):
        state[i] ^= state[i + 8]
        state[i + 8] ^= input_cv[i]
    return state


def _words(block: bytes) -> list:
    padded = block + b"\x00" * (BLOCK_LEN - len(block))
    return list(struct.unpack("<16I", padded))


def _chunk_output(chunk: bytes, counter: int) -> tuple:
    """The final Output of one 1024-byte chunk: (cv, words, counter, len, flags)."""
    cv = list(IV)
    blocks = [chunk[i:i + BLOCK_LEN] for i in range(0, len(chunk), BLOCK_LEN)] or [b""]
    for index, block in enumerate(blocks[:-1]):
        flags = CHUNK_START if index == 0 else 0
        cv = _compress(cv, _words(block), counter, len(block), flags)[:8]
    last = blocks[-1]
    flags = (CHUNK_START if len(blocks) == 1 else 0) | CHUNK_END
    return (cv, _words(last), counter, len(last), flags)


def _pure_digest(data: bytes, out_len: int = 32) -> bytes:
    """BLAKE3 of ``data``, first ``out_len`` bytes (up to 32)."""
    chunks = [data[i:i + CHUNK_LEN] for i in range(0, len(data), CHUNK_LEN)] or [b""]
    stack: list[list[int]] = []
    state: tuple = (list(IV), _words(b""), 0, 0, CHUNK_START | CHUNK_END)

    for index, chunk in enumerate(chunks):
        output = _chunk_output(chunk, index)
        if index == len(chunks) - 1:
            state = output
            break
        cv = _compress(*output)[:8]
        total = index + 1
        while total & 1 == 0 and stack:
            cv = _compress(list(IV), stack.pop() + cv, 0, BLOCK_LEN, PARENT)[:8]
            total >>= 1
        stack.append(cv)

    icv, block_words, counter, block_len, flags = state
    for cv in reversed(stack):
        right = _compress(icv, block_words, counter, block_len, flags)[:8]
        icv, block_words, counter, block_len, flags = list(IV), cv + right, 0, BLOCK_LEN, PARENT
    words = _compress(icv, block_words, counter, block_len, flags | ROOT)
    return struct.pack("<16I", *words)[:out_len]


def hexdigest(data: bytes, out_len: int = 32) -> str:
    return digest(data, out_len).hex()


def file_hash(path: str, contents: bytes) -> str:
    """The key Pages expects for one uploaded file.

    Mirrors wrangler's ``hashFile``: hash the base64 text of the file contents
    plus the file extension (no dot), and keep the first 32 hex characters.
    """
    base64_contents = base64.b64encode(contents).decode("ascii")
    tail = path.rsplit("/", 1)[-1]
    extension = tail.rsplit(".", 1)[-1] if "." in tail else ""
    return hexdigest((base64_contents + extension).encode("utf-8"))[:32]


# The native wheel wins when present; the reference implementation above is
# verified against it in scripts/verify_pages.py.
try:
    from blake3 import blake3 as _native_blake3  # type: ignore

    def _fast_digest(data: bytes, out_len: int = 32) -> bytes:
        return _native_blake3(data).digest(length=out_len)
except ImportError:
    _fast_digest = None

digest = _fast_digest if _fast_digest is not None else _pure_digest

__all__ = ["digest", "hexdigest", "file_hash"]
