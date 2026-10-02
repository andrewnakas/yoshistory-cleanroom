"""DEV: side by side retail / clean decode of one archive image.  cmp_tiles.py <off hex> <out.png> [first tile] [count]"""
import json, struct, sys
import numpy as np
from PIL import Image
sys.path.insert(0, '.')
from games.yoshistory import archive as A, smsr
off = int(sys.argv[1], 16)
J = json.load(open('games/yoshistory/spec/archive.json'))
e = [x for x in J['images'] if x['off'] == off][0]
ps = {p['off']: p['size'] for p in J['palettes']}
out = []
for path in ('D:/n64work/yoshistory/baserom.us.z64', 'D:/n64work/yoshistory/build/clean.z64'):
    rom = open(path, 'rb').read()
    trip = A.triples(rom)
    # follow the descriptor (the clean ROM may have moved the file)
    retail = open('D:/n64work/yoshistory/baserom.us.z64', 'rb').read()
    u = [u for u, t in A.triples(retail).items() if t[0] == off]
    ro = struct.unpack_from(">I", rom, u[0] + 8)[0] - 0x03000000 + A.SEG3 if u else off
    data = smsr.decode(rom, ro)[0] if e['cm'] else rom[ro:ro + e['size']]
    a = np.frombuffer(data, np.uint8)
    if e['bpp'] == 4:
        a = np.stack([a >> 4, a & 15], 1).reshape(-1)
    po = e['pals'][0]
    pal = np.concatenate([A.pal_rgba(rom[po:po + ps[po]]), np.zeros((256, 4), np.uint8)])[:256]
    w, fh = e['w'], e['fh']
    fr = a[:e['rows'] * w].reshape(-1, fh, w)
    first = int(sys.argv[3]) if len(sys.argv) > 3 else 0
    cnt = int(sys.argv[4]) if len(sys.argv) > 4 else 128
    fr = fr[first:first + cnt]
    cols = max(1, min(16, 512 // w))
    rows = (len(fr) + cols - 1) // cols
    sh = np.zeros((rows * (fh + 1), cols * (w + 1), 4), np.uint8); sh[..., 3] = 255; sh[..., 2] = 80
    for i, f in enumerate(fr):
        c = pal[f].copy(); c[c[..., 3] == 0] = (255, 0, 255, 255)
        sh[(i // cols) * (fh + 1):(i // cols) * (fh + 1) + fh, (i % cols) * (w + 1):(i % cols) * (w + 1) + w] = c
    out.append(Image.fromarray(sh, 'RGBA').convert('RGB'))
W = out[0].width * 2 + 8
im = Image.new('RGB', (W, out[0].height))
im.paste(out[0], (0, 0)); im.paste(out[1], (out[0].width + 8, 0))
sc = max(1, min(4, 1800 // W))
im.resize((W * sc, im.height * sc), Image.NEAREST).save(sys.argv[2])
print(e['w'], e['rows'], e['fh'], len(fr), im.size)
