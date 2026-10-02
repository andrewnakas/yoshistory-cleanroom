"""CLEAN ROOM: re-typeset text that lives inside textures (a 4x4 grid cannot carry letters).

The words are the game's text (kept fact); the letters are drawn with our own stroke font and coloured by the kept
colour grid of the texture they replace (so "Story Mode" stays red-to-yellow, "Practice" green-to-yellow, ...).
Briefs: WORDS = groups of tiles that form one picture, with the lines of text they show.
"""
import numpy as np
from scipy import ndimage

from cleanroom.gfx import strokefont as sf

# menu overlay (ROM 0xBD4A20): 48x42 CI8 tiles side by side; [tiles], [lines]; a line is (text, y0, y1)
MENU = [
    ([0xBE6F30, 0xBE7920, 0xBE8310], [("Options", 0, 42)]),
    ([0xBE8D00, 0xBE96F0, 0xBEA0E0], [("Practice", 0, 42)]),
    ([0xBEAAD0, 0xBEB4C0, 0xBEBEB0, 0xBEC8A0], [("Story Mode", 0, 42)]),
    ([0xBF2210, 0xBF2C00, 0xBF35F0, 0xBF3FE0], [("Trial Mode", 0, 42)]),
] + [
    ([0xBED290, 0xBEDC80, 0xBEE670, t], [("Story Mode", 0, 25), ("Start From P.%d" % n, 24, 42)])
    for n, t in ((2, 0xBEF060), (3, 0xBEFA50), (4, 0xBF0440), (5, 0xBF0E30), (6, 0xBF1820))
]


# headings: 256 x 48 frames stored upside down (frame 0 English, frame 1 Japanese); (image, frame, text)
HEADINGS = [(0x563980, 0, "GAME OVER"), (0x5672F0, 0, "Select Yoshi"), (0x639EB0, 0, "Reveal Lucky Fruit")]


def fit_line(text, w, h, bold=None):
    """Mask (h, w) of one centred line that fills the box."""
    th = max(1.0, h * (bold or (0.13 if h >= 28 else 0.09)))
    aspect = 1.1
    m = sf.render_line(text, h, aspect, th)
    if m.shape[1] > w:
        aspect *= (w - 2 * th) / m.shape[1]
        m = sf.render_line(text, h, max(0.35, aspect), th)
    while m.shape[1] > w and th > 1.0:
        th -= 0.25
        m = sf.render_line(text, h, max(0.35, aspect), th)
    out = np.zeros((h, w), np.float32)
    mw = min(w, m.shape[1])
    x = (w - mw) // 2
    out[:, x:x + mw] = m[:, :mw]
    return out


def word_art(lines, colour, outline=2, pad=3, bold=None):
    """lines [(text, y0, y1)], colour (H, W, 3) kept-grid render -> RGBA (H, W, 4): bright letters, dark rim."""
    H, W = colour.shape[:2]
    mask = np.zeros((H, W), np.float32)
    for text, y0, y1 in lines:
        mask[y0 + pad:y1 - pad, pad:W - pad] = np.maximum(
            mask[y0 + pad:y1 - pad, pad:W - pad], fit_line(text, W - 2 * pad, y1 - y0 - 2 * pad, bold))
    core = mask > 0.5
    rim = ndimage.binary_dilation(core, iterations=outline) & ~core
    c = colour.astype(np.float32)
    c = c * (255.0 / np.maximum(c.max(-1, keepdims=True), 1.0))            # full brightness, hue from the grid
    out = np.zeros((H, W, 4), np.float32)
    out[core, :3] = c[core]
    out[rim, :3] = c[rim] * 0.22 + np.array([40, 0, 60], np.float32) * 0.5
    out[..., 3] = (core | rim) * 255.0
    return np.clip(out, 0, 255).astype(np.uint8)


def saturate(c, k=1.8):
    c = np.asarray(c, np.float32)
    m = c.mean(-1, keepdims=True)
    return np.clip(m + (c - m) * k, 0, 255)


def boost(c):
    c = saturate(c)
    return c * (255.0 / max(float(c.max()), 1.0))


def yoshi(d, S, cx, cy, r, col, face=1):
    """A simple Yoshi head (our own drawing): round head, big snout, cheek, two tall eyes."""
    col = tuple(int(v) for v in boost(col))
    dark = tuple(int(v * 0.35) for v in col)

    def ell(x0, y0, x1, y1, fill, outline=dark):
        d.ellipse([S * x0, S * y0, S * x1, S * y1], fill=fill, outline=outline, width=S)

    ell(cx - r, cy - r * 0.9, cx + r, cy + r * 0.9, col)                                    # head
    ell(cx + face * r * 0.25 - r * 0.85, cy - r * 0.1, cx + face * r * 0.25 + r * 0.85, cy + r * 1.05, col)   # snout
    ell(cx - face * r * 0.75 - r * 0.45, cy + r * 0.25, cx - face * r * 0.75 + r * 0.45, cy + r * 1.0, (255, 255, 255))  # cheek
    for k in (-1, 1):                                                                       # eyes
        ex = cx + face * r * 0.1 + k * r * 0.33
        ell(ex - r * 0.3, cy - r * 1.35, ex + r * 0.3, cy - r * 0.25, (255, 255, 255), (30, 30, 30))
        ell(ex + face * r * 0.05 - r * 0.11, cy - r * 0.95, ex + face * r * 0.05 + r * 0.11, cy - r * 0.45, (20, 20, 20), None)


# title page (328 x 384, three animation frames): where things are, read once from the dev sheet
TITLE_LOGO = (20, 80, 296, 144)          # "YOSHI'S STORY"
TITLE_COPY = (88, 291, 240, 310)
TITLE_YOSHIS = [(92, 196, 26, -1), (150, 172, 24, 1), (210, 186, 27, 1), (250, 200, 22, 1), (132, 214, 30, 1),
                (72, 262, 26, 1), (190, 240, 24, -1)]
TITLE_EGGS = [(44, 152, 15), (286, 236, 14)]


def title_pages(e, blob):
    from PIL import Image, ImageDraw
    from . import generate as G
    base = G.render_rgb(e, G.get(blob, e["grids"][0]), True)
    fh, w = e["fh"], e["w"]
    out = np.zeros((e["rows"], w, 4), np.uint8)
    out[..., 3] = 255
    S = 3
    for f in range(e["rows"] // fh):
        c = base[f * fh:(f + 1) * fh]
        im = Image.fromarray(np.clip(c, 0, 255).astype(np.uint8), "RGB").resize((w * S, fh * S), Image.BILINEAR)
        d = ImageDraw.Draw(im)
        for x, y, r in TITLE_EGGS:
            d.ellipse([S * (x - r), S * (y - r * 1.2), S * (x + r), S * (y + r * 1.2)], fill=(250, 250, 245), outline=(90, 90, 90), width=S)
            for k, (dx, dy) in enumerate(((-0.4, -0.5), (0.35, 0.0), (-0.2, 0.55))):
                d.ellipse([S * (x + dx * r - r * 0.28), S * (y + dy * r - r * 0.28), S * (x + dx * r + r * 0.28), S * (y + dy * r + r * 0.28)],
                          fill=(60, 170, 70))
        for x, y, r, face in sorted(TITLE_YOSHIS, key=lambda t: t[1]):
            yoshi(d, S, x, y, r, c[min(fh - 1, y), min(w - 1, x)], face)
        px = np.asarray(im.resize((w, fh), Image.LANCZOS), np.float32)
        # logo: letters coloured by the kept grid (the rainbow), dark rim
        x0, y0, x1, y1 = TITLE_LOGO
        art = word_art([("YOSHI'S STORY", 0, y1 - y0)], saturate(c[y0:y1, x0:x1], 2.2), outline=2, pad=2, bold=0.17)
        a = art[..., 3:4] / 255.0
        px[y0:y1, x0:x1] = px[y0:y1, x0:x1] * (1 - a) + art[..., :3] * a
        x0, y0, x1, y1 = TITLE_COPY
        m = fit_line("(C) 1998 Nintendo", x1 - x0, y1 - y0, 0.1)[..., None]
        px[y0:y1, x0:x1] = px[y0:y1, x0:x1] * (1 - m) + np.array([20, 30, 170], np.float32) * m
        out[f * fh:(f + 1) * fh, :, :3] = np.clip(px, 0, 255)
    return out


def hook(index, blob):
    from . import generate as G
    by = {e["off"]: e for e in index["images"]}
    out = {}
    for tiles, lines in MENU:
        es = [by[t] for t in tiles]
        colour = np.concatenate([G.render_rgb(e, G.get(blob, e["grids"][0]), True) for e in es], 1)
        art = word_art(lines, colour)
        x = 0
        for e in es:
            out[(e["off"], e["pals"][0])] = art[:, x:x + e["w"]]
            x += e["w"]
    for off, frame, text in HEADINGS:
        e = by[off]
        w, fh = e["w"], e["fh"]
        key = (off, e["pals"][0])
        if key not in out:
            rgb = G.render_rgb(e, G.get(blob, e["grids"][0]), True)
            a = np.unpackbits(G.get(blob, e["alpha"]))[:e["rows"] * w].reshape(e["rows"], w)
            out[key] = np.concatenate([np.clip(rgb, 0, 255), a[..., None] * 255.0], -1).astype(np.uint8)
        y0 = frame * fh
        colour = out[key][y0:y0 + fh, :, :3][::-1]
        out[key][y0:y0 + fh] = word_art([(text, 0, fh)], colour, outline=2, pad=3, bold=0.15)[::-1]
    from .classify import TITLE_PIX
    e = by[TITLE_PIX]
    out[(e["off"], e["pals"][0])] = title_pages(e, blob)
    return out
