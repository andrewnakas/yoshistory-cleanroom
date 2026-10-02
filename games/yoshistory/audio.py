"""Yoshi's Story audio: dirty-room facts and clean-room samples.

    python -m games.yoshistory.audio spec <retail rom>      # DIRTY: facts -> spec/audio.json
    python -m games.yoshistory.audio gen                    # CLEAN: samples + books -> work cache (used by generate)

Layout (US ROM; the tables sit in the main segment's data, the engine is the EAD one used by Star Fox 64):
  font table 0xB4F60, sequence table 0xB5460, sample-bank table 0xB5880,
  Audiobank 0xB58B0 (62 fonts), Audiotable 0xE1AD0 (2 banks), Audioseq 0x4F3930 (65 sequences, kept note data).
Font:   u32 drumListOff, u32 instOff[numInst]
Inst:   u8 reloc, lo, hi, decayIdx; u32 envOff; TunedSample low, normal, high  (TunedSample = u32 sampleOff, f32 tuning)
Drum:   u8 decayIdx, pan, reloc, pad; TunedSample; u32 envOff
Sample: u32 codec:4 medium:2 .. size:24; u32 addr (in its sample bank); u32 loopOff; u32 bookOff
Loop:   u32 start, end, count, pad; s16 state[16] if count
Book:   s32 order, npred; s16 book[order * npred * 8]

Kept facts (user scope): per sample its length, rate, loop points, a coarse spectral outline, median pitch and RMS.
The soundfont structure (instruments, envelopes, tunings) and the sequences are kept. Generated: every waveform,
our own VADPCM codebooks (same predictor count, so every font keeps its size) and loop states.
Placeholder voices: games/yoshistory/voices/<key>.wav replaces the resynthesis of that sample when present.
"""
import json
import os
import struct
import sys

import numpy as np

from cleanroom.audio import descriptor, vadpcm
from cleanroom.audio.pitch import median_f0
from cleanroom.decomp.gen import h32

HERE = os.path.dirname(os.path.abspath(__file__))
SPEC = os.path.join(HERE, "spec")
VOICES = os.path.join(HERE, "voices")
CACHE = "D:/n64work/yoshistory/work/audio_cache"
FONT_TABLE, SEQ_TABLE, BANK_TABLE = 0xB4F60, 0xB5460, 0xB5880
AUDIOBANK = 0xB58B0
NOMINAL = 32000
SYNTH_VERSION = 3


def u32(b, o):
    return struct.unpack_from(">I", b, o)[0]


def tables(rom):
    def tab(o):
        n = struct.unpack_from(">H", rom, o)[0]
        return [struct.unpack_from(">IIBBHHH", rom, o + 16 + 16 * i) for i in range(n)]
    fonts = [{"off": AUDIOBANK + a, "size": s, "bank": sd1 >> 8, "ninst": sd2 >> 8, "ndrum": sd2 & 0xFF}
             for a, s, _, _, sd1, sd2, _ in tab(FONT_TABLE)]
    table_base = AUDIOBANK + max(f["off"] - AUDIOBANK + f["size"] for f in fonts)
    banks = [(table_base + a, s) for a, s, *_ in tab(BANK_TABLE)]
    return fonts, banks


def headers(rom, fonts):
    """Every Sample header reachable from the fonts: {rom offset: info}."""
    out = {}

    def tuned(f, o):
        so, tun = struct.unpack_from(">If", rom, o)
        if so == 0 or f["off"] + so + 16 > f["off"] + f["size"]:
            return
        h = f["off"] + so
        w0 = u32(rom, h)
        s = out.setdefault(h, {"hdr": h, "codec": w0 >> 28, "size": w0 & 0xFFFFFF, "addr": u32(rom, h + 4),
                               "loop": f["off"] + u32(rom, h + 8), "book": f["off"] + u32(rom, h + 12),
                               "bank": f["bank"], "tunings": []})
        s["tunings"].append(float(tun))
        if "order" not in s:
            lp, bk = s["loop"], s["book"]
            s["lstart"], s["lend"], s["lcount"] = u32(rom, lp), u32(rom, lp + 4), u32(rom, lp + 8)
            s["order"], s["npred"] = struct.unpack_from(">ii", rom, bk)

    for f in fonts:
        base = f["off"]
        drums = u32(rom, base)
        for i in range(f["ninst"]):
            io = u32(rom, base + 4 + 4 * i)
            if io and io + 32 <= f["size"]:
                for k in range(3):
                    tuned(f, base + io + 8 + 8 * k)
        if drums:
            for i in range(f["ndrum"]):
                do = u32(rom, base + drums + 4 * i)
                if do and do + 16 <= f["size"]:
                    tuned(f, base + do + 4)
    return out


def spec(path):
    rom = open(path, "rb").read()
    fonts, banks = tables(rom)
    hdrs = headers(rom, fonts)
    uniq = {}
    for h in hdrs.values():
        uniq.setdefault((h["bank"], h["addr"]), []).append(h)
    out = {}
    odd = 0
    for (bk, addr), hs in sorted(uniq.items()):
        h = max(hs, key=lambda x: x["size"])
        if h["codec"] != 0 or h["order"] != 2 or not 1 <= h["npred"] <= 8:
            odd += 1
            continue
        start = banks[bk][0] + addr
        data = rom[start:start + h["size"]]
        n = h["size"] // 9 * 16
        coefs = struct.unpack_from(">%dh" % (h["order"] * h["npred"] * 8), rom, h["book"] + 8)
        pcm = vadpcm.decode(data, {"order": h["order"], "npred": h["npred"], "book": list(coefs)}, n)
        tun = float(np.median([t for x in hs for t in x["tunings"]]))
        rate = int(np.clip(round(NOMINAL * tun), 4000, 48000))
        x = pcm.astype(np.float64) / 32768.0
        out[f"{bk}_{addr:06x}"] = {
            "bank": bk, "addr": addr, "size": h["size"], "n": n, "npred": h["npred"], "order": h["order"],
            "hdrs": [x["hdr"] for x in hs], "books": sorted(set(x["book"] for x in hs)),
            "loops": sorted(set(x["loop"] for x in hs)), "sizes": sorted(set(x["size"] for x in hs)),
            "lstart": h["lstart"], "lend": h["lend"], "lcount": h["lcount"], "rate": rate,
            "desc": descriptor.describe(pcm, rate), "f0": median_f0(x, rate),
            "rms": float(np.sqrt(np.mean(x ** 2))), "peak": float(np.abs(x).max())}
    os.makedirs(SPEC, exist_ok=True)
    table_end = banks[-1][0] + banks[-1][1]
    json.dump({"banks": banks, "table": [banks[0][0], table_end], "samples": out},
              open(os.path.join(SPEC, "audio.json"), "w"), separators=(",", ":"))
    secs = sum(d["n"] / d["rate"] for d in out.values())
    print(f"audio spec: {len(fonts)} fonts, {len(out)} unique samples ({len(hdrs)} headers, {odd} skipped), "
          f"{sum(d['size'] for d in out.values()) // 1024} KB, {secs:.0f} s; looped {sum(1 for d in out.values() if d['lcount'])}; "
          f"table {banks[0][0]:x}..{table_end:x}")


# ---------------------------------------------------------------------------------------------- clean room

def k_predictors(x, k):
    """Our own order-2 predictor set with k entries: k-means over per-frame least-squares fits."""
    fits = []
    step = max(16, (len(x) // 4000) // 16 * 16)
    for s in range(2, len(x) - 16, step):
        y, p1, p2 = x[s:s + 16], x[s - 1:s + 15], x[s - 2:s + 14]
        if (y ** 2).sum() < 1e3:
            continue
        a, *_ = np.linalg.lstsq(np.stack([p1, p2], 1), y, rcond=None)
        fits.append(a)
    base = [(0.0, 0.0), (1.0, 0.0), (1.8, -0.82), (1.95, -0.96), (1.5, -0.6), (0.5, 0.0), (1.9, -0.92), (1.2, -0.3)]
    if len(fits) < k:
        return base[:k]
    f = np.clip(np.asarray(fits), [-1.95, -0.98], [1.95, 0.98])
    order = np.argsort(f[:, 0])
    c = np.stack([f[order[int((i + 0.5) * len(f) / k)]] for i in range(k)])
    for _ in range(12):
        lab = np.argmin(((f[:, None, :] - c[None]) ** 2).sum(-1), 1)
        for j in range(k):
            if (lab == j).any():
                c[j] = f[lab == j].mean(0)
    out = []
    for a1, a2 in c:
        a2 = float(np.clip(a2, -0.98, 0.98))
        out.append((float(np.clip(a1, -(1 - a2) + 0.02, (1 - a2) - 0.02)), a2))
    return out


def tone_pitch(d):
    """(f0 Hz, tonal weight 0..1) of a sample from its outline."""
    fr = descriptor._steady_f0(d["desc"]["frames"])
    w = np.array([10 ** (f["rms"] / 20.0) for f in fr]) + 1e-9
    ton = np.array([f["f0"] > 20 and f["h"] > 0.45 for f in fr])
    if not ton.any():
        return 0.0, 0.0
    f0 = float(np.median([f["f0"] for f, t in zip(fr, ton) if t]))
    return f0, float((w * ton).sum() / w.sum())


def tonal(key, d):
    """Pitched instrument sample: steady partials at one exact pitch (a whole number of periods inside the loop, so
    it loops without a click and stays in tune), spectrum and loudness following the outline."""
    n, rate = d["n"], d["rate"]
    f0, _ = tone_pitch(d)
    looped = d["lcount"] and d["lend"] > d["lstart"] + 16
    ls, le = (d["lstart"], min(d["lend"], n)) if looped else (n, n)
    if looped:
        L = le - ls
        f0 = max(1, round(L * f0 / rate)) * rate / L
    fr = d["desc"]["frames"]
    k = len(fr)
    centres = (np.arange(k) + 0.5) * n / k
    t = np.arange(n)
    amps = np.stack([10 ** (np.asarray(f["db"], float) / 20.0) for f in fr])          # (k, bands)
    amps = amps / (amps.max(1, keepdims=True) + 1e-12)
    rms = np.array([10 ** (f["rms"] / 20.0) for f in fr])
    if looped:                                                                          # frozen timbre inside the loop
        inside = (centres >= ls) & (centres < le)
        if not inside.any():
            inside = np.arange(k) == np.argmin(np.abs(centres - (ls + le) / 2))
        hold_a, hold_r = amps[inside].mean(0), float(rms[inside].mean())
    rng = np.random.default_rng(h32("ystone", key))
    x = np.zeros(n)
    env_parts = np.zeros(n)
    for p in range(1, 48):
        fp = f0 * p
        if fp >= rate / 2 - 200:
            break
        ap = np.array([np.interp(np.log(fp), np.log(descriptor.CENTERS), a, left=a[0], right=0.0) for a in amps])
        a_t = np.interp(t, centres, ap)
        if looped:
            hp = float(np.interp(np.log(fp), np.log(descriptor.CENTERS), hold_a, left=hold_a[0], right=0.0))
            fade = np.clip((t - (ls - 256)) / 256.0, 0, 1)
            a_t = a_t * (1 - fade) + hp * fade
        if a_t.max() < 1e-3:
            continue
        x += a_t * np.sin(2 * np.pi * fp * t / rate + rng.uniform(0, 2 * np.pi))
        env_parts += a_t ** 2
    # loudness contour from the outline (per-frame RMS), constant inside the loop
    r_t = np.interp(t, centres, rms)
    if looped:
        fade = np.clip((t - (ls - 256)) / 256.0, 0, 1)
        r_t = r_t * (1 - fade) + hold_r * fade
    cur = np.sqrt(env_parts / 2.0) + 1e-9
    x = x / cur * r_t
    a = min(48, n // 8)
    if a > 1:
        x[:a] *= np.linspace(0, 1, a)
        if not looped:
            x[-a:] *= np.linspace(1, 0, a)
    return x


def waveform(key, d):
    n, rate = d["n"], d["rate"]
    vp = os.path.join(VOICES, key + ".wav")
    f0, tw = tone_pitch(d)
    if os.path.exists(vp):
        from .voices import read_wav
        x = read_wav(vp, rate)
        x = np.concatenate([x, np.zeros(max(0, n - len(x)))])[:n]
    elif f0 > 20 and tw > 0.6 and n >= 64:
        x = tonal(key, d)
    else:
        x = np.asarray(descriptor.synthesize(d["desc"], n, rate, seed=h32("yssmp", key)), np.float64)
        if d["lcount"] and d["lend"] > d["lstart"] + 32:
            x = np.asarray(descriptor.make_loop_seamless(x, d["lstart"], min(d["lend"], n)), np.float64)
    x = np.asarray(x, np.float64)
    rms = float(np.sqrt(np.mean(x ** 2))) if len(x) else 0.0
    if rms > 1e-6 and d.get("rms"):
        x = x * (d["rms"] / rms)
    peak = float(np.abs(x).max()) if len(x) else 0.0
    lim = min(0.98, max(d.get("peak", 0.98), 0.05))
    if peak > lim:
        x = x * (lim / peak)
    return np.clip(np.round(x * 32767.0), -32768, 32767).astype(np.int64)


def groups(S):
    """Samples that share a codebook must be encoded with the same one: [[key, ...], ...]."""
    parent = {}

    def find(a):
        while parent.setdefault(a, a) != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    for k, d in S.items():
        for b in d["books"]:
            parent[find(("b", b))] = find(("s", k))
    g = {}
    for k in S:
        g.setdefault(find(("s", k)), []).append(k)
    return list(g.values())


def _one(item):
    keys, S, stamp = item
    tag = f"{h32('ysgrp', '+'.join(keys)):08x}"
    cp = os.path.join(CACHE, tag + ".npz")
    if os.path.exists(cp):
        z = np.load(cp, allow_pickle=True)
        if str(z["stamp"]) == stamp:
            return z["out"].item()
    pcms = {k: waveform(k, S[k]) for k in keys}
    allp = np.concatenate([pcms[k] for k in keys]).astype(np.float64)
    npred = S[keys[0]]["npred"]
    preds = k_predictors(allp, npred)
    book = vadpcm.make_book(preds)
    while max(abs(v) for v in book["book"]) > 32767:
        preds = [(a1 * 0.97, a2 * 0.97) for a1, a2 in preds]
        book = vadpcm.make_book(preds)
    out = {"coefs": [int(np.clip(v, -32768, 32767)) for v in book["book"]], "data": {}, "state": {}}
    for k in keys:
        d = S[k]
        data, _, dec = vadpcm.encode(pcms[k], book)
        out["data"][k] = (data + bytes(d["size"]))[:d["size"]]
        if d["lcount"]:
            out["state"][k] = vadpcm.loop_state(dec, d["lstart"])
    os.makedirs(CACHE, exist_ok=True)
    np.savez(cp, stamp=stamp, out=np.array(out, dtype=object))
    return out


def stamp_of(keys, S):
    vs = [os.path.getmtime(os.path.join(VOICES, k + ".wav")) if os.path.exists(os.path.join(VOICES, k + ".wav")) else 0
          for k in keys]
    return f"{SYNTH_VERSION}:{vs}:{[S[k]['size'] for k in keys]}"


def gen(jobs=4, log=print):
    """-> list of group results (cached on disk; only changed groups are recomputed)."""
    from multiprocessing import Pool
    J = json.load(open(os.path.join(SPEC, "audio.json")))
    S = J["samples"]
    G = sorted(groups(S), key=lambda ks: -sum(S[k]["n"] for k in ks))
    items = [(ks, {k: S[k] for k in ks}, stamp_of(ks, S)) for ks in G]
    res = []
    with Pool(jobs) as pool:
        for i, r in enumerate(pool.imap(_one, items, chunksize=1)):
            res.append(r)
            if i % 100 == 0:
                log(f"  audio {i}/{len(items)}")
    return J, res


def apply(rom, log=print):
    """Write our samples, codebooks and loop states into the ROM image (bytearray)."""
    J, res = gen(log=log)
    S, banks = J["samples"], J["banks"]
    t0, t1 = J["table"]
    rom[t0:t1] = bytes(t1 - t0)                              # nothing of the retail sample data stays
    nb = 0
    for r in res:
        for k, data in r["data"].items():
            d = S[k]
            start = banks[d["bank"]][0] + d["addr"]
            rom[start:start + len(data)] = data
            blob = struct.pack(">%dh" % len(r["coefs"]), *r["coefs"])
            for bo in d["books"]:
                rom[bo + 8:bo + 8 + len(blob)] = blob
                nb += 1
            st = r["state"].get(k)
            if st is not None:
                for lo in d["loops"]:
                    rom[lo + 16:lo + 48] = struct.pack(">16h", *st)
    log(f"audio: {len(S)} samples in {len(res)} codebook groups written, {nb} books, table {t1 - t0} B rebuilt")


if __name__ == "__main__":
    if sys.argv[1] == "spec":
        spec(sys.argv[2])
    else:
        gen()
