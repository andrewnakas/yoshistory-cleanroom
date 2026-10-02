"""DIRTY ROOM: classify every archive target (image / palette / data) from the descriptor runs.

    python -m games.yoshistory.classify <retail rom> [--sheet out.png kind]

Result (also used by extract_spec): {rom offset: dict(kind, size, cm, w, fh, bpp, pals=[offsets], runs=[...])}
"""
import re
import struct
import sys

import numpy as np

from . import archive as A
from . import smsr


def is_palette(rom, ent):
    ro, sz, cm = ent
    # one palette (<= 256 colours) or a block of 256-colour variants
    return (not cm) and sz >= 16 and sz % 2 == 0 and (sz <= 0x200 or (sz % 0x200 == 0 and sz <= 0x2000))


YOSHI_PALS = [0x96a390 + 0x200 * k for k in range(8)]
FRAME_TABLE = 0xB0F7C0          # 0x80-byte records: DL pointer, part count, (id << 24 | size, part pointer) ...
PARTS_START, PARTS_END = 0x96B390, 0x9E6BC0


# title overlay (ROM 0xD14550, data at +0x460): three 328 x 384 CI8 pages sharing one palette
TITLE_PIX, TITLE_PAL = 0xD14550 + 0x460 + 0x10, 0xD14550 + 0x460 + 0x5C418


def yoshi_frames(rom):
    o = FRAME_TABLE
    while True:
        dl = struct.unpack_from(">I", rom, o)[0]
        if not 0x03400000 <= dl < 0x03700000:
            return
        n = rom[o + 4]
        yield dl - 0x03000000 + A.SEG3, [struct.unpack_from(">II", rom, o + 8 + 8 * k) for k in range(n)]
        o += 0x80


def dl_tiles(rom, a):
    """(w, h) of every texture a frame's display list loads, in order (palette loads skipped)."""
    w = np.frombuffer(rom[a:a + 0x440], dtype=">u4").reshape(-1, 2)
    out, cur = [], None
    for x, y in w.tolist():
        op = x >> 24
        if op == 0xFD:
            cur = (x >> 16) & 0xFF
        elif op == 0xF2 and cur is not None and cur != 0x10:
            out.append((((y >> 12) & 0xFFF) // 4 + 1, (y & 0xFFF) // 4 + 1))
            cur = None
        elif op == 0xB8:
            break
    return out


def yoshi_parts(rom):
    """{rom offset: (size, w, h, guessed)} covering PARTS_START..PARTS_END completely."""
    parts = {}
    for dl, ps in yoshi_frames(rom):
        for (hdr, ptr), (w, h) in zip(ps, dl_tiles(rom, dl)):
            if w * h == hdr & 0xFFFF:
                parts.setdefault(ptr - 0x03000000 + A.SEG3, (hdr & 0xFFFF, w, h, False))
    pos = PARTS_START
    for o in sorted(parts) + [PARTS_END]:
        if o > pos:                                   # parts no frame uses: one image per gap, width guessed
            data = rom[pos:o]
            if any(data):
                w, _ = A.guess_width(data, [w for w in (32, 24, 16, 48) if len(data) % w == 0])
                w = w or 16
                parts[pos] = (len(data) // w * w, w, min(32, len(data) // w), True)
        if o < PARTS_END:
            pos = o + parts[o][0]
    return parts


def classify(rom):
    trip = A.triples(rom)
    out = {}

    def rec(ent):
        return out.setdefault(ent[0], dict(kind="data", size=ent[1], cm=ent[2], pals=[], runs=[], w=0, fh=0, bpp=8))

    for r in A.runs(trip):
        if r[0] < A.SEG3 or r[0] >= A.DESC_END:
            continue
        ents = [trip[u] for u in r]
        s = "".join("C" if e[2] else "R" for e in ents)
        n = len(re.match(r"C*", s).group(0))
        m = len(re.match(r"R*", s[n:]).group(0))
        d = struct.unpack(">6H", rom[r[0] - 12:r[0]])
        dims_ok = all(0 < x <= 8192 for x in d)
        for k, e in enumerate(ents):
            t = rec(e)
            t["runs"].append(r[0])
            if k < n or (n == 0 and k == 0 and e[1] >= 64 and dims_ok):
                # leading image
                sz = e[1]
                w = fh = 0
                bpp = 8
                if dims_ok:
                    if d[4] * d[5] == sz:
                        w, fh = d[4], d[1] if d[5] % max(d[1], 1) == 0 else d[5]
                    elif d[4] * d[5] == sz * 2:
                        w, fh, bpp = d[4], d[1] if d[5] % max(d[1], 1) == 0 else d[5], 4
                    elif d[2] == 16 and d[3] == 16 and d[0] >= 64 and sz % 256 == 0:
                        w, fh = 16, 16                      # tile set, tiles stored one after another
                    elif n == 1 and d[0] * d[1] == sz:
                        w, fh = d[0], d[1]
                pal = ents[n + k] if (k < n and n + k < n + m and is_palette(rom, ents[n + k])) else None
                if t["kind"] != "image" or (w and not t["w"]):
                    t.update(kind="image", w=w or t["w"], fh=fh or t["fh"], bpp=bpp)
                if pal is not None:
                    step = 0x20 if bpp == 4 and pal[1] % 0x20 == 0 else 0x200   # 4-bit images: 16-colour variants
                    for q in range(pal[0], pal[0] + pal[1], step):           # every variant
                        p = rec((q, min(step, pal[1]), False))
                        p["kind"] = "palette"
                        p["size"] = min(step, pal[1])
                        if pal[0] not in p["runs"]:
                            p["runs"].append(r[0])
                        if q not in t["pals"]:
                            t["pals"].append(q)
    # runs with fewer palettes than images: which image uses which palette is not stated, so every image of the
    # run is built to look right under every palette of the run
    for r in A.runs(trip):
        if r[0] < A.SEG3 or r[0] >= A.DESC_END:
            continue
        ents = [trip[u] for u in r]
        st = "".join("C" if e[2] else "R" for e in ents)
        n = len(re.match(r"C*", st).group(0))
        pl = []
        for e in ents[n:]:
            if not is_palette(rom, e):
                break
            pl += list(range(e[0], e[0] + e[1], 0x200))
        imgs = [out[e[0]] for e in ents[:n] if out[e[0]]["kind"] == "image"]
        if n >= 2 and pl and any(not t["pals"] for t in imgs) and all(out.get(q, {}).get("kind") == "palette" for q in pl):
            for t in imgs:
                t["pals"] += [q for q in pl if q not in t["pals"]]
    # unreferenced CMPR files
    for o in smsr.find_all(rom):
        if o not in out:
            sz = struct.unpack_from(">I", rom, o + 8)[0]
            out[o] = dict(kind="unref", size=sz, cm=True, pals=[], runs=[], w=0, fh=0, bpp=8)
    # Yoshi: body-part textures (raw CI8) drawn with the palette of the current Yoshi colour
    for p in YOSHI_PALS:
        out.setdefault(p, dict(kind="palette", size=0x200, cm=False, pals=[], runs=[], w=0, fh=0, bpp=8))["kind"] = "palette"
    for t in out.values():
        if t["kind"] == "image" and any(p in YOSHI_PALS for p in t["pals"]):
            t["pals"] = [p for p in t["pals"] if p not in YOSHI_PALS] + YOSHI_PALS
    for o, (sz, w, h, guess) in yoshi_parts(rom).items():
        out[o] = dict(kind="image", size=sz, cm=False, pals=list(YOSHI_PALS), runs=[], w=w, fh=h, bpp=8)
        if guess:
            out[o]["guess"] = True
    # textures inside code overlays (static display lists) and the title pages
    from . import texscan
    tex, tluts, _ = texscan.scan(rom)
    for p, n in tluts.items():
        out[p] = dict(kind="palette", size=2 * n, cm=False, pals=[], runs=[], w=0, fh=0, bpp=8)
    for o, e in tex.items():
        out[o] = dict(kind="image", size=e["size"], cm=False, pals=[e["tlut"]] if e["fmt"] == 2 else [], runs=[],
                      w=e["w"], fh=e["h"], bpp=4 << e["siz"])
        if e["fmt"] == 4:
            out[o]["ia"] = True
    out[TITLE_PAL] = dict(kind="palette", size=0x200, cm=False, pals=[], runs=[], w=0, fh=0, bpp=8)
    out[TITLE_PIX] = dict(kind="image", size=328 * 384 * 3, cm=False, pals=[TITLE_PAL], runs=[], w=328, fh=384, bpp=8)
    # width for images the dims did not settle
    for o, t in out.items():
        if t["kind"] == "image" and not t["w"]:
            data = A.read(rom, (o, t["size"], t["cm"]))
            w, _ = A.guess_width(data)
            t["w"] = w
            t["fh"] = w if w and (len(data) // w) % w == 0 else (len(data) // w if w else 0)
            t["guess"] = True
    return out


def sheet(rom, cl, kind, path, limit=400):
    from PIL import Image, ImageDraw
    tiles = []
    for o in sorted(cl):
        t = cl[o]
        if kind == "nopal":
            if not (t["kind"] == "image" and not t["pals"]):
                continue
        elif kind == "guess":
            if not (t["kind"] == "image" and t.get("guess")):
                continue
        elif kind == "data":
            if not (t["kind"] in ("data", "unref") and t["cm"]):
                continue
        elif kind == "rawdata":
            if not (t["kind"] == "data" and not t["cm"] and t["size"] >= 64):
                continue
        data = A.read(rom, (o, t["size"], t["cm"]))
        w = t["w"] or A.guess_width(data)[0] or 16
        if t["bpp"] == 4:
            a = np.frombuffer(data, np.uint8)
            data = np.stack([(a >> 4) * 17, (a & 15) * 17], 1).astype(np.uint8).tobytes()
        idx = np.frombuffer(data, np.uint8)
        idx = idx[:len(idx) // w * w].reshape(-1, w)[:160]
        if not idx.size:
            continue
        if t["pals"]:
            pal = np.concatenate([A.pal_rgba(A.read(rom, (t["pals"][0], cl[t["pals"][0]]["size"], False))), np.zeros((256, 4), np.uint8)])[:256]
            im = Image.fromarray(pal[idx], "RGBA")
            bg = Image.new("RGBA", im.size, (60, 60, 90, 255))
            bg.alpha_composite(im)
            im = bg.convert("RGB")
        else:
            im = Image.fromarray(idx, "L").convert("RGB")
        sc = 2 if w <= 64 else 1
        tiles.append((o, im.resize((im.width * sc, im.height * sc), Image.NEAREST).crop((0, 0, min(im.width * sc, 256), min(im.height * sc, 200)))))
        if len(tiles) >= limit:
            break
    W = 1900
    x = y = rowh = 0
    sh = Image.new("RGB", (W, 6000), (20, 20, 20))
    dr = ImageDraw.Draw(sh)
    for o, t in tiles:
        if x + max(t.width, 44) > W:
            x, y, rowh = 0, y + rowh + 14, 0
        sh.paste(t, (x, y + 11))
        dr.text((x, y), f"{o:x}", fill=(255, 255, 0))
        x += max(t.width, 44) + 4
        rowh = max(rowh, t.height)
    sh.crop((0, 0, W, min(6000, y + rowh + 16))).save(path)
    print(f"sheet {kind}: {len(tiles)} -> {path}")


def main(argv):
    rom = open(argv[1], "rb").read()
    cl = classify(rom)
    import collections
    c = collections.Counter()
    b = collections.Counter()
    for t in cl.values():
        k = t["kind"] + ("/cmpr" if t["cm"] else "/raw")
        if t["kind"] == "image":
            k += "/pal" if t["pals"] else "/nopal"
            k += "/guess" if t.get("guess") else ""
            if len(t["pals"]) > 1:
                c["image multi-pal"] += 1
        c[k] += 1
        b[k] += t["size"]
    for k in sorted(c):
        print(f"{k:28s} {c[k]:5d} {b[k]:9d} B")
    if "--sheet" in argv:
        i = argv.index("--sheet")
        sheet(rom, cl, argv[i + 2], argv[i + 1])


if __name__ == "__main__":
    main(sys.argv)
