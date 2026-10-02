"""CLEAN ROOM: spec + the game's program (code, layout, text, sequences) -> clean ROM.

    python -m games.yoshistory.generate <retail rom> <clean rom out>

The retail ROM is used only as the carrier of kept facts (code, geometry, tile maps, tables, text). Every image and
palette listed in spec/archive.json is rebuilt here from its grid + outline and written into its original slot.
"""
import json
import os
import struct
import sys
import zlib

import numpy as np

from . import archive as A
from . import smsr
from .extract_spec import SPEC, cells, grid_n

FREE_START, FREE_END = 0xEBDA70, (0xEBDA70 if os.environ.get("YS_NOMOVE") else 0x1000000)          # 0xFF padding in the retail layout
HOOKS = []          # later passes (drawn text, faces, ...) register (off -> rgba override) here


def load_spec():
    index = json.load(open(os.path.join(SPEC, "archive.json")))
    blob = zlib.decompress(open(os.path.join(SPEC, "archive.bin"), "rb").read())
    return index, blob


def get(blob, ref, dtype=np.uint8):
    return np.frombuffer(blob, dtype, count=ref[1] // np.dtype(dtype).itemsize, offset=ref[0])


def up(g, w, h, smooth):
    """(n, n) or (n, n, c) grid -> (h, w[, c]) by cell (smooth: bilinear between cell centres)."""
    n = g.shape[0]
    if not smooth:
        yi = np.zeros(h, int)
        xi = np.zeros(w, int)
        for k, (a, b) in enumerate(cells(h, n)):
            yi[a:b] = k
        for k, (a, b) in enumerate(cells(w, n)):
            xi[a:b] = k
        return g[yi][:, xi]
    ys = (np.arange(h, dtype=np.float32) + 0.5) / h * n - 0.5
    xs = (np.arange(w, dtype=np.float32) + 0.5) / w * n - 0.5
    y0 = np.clip(np.floor(ys).astype(int), 0, n - 1)
    x0 = np.clip(np.floor(xs).astype(int), 0, n - 1)
    y1, x1 = np.clip(y0 + 1, 0, n - 1), np.clip(x0 + 1, 0, n - 1)
    fy = np.clip(ys - np.floor(ys), 0, 1).reshape(-1, 1, *([1] * (g.ndim - 2)))
    fx = np.clip(xs - np.floor(xs), 0, 1).reshape(1, -1, *([1] * (g.ndim - 2)))
    top = g[y0][:, x0] * (1 - fx) + g[y0][:, x1] * fx
    bot = g[y1][:, x0] * (1 - fx) + g[y1][:, x1] * fx
    return top * (1 - fy) + bot * fy


def render_rgb(e, grids, smooth=True):
    """Frame grids -> (rows, w, 3) float colour image (colour only where the cell had opaque texels)."""
    w, fh, rows = e["w"], e["fh"], e["rows"]
    n = grid_n(w, fh)
    g = grids.reshape(-1, n, n, 4).astype(np.float32)
    out = np.zeros((rows, w, 3), np.float32)
    if smooth < 0:                                   # coarser tiers for images that must fit a tight slot
        g[..., :3] = np.round(g[..., :3] / 32.0) * 32.0
    for f in range(rows // fh):
        cov = g[f, ..., 3:4] / 255.0
        if cov.max() <= 0:
            continue
        if smooth < -1:
            out[f * fh:(f + 1) * fh] = np.round((g[f, ..., :3] * cov).sum((0, 1)) / cov.sum() / 32.0) * 32.0
            continue
        smooth = smooth > 0
        num = up(g[f, ..., :3] * cov, w, fh, smooth)
        den = up(cov, w, fh, smooth)
        mean = (g[f, ..., :3] * cov).sum((0, 1)) / cov.sum()
        out[f * fh:(f + 1) * fh] = np.where(den > 1e-3, num / np.maximum(den, 1e-3), mean)
    return out


def render_level(e, blob, smooth=True):
    """Palette-less image: 2-bit level outline shaded by the grid -> (rows, w) uint8."""
    w, fh, rows = e["w"], e["fh"], e["rows"]
    b = get(blob, e["level2"])
    lv = np.empty(len(b) * 4, np.uint8)
    lv[0::4], lv[1::4], lv[2::4], lv[3::4] = b >> 6, (b >> 4) & 3, (b >> 2) & 3, b & 3
    lv = lv[:rows * w].reshape(rows, w).astype(np.float32)
    n = grid_n(w, fh)
    g = get(blob, e["grids"][0]).reshape(-1, n, n, 4).astype(np.float32)[..., 0]
    out = np.zeros((rows, w), np.float32)
    if e.get("ia"):
        inten = np.concatenate([up(g[f], w, fh, True) for f in range(rows // fh)])
        return ((np.clip(np.round(inten / 17), 0, 15).astype(np.uint8) << 4) | (lv.astype(np.uint8) * 5))
    for f in range(rows // fh):
        base = up(g[f], w, fh, smooth > 0)
        band = lv[f * fh:(f + 1) * fh]
        if smooth < 0:
            base = band * 64 + 32
        # stay inside the kept 2-bit band, shaded by the coarse grid
        out[f * fh:(f + 1) * fh] = np.clip(base, band * 64, band * 64 + 63)
        if not e.get("soft0", True):
            out[f * fh:(f + 1) * fh][band == 0] = 0                     # flat background stays empty
    out = np.round(out / 8) * 8 if smooth <= 0 else out
    return np.clip(out, 0, 255).astype(np.uint8)


def median_cut(vecs, weights, k):
    """vecs (N, D) uint8, weights (N,) -> (labels (N,), centres (k', D) float)."""
    boxes = [np.arange(len(vecs))]
    v = vecs.astype(np.int32)
    while len(boxes) < k:
        best, bi, bd = 0, -1, 0
        for i, ix in enumerate(boxes):
            if len(ix) < 2:
                continue
            sub = v[ix]
            rng = sub.max(0) - sub.min(0)
            d = int(rng.argmax())
            score = float(rng[d]) * float(weights[ix].sum()) ** 0.5
            if score > best:
                best, bi, bd = score, i, d
        if bi < 0:
            break
        ix = boxes[bi]
        order = ix[np.argsort(v[ix, bd], kind="stable")]
        cw = np.cumsum(weights[order])
        cut = int(np.searchsorted(cw, cw[-1] / 2.0))
        cut = min(max(cut, 1), len(order) - 1)
        boxes[bi] = order[:cut]
        boxes.append(order[cut:])
    labels = np.zeros(len(vecs), np.int32)
    centres = np.zeros((len(boxes), vecs.shape[1]), np.float32)
    for i, ix in enumerate(boxes):
        labels[ix] = i
        centres[i] = (v[ix] * weights[ix, None]).sum(0) / max(1e-9, weights[ix].sum())
    return labels, centres


def components(images):
    parent = {}

    def find(x):
        while parent.setdefault(x, x) != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for e in images:
        for p in e["pals"]:
            parent[find(("p", p))] = find(("i", e["off"]))
    comp = {}
    for e in images:
        if e["pals"]:
            comp.setdefault(find(("i", e["off"])), []).append(e)
    return list(comp.values())


def rgba16(c, a):
    r, g, b = (int(max(0, min(31, round(x / 255.0 * 31)))) for x in c)
    return (r << 11) | (g << 6) | (b << 1) | (1 if a else 0)


def build_component(imgs, blob, pal_sizes, overrides, smooth=True, shrink=1.0):
    """Returns ({image off: index bytes}, {palette off: palette bytes})."""
    pals = []
    for e in imgs:
        for p in e["pals"]:
            if p not in pals:
                pals.append(p)
    K = min(pal_sizes[p] // 2 for p in pals)
    K = max(2, int(K * shrink)) if shrink < 1 else K
    vec_parts, alphas = [], []
    for e in imgs:
        a = np.unpackbits(get(blob, e["alpha"]))[:e["rows"] * e["w"]].astype(bool)
        cols = {}
        for k, p in enumerate(e["pals"]):
            if (e["off"], p) in overrides:
                c = overrides[(e["off"], p)]
                cols[p] = c[..., :3].reshape(-1, 3).astype(np.float32)
                if k == 0:
                    a = c[..., 3].reshape(-1) > 127
            else:
                cols[p] = render_rgb(e, get(blob, e["grids"][k]), smooth).reshape(-1, 3)
        prim = cols[e["pals"][0]]
        full = np.concatenate([cols.get(p, prim) for p in pals], 1)
        vec_parts.append(full)
        alphas.append(a)
    allv = np.concatenate(vec_parts)
    alla = np.concatenate(alphas)
    has_tr = bool((~alla).any())
    q = np.clip(np.round(allv / 255.0 * 31), 0, 31).astype(np.uint8)
    op = q[alla]
    idx_all = np.zeros(len(q), np.int32)
    first = 1 if has_tr else 0
    if len(op):
        uq, inv, cnt = np.unique(op, axis=0, return_inverse=True, return_counts=True)
        labels, centres = median_cut(uq, cnt.astype(np.float64), max(1, K - first))
        idx_all[alla] = labels[inv.reshape(-1)] + first
    else:
        centres = np.zeros((1, 3 * len(pals)), np.float32)
    out_pal = {}
    for j, p in enumerate(pals):
        n = pal_sizes[p] // 2
        ent = []
        if has_tr:
            ent.append(0)
        for c in centres[:n - first]:
            ent.append(rgba16(c[3 * j:3 * j + 3] / 31.0 * 255.0, True))
        while len(ent) < n:
            ent.append(ent[-1])
        out_pal[p] = struct.pack(">%dH" % n, *ent[:n])
    out_img = {}
    pos = 0
    for e in imgs:
        n = e["rows"] * e["w"]
        ix = np.clip(idx_all[pos:pos + n], 0, 255).astype(np.uint8)
        pos += n
        if e["bpp"] == 4:
            ix = ((ix[0::2] & 15) << 4) | (ix[1::2] & 15)
        out_img[e["off"]] = ix.tobytes()
    return out_img, out_pal


def crc6106(rom):
    """Header checksum pair as the CIC-6106 boot code computes it over 0x1000..0x101000."""
    w = np.frombuffer(bytes(rom[0x1000:0x101000]), dtype=">u4").tolist()
    M = 0xFFFFFFFF
    t1 = t2 = t3 = t4 = t5 = t6 = 0x1FEA617A
    for d in w:
        if (t6 + d) & M < t6:
            t4 = (t4 + 1) & M
        t6 = (t6 + d) & M
        t3 ^= d
        k = d & 31
        r = ((d << k) | (d >> (32 - k))) & M
        t5 = (t5 + r) & M
        t2 ^= r if t2 > d else t6 ^ d
        t1 = (t1 + (t5 ^ d)) & M
    return ((t6 * t4 + t3) & M, (t5 * t2 + t1) & M)


FAULT_FONT = 0xA8C0C            # crash-screen font: 256 words, 8x8 glyphs, 8 characters share 16 words


def fault_font():
    """Our own 8x8 glyphs (stroke font) in the layout Fault_PrintCharImpl reads."""
    from cleanroom.gfx import strokefont as sf
    words = [0] * 256
    for c in range(0x20, 0x7F):
        m = sf.render(chr(c).upper() if chr(c).upper() in sf.G or chr(c) not in sf.G else chr(c), 7, 8, 0.55) > 0.3
        base = (c // 8) * 16 + ((c & 4) >> 2)
        for i in range(8):
            for j in range(7):
                if m[i, j]:
                    words[base + 2 * i] |= (0x10000000 << (c % 4)) >> (4 * j)
    return struct.pack(">256I", *words)


def pack(e, data):
    data = data + b"\0" * (e["size"] - len(data))
    assert len(data) == e["size"], (hex(e["off"]), len(data), e["size"])
    return smsr.encode(data) if e["cm"] else data


def build(retail, log=print):
    index, blob = load_spec()
    rom = bytearray(retail)
    pal_sizes = {p["off"]: p["size"] for p in index["palettes"]}
    overrides = {}
    from . import drawn
    for h in HOOKS + [drawn.hook]:
        overrides.update(h(index, blob))
    users = {}
    for u, (ro, sz, cm) in A.triples(retail).items():
        users.setdefault(ro, []).append(u)
    files = {}
    stats = dict(images=0, palettes=0, coarse=0, shrunk=0)
    fail = []
    moved = {}                                         # image off -> new ROM offset (free space after the archive)
    free = FREE_START
    for imgs in components(index["images"]):
        ok = False
        for smooth, shrink in ((1, 1.0), (0, 1.0), (0, 0.5), (-1, 0.25), (-2, 0.1), (-2, 0.02)):
            oi, op = build_component(imgs, blob, pal_sizes, overrides, smooth, shrink)
            enc = {e["off"]: pack(e, oi[e["off"]]) for e in imgs}
            big = [e for e in imgs if len(enc[e["off"]]) > e["slot"]]
            # a file that outgrows its slot moves to the unused end of the ROM (its descriptors are re-pointed)
            if all(e["cm"] and users.get(e["off"]) for e in big) and                     free + sum(len(enc[e["off"]]) for e in big) <= FREE_END:
                for e in big:
                    moved[e["off"]] = free
                    free += len(enc[e["off"]])
                ok = True
                break
        if not ok:
            fail += [hex(e["off"]) for e in big]
            continue
        stats["coarse"] += (smooth <= 0) * len(imgs)
        stats["shrunk"] += (shrink < 1) * len(imgs)
        files.update(enc)
        for p, b in op.items():
            rom[p:p + len(b)] = b
            stats["palettes"] += 1
        stats["images"] += len(imgs)
    for e in index["images"]:
        if e["pals"]:
            continue
        for smooth in (1, 0, -1):
            px = render_level(e, blob, smooth)
            if e["bpp"] == 4:
                v = px.reshape(-1) >> 4
                px = ((v[0::2] << 4) | v[1::2]).astype(np.uint8)
            enc = pack(e, px.tobytes())
            if len(enc) <= e["slot"]:
                break
        if len(enc) > e["slot"]:
            fail.append(hex(e["off"]))
            continue
        files[e["off"]] = enc
        stats["images"] += 1
    by_off = {e["off"]: e for e in index["images"]}
    for off, enc in files.items():
        e = by_off[off]
        dst = moved.get(off, off)
        if e["cm"]:
            rom[off:off + e["slot"]] = bytes(e["slot"])          # the slot ends where the next file starts
            comp = struct.unpack_from(">I", enc, 4)[0]
            for u in users.get(off, []):
                struct.pack_into(">II", rom, u + 4, comp, dst - A.SEG3 + 0x03000000)
        assert dst != off or len(enc) <= e["slot"]
        rom[dst:dst + len(enc)] = enc
    if os.environ.get("YS_VERBOSE"):
        for off in moved:
            e = by_off[off]
            log(f"  moved {off:x} w={e['w']} rows={e['rows']} fh={e['fh']} slot={e['slot']:x} new={len(files[off]):x} users={[hex(u) for u in users[off]]}")
    stats["moved"] = len(moved)
    stats["moved_kb"] = (free - FREE_START) // 1024
    log(f"generate: {stats['images']} images, {stats['palettes']} palettes written "
        f"({stats['moved']} moved = {stats['moved_kb']} KB, {stats['coarse']} blocky, {stats['shrunk']} with a reduced palette); not fitting: {len(fail)} {fail[:8]}")
    for q, src, size in index.get("aliases", []):
        rom[q:q + size] = rom[src:src + size]
    if not os.environ.get("YS_NOAUDIO"):
        from . import audio
        audio.apply(rom, log)
    rom[FAULT_FONT:FAULT_FONT + 0x400] = fault_font()
    struct.pack_into(">II", rom, 0x10, *crc6106(rom))      # the boot code refuses a ROM whose first MB changed
    return bytes(rom), fail


def main(argv):
    retail = open(argv[1], "rb").read()
    rom, fail = build(retail)
    open(argv[2], "wb").write(rom)
    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
