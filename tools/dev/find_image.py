"""DEV (dirty): which spec image draws a screen region? Binary search: restore half of the images to retail and see
whether the region gets closer to the retail screenshot.   find_image.py x0 y0 x1 y1   (coords in the 934x667 shot at 84 s)"""
import json, struct, subprocess, sys, os
import numpy as np
from PIL import Image
sys.path.insert(0, '.')
from games.yoshistory import archive as A
if __name__ == '__main__':
    W = 'D:/n64work/yoshistory/'
    box = tuple(int(v) for v in sys.argv[1:5])
    retail = open(W + 'baserom.us.z64', 'rb').read()
    clean = open(W + 'build/clean_noaudio.z64', 'rb').read()
    J = json.load(open('games/yoshistory/spec/archive.json'))
    ps = {p['off']: p['size'] for p in J['palettes']}
    users = {}
    for u, (ro, sz, cm) in A.triples(retail).items():
        users.setdefault(ro, []).append(u)
    ref = np.asarray(Image.open(W + 'shots/r3/shot_84.png').convert('RGB').crop(box), float)
    log = open(W + 'work/find_image.log', 'a')

    def test(sel):
        rom = bytearray(clean)
        for e in sel:
            o = e['off']
            s = e['slot'] if e['cm'] else e['size']
            rom[o:o + s] = retail[o:o + s]
            for u in users.get(o, []):
                rom[u:u + 12] = retail[u:u + 12]
            for q in e['pals']:
                rom[q:q + ps[q]] = retail[q:q + ps[q]]
        open(W + 'devsite/test.z64', 'wb').write(rom)
        subprocess.run([sys.executable, 'ports/ejs/cdp_shot.py', W + 'shots/fi', '--port', '9471', '--url',
                        'http://localhost:8471/index.html?rom=test.z64', '--gpu', '--script',
                        '24:Enter:0.2,32:Enter:0.2,44:Enter:0.2,48:x:0.2,56:x:0.2,60:x:0.2,68:x:0.2,76:x:0.2,84:shot'],
                       env=dict(os.environ, CDP_MUTE='1'), capture_output=True)
        try:
            d = float(np.abs(np.asarray(Image.open(W + 'shots/fi/shot_84.png').convert('RGB').crop(box), float) - ref).mean())
        except Exception:
            d = 999.0
        log.write(f"restored {len(sel)} diff {d:.1f}\n"); log.flush()
        return d

    R = J['images'][:373]
    base = 64.4
    while len(R) > 1:
        h = len(R) // 2
        a = test(R[:h])
        b = test(R[h:]) if a > base - 6 else 999
        print("halves %.1f %.1f" % (a, b), file=log, flush=True)
        R = R[:h] if a <= b else R[h:]
        print("R=%d %s" % (len(R), [hex(e['off']) for e in R][:6]), file=log, flush=True)
    print("FOUND", hex(R[0]['off']), R[0]['w'], R[0]['rows'], R[0]['fh'], R[0]['pals'])
