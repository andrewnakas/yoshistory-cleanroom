"""DEV (dirty): delta-debug which regenerated archive items break level 1. Finds a minimal set of spec images whose
restoration to retail makes the level-1 screenshot match the retail reference. Log: work/ddmin.log"""
import json, struct, subprocess, sys, os
import numpy as np
from PIL import Image
sys.path.insert(0, '.')
from games.yoshistory import archive as A
W = 'D:/n64work/yoshistory/'
retail = open(W + 'baserom.us.z64', 'rb').read()
clean = open(W + 'build/clean.z64', 'rb').read()
J = json.load(open('games/yoshistory/spec/archive.json'))
ps = {p['off']: p['size'] for p in J['palettes']}
users = {}
for u, (ro, sz, cm) in A.triples(retail).items():
    users.setdefault(ro, []).append(u)
items = [e for e in J['images'] if e['off'] < 0xB47A10]
ref = np.asarray(Image.open(W + 'shots/r3/shot_84.png').convert('RGB').resize((64, 48), Image.BILINEAR), float)
log = open(W + 'work/ddmin.log', 'a')
runs = [0]


def test(sel):
    rom = bytearray(clean)
    for e in sel:
        o = e['off']
        rom[o:o + e['slot']] = retail[o:o + e['slot']]
        for u in users.get(o, []):
            rom[u:u + 12] = retail[u:u + 12]
        for p in e['pals']:
            rom[p:p + ps[p]] = retail[p:p + ps[p]]
    open(W + 'devsite/test.z64', 'wb').write(rom)
    env = dict(os.environ, CDP_MUTE='1')
    subprocess.run([sys.executable, 'ports/ejs/cdp_shot.py', W + 'shots/dd', '--port', '9471', '--url',
                    'http://localhost:8471/index.html?rom=test.z64', '--gpu', '--script',
                    '24:Enter:0.2,32:Enter:0.2,44:Enter:0.2,48:x:0.2,56:x:0.2,60:x:0.2,68:x:0.2,76:x:0.2,84:shot'],
                   env=env, capture_output=True)
    try:
        d = float(np.abs(np.asarray(Image.open(W + 'shots/dd/shot_84.png').convert('RGB').resize((64, 48), Image.BILINEAR), float) - ref).mean())
    except Exception:
        d = 999.0
    runs[0] += 1
    log.write(f"run {runs[0]} restored {len(sel)} diff {d:.1f}\n"); log.flush()
    return d < 45


R = items
assert test(R), "restoring every image does not fix it"
n = 2
while len(R) >= 2:
    size = max(1, len(R) // n)
    chunks = [R[i:i + size] for i in range(0, len(R), size)]
    reduced = False
    for i in range(len(chunks)):
        rest = [e for j, c in enumerate(chunks) if j != i for e in c]
        if test(rest):
            R = rest; n = max(n - 1, 2); reduced = True
            break
    if not reduced:
        if n >= len(R):
            break
        n = min(len(R), n * 2)
    log.write("R=%d n=%d %s\n" % (len(R), n, [hex(e['off']) for e in R][:20])); log.flush()
log.write("FINAL %s\n" % [(hex(e['off']), e['w'], e['rows'], e['cm']) for e in R]); log.flush()
print("FINAL", [(hex(e['off']), e['w'], e['rows'], e['cm']) for e in R])
