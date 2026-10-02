"""Taint scan (dev, reads the retail ROM): no regenerated asset of the clean ROM may still hold its retail bytes.

    python -m games.yoshistory.taint <retail rom> <clean rom>

Fails: an image / palette / sample / codebook whose bytes equal retail (unless trivial: one or two byte values),
retail bytes left in archive space that no spec item covers, an identical ROM. Prints what is kept, by category.
"""
import hashlib
import json
import os
import struct
import sys

import numpy as np

from . import archive as A
from .extract_spec import SPEC


def trivial(b):
    return len(set(b)) <= 4


def main(argv):
    retail = open(argv[1], "rb").read()
    clean = open(argv[2], "rb").read()
    fails = []
    if hashlib.sha1(retail).digest() == hashlib.sha1(clean).digest():
        fails.append("ROM identical to retail")
    J = json.load(open(os.path.join(SPEC, "archive.json")))
    cov = np.zeros(len(retail), np.uint8)            # 1 image, 2 palette, 3 kept table, 4 sample, 5 book/loop state
    n = dict(img=0, pal=0, smp=0, book=0)
    for e in J["images"]:
        o, s = e["off"], e["slot"] if e["cm"] else e["size"]
        cov[o:o + s] = 1
        n["img"] += 1
        if retail[o:o + s] == clean[o:o + s] and not trivial(retail[o:o + s]):
            fails.append(f"image {o:x}")
        elif s >= 64:
            a = np.frombuffer(retail[o:o + s], np.uint8)
            b = np.frombuffer(clean[o:o + s], np.uint8)
            if (a == b).mean() > 0.9 and not trivial(retail[o:o + s]):
                fails.append(f"image {o:x} ({(a == b).mean():.0%} same)")
    for p in J["palettes"]:
        o, s = p["off"], p["size"]
        cov[o:o + s] = 2
        n["pal"] += 1
        if retail[o:o + s] == clean[o:o + s] and not trivial(retail[o:o + s]):
            fails.append(f"palette {o:x}")
    for k in J["kept"]:
        o = k["off"]
        s = 16 + struct.unpack_from(">I", retail, o + 4)[0] - 12 if k["cm"] else k["size"]
        cov[o:o + max(s, 0)] = np.where(cov[o:o + max(s, 0)] == 0, 3, cov[o:o + max(s, 0)])
    for q, src, size in J.get("aliases", []):
        cov[q:q + size] = 2
        if retail[q:q + size] == clean[q:q + size]:
            fails.append(f"palette copy {q:x}")
    for o, s, _ in J.get("kept_raw", []):
        cov[o:o + s] = 3
    ap = os.path.join(SPEC, "audio.json")
    table = (0, 0)
    if os.path.exists(ap):
        AJ = json.load(open(ap))
        table = tuple(AJ["table"])
        for key, d in AJ["samples"].items():
            o = AJ["banks"][d["bank"]][0] + d["addr"]
            cov[o:o + d["size"]] = 4
            n["smp"] += 1
            if retail[o:o + d["size"]] == clean[o:o + d["size"]] and not trivial(retail[o:o + d["size"]]):
                fails.append(f"sample {key}")
            for bo in d["books"]:
                m = d["order"] * d["npred"] * 16
                cov[bo + 8:bo + 8 + m] = 5
                n["book"] += 1
                if retail[bo + 8:bo + 8 + m] == clean[bo + 8:bo + 8 + m]:
                    fails.append(f"codebook {bo:x}")
        # the rest of the sample table must not be retail
        a = np.frombuffer(retail[table[0]:table[1]], np.uint8)
        b = np.frombuffer(clean[table[0]:table[1]], np.uint8)
        same = int(((a == b) & (a != 0) & (cov[table[0]:table[1]] == 0)).sum())
        if same:
            fails.append(f"sample table: {same} uncovered retail bytes")
    else:
        fails.append("audio spec missing (samples are retail)")
    # archive space no spec item covers: must be empty or changed
    r = np.frombuffer(retail, np.uint8)
    c = np.frombuffer(clean, np.uint8)
    lo, hi = A.DESC_END, 0x9E6BC0
    un = (cov[lo:hi] == 0) & (r[lo:hi] != 0) & (r[lo:hi] == c[lo:hi])
    idx = np.nonzero(un)[0]
    runs = []
    if len(idx):
        br = np.nonzero(np.diff(idx) > 16)[0]
        st = np.concatenate([[idx[0]], idx[br + 1]])
        en = np.concatenate([idx[br], [idx[-1]]])
        runs = [(int(s) + lo, int(e - s) + 1) for s, e in zip(st, en) if e - s + 1 >= 64]
    for s, m in runs:
        fails.append(f"uncovered archive data {s:x}+{m:x}")
    same = (r == c)
    cats = [("header + main code/data (kept: code)", 0, 0xB4F60), ("audio tables + Audiobank (kept: structure)", 0xB4F60, table[0] or 0xE1AD0),
            ("Audiotable (samples)", table[0] or 0xE1AD0, table[1] or 0x4F3930), ("Audioseq (kept: note data)", table[1] or 0x4F3930, A.SEG3),
            ("archive descriptors (kept: layout)", A.SEG3, A.DESC_END), ("archive files", A.DESC_END, 0x9E6BC0),
            ("Yoshi display lists / frames (kept: geometry)", 0x9E6BC0, 0xB47A10), ("overlays (kept: code, geometry)", 0xB47A10, A.DATA_END),
            ("free space", A.DATA_END, len(retail))]
    print(f"taint: {n['img']} images, {n['pal']} palettes, {n['smp']} samples, {n['book']} codebooks checked")
    for name, a0, a1 in cats:
        nz = r[a0:a1] != 0
        print(f"  {name:48s} {a0:7x}..{a1:7x}  same as retail {int((same[a0:a1] & nz).sum()) / max(1, int(nz.sum())):5.1%} of non-zero bytes")
    print(f"taint: {len(fails)} failing", fails[:12])
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
