"""DIRTY ROOM: retail ROM -> spec/archive.json + spec/archive.bin (kept facts only).

    python -m games.yoshistory.extract_spec <retail rom>

Per image of the asset archive: storage facts (offset, size, slot, width, frame height, bits per pixel, palettes)
and, per frame (sprite frame or 16x16 tile), a 4x4 colour grid (16x16 for frames >= 128 px) plus the opacity
outline (1 bit per texel; palette-less 8/4-bit images: 2-bit level). No texel colours, no palettes.
"""
import json
import os
import sys
import zlib

import numpy as np

from . import archive as A
from .classify import classify

HERE = os.path.dirname(os.path.abspath(__file__))
SPEC = os.path.join(HERE, "spec")
OVERRIDES = os.path.join(HERE, "image_overrides.json")


# archive space no descriptor covers that is not picture data (looked at once on a dev sheet)
RAW_KEPT = [[0x6BC41A, 0x181F6, "16-bit record tables (animation / geometry)"]]


def cells(n_px, n):
    """Cell boundaries (like cleanroom.decomp.spec.grid)."""
    return [(g * n_px // n, max(g * n_px // n + 1, (g + 1) * n_px // n)) for g in range(n)]


def grid_n(w, fh):
    return 16 if max(w, fh) >= 128 else 4


def frame_grids(rgba, fh):
    """rgba (H, W, 4) float -> (frames, n, n, 4) uint8: mean colour of opaque texels per cell, alpha = coverage."""
    H, W = rgba.shape[:2]
    n = grid_n(W, fh)
    nf = H // fh
    out = np.zeros((nf, n, n, 4), np.uint8)
    cy, cx = cells(fh, n), cells(W, n)
    for f in range(nf):
        fr = rgba[f * fh:(f + 1) * fh]
        for gy, (y0, y1) in enumerate(cy):
            for gx, (x0, x1) in enumerate(cx):
                c = fr[y0:y1, x0:x1].reshape(-1, 4)
                a = c[:, 3] > 127
                if a.any():
                    out[f, gy, gx, :3] = np.round(c[a, :3].mean(0))
                out[f, gy, gx, 3] = int(round(255 * a.mean()))
    return out


def main(argv):
    rom = open(argv[1], "rb").read()
    cl = classify(rom)
    if os.path.exists(OVERRIDES):
        for k, v in json.load(open(OVERRIDES)).items():
            if k.startswith("_"):
                continue
            t = cl[int(k, 16)]
            for q in v.pop("add_pals", []):                  # a palette stored next to the image, not in a descriptor
                q = int(q, 16)
                cl[q] = dict(kind="palette", size=0x200, cm=False, pals=[], runs=[], w=0, fh=0, bpp=8)
                t["pals"] = [q] + [x for x in t["pals"] if x != q]
            t.update(v)
            if t["kind"] == "image" and not t["w"]:
                data = A.read(rom, (int(k, 16), t["size"], t["cm"]))
                t["w"] = A.guess_width(data)[0]
                t["fh"] = t["w"] if (len(data) // t["w"]) % t["w"] == 0 else len(data) // t["w"]
    offs = sorted(cl)
    blob = bytearray()

    def put(arr):
        b = np.ascontiguousarray(arr).tobytes()
        o = len(blob)
        blob.extend(b)
        return [o, len(b)]

    index = {"images": [], "palettes": [], "kept": []}
    nfr = 0
    for i, o in enumerate(offs):
        t = cl[o]
        nxt = offs[i + 1] if i + 1 < len(offs) else o + (16 + int.from_bytes(rom[o + 4:o + 8], "big") if t["cm"] else t["size"])
        slot = nxt - o
        if t["kind"] == "palette":
            index["palettes"].append({"off": o, "size": t["size"]})
            continue
        if t["kind"] != "image" or not t["w"]:
            index["kept"].append({"off": o, "size": t["size"], "cm": t["cm"]})
            continue
        data = A.read(rom, (o, t["size"], t["cm"]))
        a = np.frombuffer(data, np.uint8)
        w, bpp = t["w"], t["bpp"]
        if bpp == 4:
            a = np.stack([a >> 4, a & 15], 1).reshape(-1)
        rows = len(a) // w
        fh = t["fh"] if t["fh"] and rows % t["fh"] == 0 else rows
        idx = a[:rows * w].reshape(rows, w)
        e = {"off": o, "size": t["size"], "cm": t["cm"], "slot": slot, "w": w, "rows": rows, "fh": fh, "bpp": bpp,
             "pals": t["pals"], "users": len(t["runs"])}
        if t["pals"]:
            e["grids"] = []
            for k, po in enumerate(t["pals"]):
                pal = np.concatenate([A.pal_rgba(rom[po:po + cl[po]["size"]]), np.zeros((256, 4), np.uint8)])[:256]
                rgba = pal[idx].astype(np.float32)
                e["grids"].append(put(frame_grids(rgba, fh)))
                if k == 0:
                    e["alpha"] = put(np.packbits(rgba[..., 3] > 127))
        else:
            # intensity image: grid of mean level + 2-bit level outline
            v = idx.astype(np.float32) * (17 if bpp == 4 else 1)
            lv = (v.astype(np.uint8) >> 6).ravel()
            if t.get("ia"):                                  # IA8: grid of intensity, 2-bit alpha outline
                e["ia"] = True
                lv = ((idx & 15) >> 2).astype(np.uint8).ravel()
                v = (idx >> 4).astype(np.float32) * 17
            rgba = np.stack([v, v, v, np.full_like(v, 255)], -1)
            e["grids"] = [put(frame_grids(rgba, fh))]
            lv = np.concatenate([lv, np.zeros(-len(lv) % 4, np.uint8)])
            e["level2"] = put((lv[0::4] << 6) | (lv[1::4] << 4) | (lv[2::4] << 2) | lv[3::4])
        nfr += rows // fh
        index["images"].append(e)
    # copies of a palette that no descriptor points at (they follow small tables): regenerated as copies
    cov = np.zeros(len(rom), np.uint8)
    for e in index["images"]:
        cov[e["off"]:e["off"] + (e["slot"] if e["cm"] else e["size"])] = 1
    for p in index["palettes"]:
        cov[p["off"]:p["off"] + p["size"]] = 1
    for k in index["kept"]:
        cov[k["off"]:k["off"] + (int.from_bytes(rom[k["off"] + 4:k["off"] + 8], "big") + 4 if k["cm"] else k["size"])] = 1
    index["aliases"] = []
    seen = set()
    for p in index["palettes"]:
        b = rom[p["off"]:p["off"] + p["size"]]
        if p["size"] < 0x200 or b in seen or len(set(b)) <= 2:
            continue
        seen.add(b)
        q = rom.find(b, A.DESC_END)
        while 0 <= q < A.DATA_END:
            if q != p["off"] and not cov[q:q + p["size"]].any():
                index["aliases"].append([q, p["off"], p["size"]])
                cov[q:q + p["size"]] = 1
            q = rom.find(b, q + 2)
    index["kept_raw"] = RAW_KEPT
    os.makedirs(SPEC, exist_ok=True)
    json.dump(index, open(os.path.join(SPEC, "archive.json"), "w"), separators=(",", ":"))
    open(os.path.join(SPEC, "archive.bin"), "wb").write(zlib.compress(bytes(blob), 9))
    print(f"spec: {len(index['images'])} images ({nfr} frames/tiles), {len(index['palettes'])} palettes, "
          f"{len(index['kept'])} kept tables, {len(index['aliases'])} palette copies; blob {len(blob) // 1024} KB")


if __name__ == "__main__":
    main(sys.argv)
