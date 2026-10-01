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
    return (not cm) and sz >= 16 and sz % 2 == 0 and sz <= 0x400


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
                    p = rec(pal)
                    p["kind"] = "palette"
                    if pal[0] not in t["pals"]:
                        t["pals"].append(pal[0])
    # unreferenced CMPR files
    for o in smsr.find_all(rom):
        if o not in out:
            sz = struct.unpack_from(">I", rom, o + 8)[0]
            out[o] = dict(kind="unref", size=sz, cm=True, pals=[], runs=[], w=0, fh=0, bpp=8)
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
