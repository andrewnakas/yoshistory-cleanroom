"""Dev: one contact sheet from a cdp_shot output folder.   python -m games.yoshistory.look <shots dir> [cols]"""
import glob
import re
import sys

from PIL import Image, ImageDraw


def main(argv):
    d = argv[1]
    cols = int(argv[2]) if len(argv) > 2 else 3
    fs = sorted(glob.glob(d + "/shot_*.png"), key=lambda f: float(re.findall(r"_([\d.]+)\.png", f)[0]))
    w = 1440 // cols
    ims = []
    for f in fs:
        im = Image.open(f).convert("RGB")
        im = im.crop((0, 0, im.width, int(im.height * 0.9)))
        im = im.resize((w, int(im.height * w / im.width)))
        ImageDraw.Draw(im).text((4, 4), re.findall(r"_([\d.]+)\.png", f)[0] + "s", fill=(255, 255, 0))
        ims.append(im)
    h = ims[0].height
    sh = Image.new("RGB", (w * cols, h * ((len(ims) + cols - 1) // cols)))
    for i, im in enumerate(ims):
        sh.paste(im, ((i % cols) * w, (i // cols) * h))
    sh.save(d + "_sheet.png")
    print(d + "_sheet.png", sh.size)


if __name__ == "__main__":
    main(sys.argv)
