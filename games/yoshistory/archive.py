"""Dirty-room reader for the Yoshi's Story asset segment (segment 3, ROM 0x526EC0..).

The descriptor area (0x526EC0..0x561540) holds resource triples (u32 size, u32 stored size, u32 seg-3 pointer);
stored size < size means a CMPR/SMSR00 file. Triples sit in runs: images, then their palettes, then small
tables (animation / tile maps), sometimes followed by more images. A 12-byte dims block (6 x u16) precedes most runs.
"""
import struct

import numpy as np

from . import smsr

SEG3 = 0x526EC0
DESC_END = 0x561540
DATA_END = 0xEBDA70


def triples(rom):
    """{descriptor offset: (rom offset, size, compressed)} for every valid triple in the ROM."""
    w = np.frombuffer(rom[:len(rom) & ~3], dtype=">u4").astype(np.int64)
    ptr, size, comp = w[2:], w[:-2], w[1:-1]
    ok = (ptr >= 0x03000000) & (ptr < 0x03000000 + DATA_END - SEG3) & (size > 0) & (size < 0x100000) & (comp > 0) & (comp <= size + 0x400)
    out = {}
    for i in np.nonzero(ok)[0].tolist():
        ro = int(ptr[i]) - 0x03000000 + SEG3
        sz, c = int(size[i]), int(comp[i])
        cm = rom[ro:ro + 4] == b"CMPR"
        if cm:
            if struct.unpack_from(">II", rom, ro + 4) != (c, sz):
                continue
        elif c != sz:
            continue
        out[i * 4] = (ro, sz, cm)
    return out


def runs(trip):
    out, cur = [], []
    for u in sorted(trip):
        if cur and u == cur[-1] + 12:
            cur.append(u)
        else:
            if cur:
                out.append(cur)
            cur = [u]
    if cur:
        out.append(cur)
    return out


def read(rom, ent):
    ro, sz, cm = ent
    return smsr.decode(rom, ro)[0] if cm else rom[ro:ro + sz]


def guess_width(data, cands=None):
    """Row width of an 8-bit image by vertical similarity; returns (width, score). Lower score = better."""
    a = np.frombuffer(data, dtype=np.uint8).astype(np.int16)
    n = len(a)
    if cands is None:
        cands = [w for w in (8, 12, 16, 20, 24, 28, 32, 40, 48, 56, 64, 72, 80, 96, 112, 128, 160, 192, 256, 320)
                 if n % w == 0 and n // w >= 2]
    best = (0, 9e9)
    for w in cands:
        if n % w or n // w < 2:
            continue
        m = a.reshape(-1, w)
        s = float((m[1:] != m[:-1]).mean()) + 0.002 * (w ** 0.5) * 0  # exact-index mismatch rate between rows
        if s < best[1] - 1e-9:
            best = (w, s)
    return best


def pal_rgba(pal):
    """RGBA16 palette bytes -> (n, 4) uint8."""
    v = np.frombuffer(pal[:len(pal) & ~1], dtype=">u2").astype(np.uint32)
    r = (v >> 11) & 31
    g = (v >> 6) & 31
    b = (v >> 1) & 31
    a = (v & 1) * 255
    return np.stack([r * 255 // 31, g * 255 // 31, b * 255 // 31, a], 1).astype(np.uint8)
