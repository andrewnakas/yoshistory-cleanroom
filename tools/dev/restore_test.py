"""DEV (dirty): clean ROM with a subset of archive items restored to retail bytes (bisecting).
   restore_test.py <out> tiles|nopal|small|kindX ...   (never published)"""
import json, struct, sys
sys.path.insert(0, '.')
from games.yoshistory import archive as A
retail = open('D:/n64work/yoshistory/baserom.us.z64', 'rb').read()
rom = bytearray(open('D:/n64work/yoshistory/build/clean.z64', 'rb').read())
J = json.load(open('games/yoshistory/spec/archive.json'))
ps = {p['off']: p['size'] for p in J['palettes']}
users = {}
for u, (ro, sz, cm) in A.triples(retail).items():
    users.setdefault(ro, []).append(u)
what = sys.argv[2:]
n = 0
for e in J['images']:
    sel = ('tiles' in what and e['w'] == 16 and e['rows'] >= 1024) or \
          ('nopal' in what and not e['pals']) or \
          ('parts' in what and not e['cm'] and e['off'] < 0xB47A10) or \
          ('cmpr' in what and e['cm'] and not (e['w'] == 16 and e['rows'] >= 1024)) or \
          ('ovl' in what and e['off'] >= 0xB47A10)
    if not sel:
        continue
    o = e['off']
    rom[o:o + e['slot']] = retail[o:o + e['slot']]
    for u in users.get(o, []):
        rom[u:u + 12] = retail[u:u + 12]
    for p in e['pals']:
        rom[p:p + ps[p]] = retail[p:p + ps[p]]
    n += 1
for w in what:
    if ':' in w:                       # raw range a:b (hex)
        a, b = (int(x, 16) for x in w.split(':'))
        rom[a:b] = retail[a:b]
open(sys.argv[1], 'wb').write(rom)
print('restored', n, what)
