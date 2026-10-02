"""DEV (dirty): retail ROM with every compressed archive image re-encoded by our SMSR encoder (codec/placement test)."""
import json, struct, sys
sys.path.insert(0, '.')
from games.yoshistory import archive as A, smsr
retail = open('D:/n64work/yoshistory/baserom.us.z64', 'rb').read()
rom = bytearray(retail)
J = json.load(open('games/yoshistory/spec/archive.json'))
users = {}
for u, (ro, sz, cm) in A.triples(retail).items():
    users.setdefault(ro, []).append(u)
free = 0xEBDA70
only = set(int(x, 16) for x in sys.argv[2:])
n = moved = 0
for e in J['images']:
    if not e['cm'] or (only and e['off'] not in only):
        continue
    off = e['off']
    data, _ = smsr.decode(retail, off)
    enc = smsr.encode(data)
    dst = off
    if len(enc) > e['slot']:
        moved += 1
        continue
    old = 16 + struct.unpack_from(">I", retail, off + 4)[0]
    rom[off:off + old] = bytes(old)
    for u in users.get(off, []):
        struct.pack_into(">II", rom, u + 4, struct.unpack_from(">I", enc, 4)[0], dst - A.SEG3 + 0x03000000)
    rom[dst:dst + len(enc)] = enc
    n += 1
open(sys.argv[1], 'wb').write(rom)
print(n, 'reencoded', moved, 'moved', hex(free))
