"""DIRTY ROOM: find textures that display lists outside the archive load (code overlays, main data).

    python -m games.yoshistory.texscan <retail rom> [--sheet out.png]

Walks every F3DEX G_SETTIMG whose address is a RAM address inside the main segment or an overlay, and reads the
format / size from the following load + tile commands. Returns {rom offset: dict(fmt, siz, w, h, tlut)}.
"""
import collections
import json
import os
import struct
import sys

import numpy as np

MAIN_ROM, MAIN_VRAM, MAIN_END = 0x1070, 0x80000470, 0xB58B0
OVL_START, OVL_END = 0xB47A10, 0xEBDA70


def overlays(rom):
    """[(rom start, rom end, vram start, vram end)] from the actor / scene records."""
    w = np.frombuffer(rom[:len(rom) & ~3], dtype=">u4").astype(np.int64)
    a, b, c, d = w[:-3], w[1:-2], w[2:-1], w[3:]
    ok = (a >= OVL_START) & (a < OVL_END) & (b > a) & (b <= OVL_END) & (c >= 0x80200000) & (c < 0x80800000) & \
         ((d - c) >= (b - a)) & ((d - c) < (b - a) + 0x100000)
    return sorted({(int(a[k]), int(b[k]), int(c[k]), int(d[k])) for k in np.nonzero(ok)[0].tolist()})


def scan(rom):
    ovl = overlays(rom)
    regions = [(MAIN_ROM, MAIN_END, MAIN_VRAM)] + [(r0, r1, v0) for r0, r1, v0, v1 in ovl]
    tex, tluts = {}, {}
    for r0, r1, v0 in regions:
        w = np.frombuffer(rom[r0:r0 + ((r1 - r0) & ~7)], dtype=">u4").reshape(-1, 2)
        ops = (w[:, 0] >> 24)
        fd = np.nonzero((ops == 0xFD) & ((w[:, 0] & 0xFFFF) == 0) & (w[:, 1] >= v0) & (w[:, 1] < v0 + (r1 - r0)))[0]
        last_tlut = None
        for k in fd.tolist():
            x, addr = int(w[k, 0]), int(w[k, 1])
            fmt, siz = (x >> 21) & 7, (x >> 19) & 3
            ro = addr - v0 + r0
            n_tex = wd = ht = None
            line = None
            is_tlut = False
            for j in range(k + 1, min(k + 12, len(w))):
                y0, y1 = int(w[j, 0]), int(w[j, 1])
                op = y0 >> 24
                if op == 0xFD:
                    break
                if op == 0xF0:                                   # LOADTLUT
                    is_tlut = True
                    n_tex = ((y1 >> 14) & 0x3FF) + 1
                    break
                if op == 0xF3:                                   # LOADBLOCK
                    n_tex = ((y1 >> 12) & 0xFFF) + 1
                if op == 0xF5 and ((y1 >> 24) & 7) != 7:         # render tile
                    line = (y0 >> 9) & 0x1FF
                    rfmt, rsiz = (y0 >> 21) & 7, (y0 >> 19) & 3
                if op == 0xF2:
                    wd, ht = ((y1 >> 12) & 0xFFF) // 4 + 1, (y1 & 0xFFF) // 4 + 1
                    break
            if is_tlut:
                tluts[ro] = max(tluts.get(ro, 0), n_tex)
                last_tlut = ro
                continue
            if wd is None or n_tex is None:
                continue
            try:
                fmt, siz = rfmt, rsiz
            except NameError:
                pass
            bits = 4 << siz
            # LoadBlock of a 4-bit texture is issued as 16-bit texels
            size = wd * ht * bits // 8
            if size <= 0 or size > 0x4000 or ro + size > r1:
                continue
            e = dict(fmt=fmt, siz=siz, w=wd, h=ht, size=size, tlut=last_tlut if fmt == 2 else None)
            if ro not in tex or tex[ro]["size"] < size:
                tex[ro] = e
    return tex, tluts, ovl


def decode(rom, o, e, tluts):
    from cleanroom.gfx import texfmt
    pal = None
    if e["fmt"] == 2 and e["tlut"] is not None:
        n = tluts[e["tlut"]]
        v = np.frombuffer(rom[e["tlut"]:e["tlut"] + 2 * n], dtype=">u2").astype(np.uint32)
        pal = np.stack([((v >> 11) & 31) * 255 // 31, ((v >> 6) & 31) * 255 // 31, ((v >> 1) & 31) * 255 // 31, (v & 1) * 255], 1).astype(np.uint8)
        pal = np.concatenate([pal, np.zeros((256, 4), np.uint8)])[:256]
    return texfmt.decode(rom[o:o + e["size"]], e["w"], e["h"], e["fmt"], e["siz"], pal).reshape(e["h"], e["w"], 4)


def main(argv):
    rom = open(argv[1], "rb").read()
    tex, tluts, ovl = scan(rom)
    c = collections.Counter((e["fmt"], e["siz"]) for e in tex.values())
    print(f"texscan: {len(tex)} textures ({sum(e['size'] for e in tex.values())} B), {len(tluts)} palettes, {len(ovl)} overlays")
    print("  fmt/siz:", dict(c), " in main:", sum(o < MAIN_END for o in tex))
    if "--sheet" in argv:
        from PIL import Image, ImageDraw
        path = argv[argv.index("--sheet") + 1]
        W = 1900
        x = y = rowh = 0
        sh = Image.new("RGB", (W, 5000), (40, 40, 70))
        dr = ImageDraw.Draw(sh)
        for o in sorted(tex):
            e = tex[o]
            try:
                im = Image.fromarray(decode(rom, o, e, tluts), "RGBA")
            except Exception as ex:
                continue
            sc = 2 if max(e["w"], e["h"]) <= 48 else 1
            im = im.resize((im.width * sc, im.height * sc), Image.NEAREST)
            if x + max(im.width, 40) > W:
                x, y, rowh = 0, y + rowh + 12, 0
            sh.paste(im, (x, y + 10), im)
            dr.text((x, y), f"{o:x}", fill=(255, 255, 0))
            x += max(im.width, 40) + 4
            rowh = max(rowh, im.height)
        sh.crop((0, 0, W, y + rowh + 14)).save(path)
        print("sheet ->", path)


if __name__ == "__main__":
    main(sys.argv)
