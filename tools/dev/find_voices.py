"""DEV (dirty): which samples are voice clips? Silero VAD (speech fraction) + outline heuristics -> work/voice_scan.json"""
import json, struct, sys
import numpy as np
sys.path.insert(0, '.')
from cleanroom.audio import vadpcm
from games.yoshistory import audio
from faster_whisper.vad import get_speech_timestamps, VadOptions
rom = open('D:/n64work/yoshistory/baserom.us.z64', 'rb').read()
J = json.load(open('games/yoshistory/spec/audio.json')); S = J['samples']; banks = J['banks']
out = {}
for k, d in sorted(S.items()):
    dur = d['n'] / d['rate']
    if d['lcount'] or dur < 0.15:
        continue
    o = banks[d['bank']][0] + d['addr']
    coefs = struct.unpack_from(">%dh" % (d['npred'] * 16), rom, d['books'][0] + 8)
    x = vadpcm.decode(rom[o:o + d['size']], {"order": 2, "npred": d['npred'], "book": list(coefs)}, d['n']).astype(np.float32) / 32768
    y = np.interp(np.arange(0, len(x), d['rate'] / 16000), np.arange(len(x)), x).astype(np.float32)
    y = np.concatenate([np.zeros(4000, np.float32), y, np.zeros(4000, np.float32)])
    ts = get_speech_timestamps(y, VadOptions(threshold=0.35, min_speech_duration_ms=60, min_silence_duration_ms=50))
    sp = sum(t['end'] - t['start'] for t in ts) / max(1, len(y) - 8000)
    f0, tw = audio.tone_pitch(d)
    out[k] = dict(dur=round(dur, 2), speech=round(float(min(sp, 1)), 2), f0=round(f0), tw=round(tw, 2), rate=d['rate'], bank=d['bank'])
json.dump(out, open('D:/n64work/yoshistory/work/voice_scan.json', 'w'))
v = [k for k, r in out.items() if r['speech'] >= 0.5]
print(len(out), 'non-looped clips;', len(v), 'with speech >= 0.5; per bank', [sum(1 for k in v if out[k]['bank'] == b) for b in (0, 1)])
print('total voice seconds %.0f' % sum(out[k]['dur'] for k in v))
import collections
print(sorted(collections.Counter(round(out[k]['dur']) for k in v).items()))
print([ (k, out[k]['dur'], out[k]['f0']) for k in v[:25]])
