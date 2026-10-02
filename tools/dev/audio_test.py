"""DEV (dirty): retail ROM + parts of our audio, boot check.  audio_test.py <variant>"""
import json, struct, subprocess, sys, os
sys.path.insert(0, '.')
from games.yoshistory import audio
W = 'D:/n64work/yoshistory/'
if __name__ == '__main__':
    retail = open(W + 'baserom.us.z64', 'rb').read()
    J, res = audio.gen(log=lambda *a: None)
    S, banks = J['samples'], J['banks']
    v = sys.argv[1]
    rom = bytearray(retail)
    keys = sorted(S)
    lo, hi = (int(x) for x in sys.argv[2:4]) if len(sys.argv) > 3 else (0, len(keys))
    sel = set(keys[lo:hi])
    if v == 'gaps':
        cov = bytearray(J['table'][1] - J['table'][0])
        for d in S.values():
            a = banks[d['bank']][0] + d['addr'] - J['table'][0]
            cov[a:a + d['size']] = b'\1' * d['size']
        import numpy as np
        a = np.frombuffer(bytes(rom[J['table'][0]:J['table'][1]]), np.uint8).copy()
        a[np.frombuffer(bytes(cov), np.uint8) == 0] = 0
        rom[J['table'][0]:J['table'][1]] = a.tobytes()
    for r in res:
        for k, data in r['data'].items():
            if k not in sel:
                continue
            d = S[k]
            start = banks[d['bank']][0] + d['addr']
            if v in ('data', 'all'):
                rom[start:start + len(data)] = data
            if v in ('books', 'all'):
                blob = struct.pack(">%dh" % len(r['coefs']), *r['coefs'])
                for bo in d['books']:
                    rom[bo + 8:bo + 8 + len(blob)] = blob
            if v in ('loops', 'all'):
                st = r['state'].get(k)
                if st is not None:
                    for l in d['loops']:
                        rom[l + 16:l + 48] = struct.pack(">16h", *st)
    from games.yoshistory.generate import crc6106
    struct.pack_into('>II', rom, 0x10, *crc6106(rom))
    open(W + 'devsite/test.z64', 'wb').write(rom)
    p = subprocess.run([sys.executable, 'ports/ejs/cdp_shot.py', W + 'shots/au', '--port', '9471', '--url',
                        'http://localhost:8471/index.html?rom=test.z64', '--gpu', '--script', '14:shot,22:shot', '--wait', '40'],
                       env=dict(os.environ, CDP_MUTE='1'), capture_output=True, text=True)
    from PIL import Image
    import numpy as np
    try: m = float(np.asarray(Image.open(W + 'shots/au/shot_22.png').convert('L')).mean())
    except Exception: m = -1
    print(v, lo, hi, p.stdout.strip()[:14], 'brightness %.1f' % m)
