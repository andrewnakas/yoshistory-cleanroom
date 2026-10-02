"""Yoshi's voice clips: placeholder TTS voices (clean) and the practice pack (dirty, personal use, never published).

    python -m games.yoshistory.voices scan <retail rom>      # DIRTY: which samples are voice clips -> spec/voices.json
    python -m games.yoshistory.voices practice <retail rom>  # DIRTY: D:/n64work/yoshistory/practice (clips to imitate)
    python -m games.yoshistory.voices build                  # CLEAN: Piper placeholders -> games/yoshistory/voices/<key>.wav
    python -m games.yoshistory.voices cut <recording.wav>    # the user's takes -> games/yoshistory/voices/<key>.wav

The placeholders are a stock TTS voice saying short made-up Yoshi words, lifted in pitch: our own performance of
nonsense syllables, not a copy of the original performer. The user's own recordings replace them (cut).
"""
import json
import os
import struct
import sys
import wave

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
SPEC = os.path.join(HERE, "spec")
VOICES = os.path.join(HERE, "voices")
PRACTICE = "D:/n64work/yoshistory/practice"
PIPER_DIR = "C:/Users/andre/n64work/piper_voices"
MODEL = "en_US-amy-medium"
LIFT = 2 ** (7 / 12)                      # pitch lift (speak slower, play faster)
HZ = 22050
WORDS = [(0.3, ["Yah!", "Hup!", "Ha!"]), (0.5, ["Wah!", "Yup!", "Hey!", "Boing!"]), (0.8, ["Yoshi!", "Woo hoo!", "Yippee!"]),
         (1.2, ["Yoshi yoshi!", "Woo hoo hoo!", "Oh no no!"]), (1.7, ["Yoshi, yoshi yoshi!", "La la, la la!"]),
         (9.9, ["La la la, la la la, la!", "Yoshi, yoshi, yoshi yoshi!"])]


def read_wav(p, rate=None):
    with wave.open(p) as w:
        x = np.frombuffer(w.readframes(w.getnframes()), "<i2").astype(np.float64) / 32768
        sr = w.getframerate()
    if rate and rate != sr:
        x = np.interp(np.arange(0, len(x), sr / rate), np.arange(len(x)), x)
    return x


def write_wav(p, x, sr):
    with wave.open(p, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(int(sr))
        w.writeframes((np.clip(x, -1, 1) * 32767).astype("<i2").tobytes())


def keys():
    V = json.load(open(os.path.join(SPEC, "voices.json")))
    return sorted(V), V


def word_for(key, dur):
    from cleanroom.decomp.gen import h32
    for lim, opts in WORDS:
        if dur < lim:
            return opts[h32("ysword", key) % len(opts)]


def decode_retail(rom, J, key):
    from cleanroom.audio import vadpcm
    d = J["samples"][key]
    o = J["banks"][d["bank"]][0] + d["addr"]
    coefs = struct.unpack_from(">%dh" % (d["npred"] * 16), rom, d["books"][0] + 8)
    x = vadpcm.decode(rom[o:o + d["size"]], {"order": 2, "npred": d["npred"], "book": list(coefs)}, d["n"])
    return x.astype(np.float32) / 32768, d["rate"]


def scan(path):
    """Silero VAD over every non-looped clip: the ones that are mostly voice."""
    from faster_whisper.vad import VadOptions, get_speech_timestamps
    rom = open(path, "rb").read()
    J = json.load(open(os.path.join(SPEC, "audio.json")))
    out = {}
    for k, d in sorted(J["samples"].items()):
        dur = d["n"] / d["rate"]
        if d["lcount"] or dur < 0.15:
            continue
        x, sr = decode_retail(rom, J, k)
        y = np.interp(np.arange(0, len(x), sr / 16000), np.arange(len(x)), x).astype(np.float32)
        y = np.concatenate([np.zeros(4000, np.float32), y, np.zeros(4000, np.float32)])
        ts = get_speech_timestamps(y, VadOptions(threshold=0.35, min_speech_duration_ms=60, min_silence_duration_ms=50))
        if sum(t["end"] - t["start"] for t in ts) / max(1, len(y) - 8000) >= 0.5:
            out[k] = {"dur": round(dur, 2)}
    json.dump(out, open(os.path.join(SPEC, "voices.json"), "w"), indent=0)
    print(f"voices: {len(out)} voice clips, {sum(v['dur'] for v in out.values()):.0f} s")


def layout():
    """[(key, clip_len, gap)] in track order (clip, 0.3 s, 80 ms beep, gap 1.5x + 1.5 s)."""
    ks, V = keys()
    J = json.load(open(os.path.join(SPEC, "audio.json")))
    out = []
    for k in ks:
        d = J["samples"][k]
        n = len(np.arange(0, d["n"], d["rate"] / HZ))
        out.append((k, n, int((n / HZ * 1.5 + 1.5) * HZ)))
    return out


def practice(path):
    rom = open(path, "rb").read()
    J = json.load(open(os.path.join(SPEC, "audio.json")))
    os.makedirs(os.path.join(PRACTICE, "clips"), exist_ok=True)
    beep = (0.2 * np.sin(2 * np.pi * 880 * np.arange(int(0.08 * HZ)) / HZ)).astype(np.float32)
    parts = []
    lines = ["Yoshi's Story voice practice. Listen, then make the sound after each beep (2-3 takes if you like).",
             "Record the track as one file, then: python -m games.yoshistory.voices cut <file>",
             "These clips come from your own ROM: practice only, never share or commit them.", "",
             "== yoshi  (practice_yoshi_call_and_response.wav)"]
    for i, (k, n, gap) in enumerate(layout(), 1):
        x, sr = decode_retail(rom, J, k)
        x = np.interp(np.arange(0, len(x), sr / HZ), np.arange(len(x)), x).astype(np.float32)
        write_wav(os.path.join(PRACTICE, "clips", f"{i:02d}_{k}.wav"), x, HZ)
        parts += [x, np.zeros(int(0.3 * HZ), np.float32), beep, np.zeros(gap, np.float32)]
        lines.append(f"  {k}  max {n / HZ:.1f}s  \"(Yoshi sound {i})\"")
    track = np.concatenate(parts)
    write_wav(os.path.join(PRACTICE, "practice_yoshi_call_and_response.wav"), track, HZ)
    open(os.path.join(PRACTICE, "SCRIPT.txt"), "w", encoding="utf8").write("\n".join(lines) + "\n")
    print(f"practice pack: {len(lines) - 5} clips, {len(track) / HZ / 60:.1f} min -> {PRACTICE}")


def steady(d):
    """Held pitch: most of the clip is tonal and its pitch stays within a semitone."""
    from . import audio
    from cleanroom.audio import descriptor
    f0, tw = audio.tone_pitch(d)
    fr = [f["f0"] for f in descriptor._steady_f0(d["desc"]["frames"]) if f["f0"] > 20 and f["h"] > 0.45]
    return tw > 0.6 and len(fr) >= 2 and (max(fr) / min(fr)) < 1.06


def build():
    import librosa
    from piper import PiperVoice, SynthesisConfig
    ks, V = keys()
    J = json.load(open(os.path.join(SPEC, "audio.json")))
    os.makedirs(VOICES, exist_ok=True)
    voice = PiperVoice.load(os.path.join(PIPER_DIR, MODEL + ".onnx"))
    sr = voice.config.sample_rate

    def say(text, length):
        cfg = SynthesisConfig(length_scale=length, noise_scale=0.6, noise_w_scale=0.8)
        x = np.concatenate([c.audio_float_array for c in voice.synthesize(text, syn_config=cfg)]).astype(np.float32)
        idx = np.nonzero(np.abs(x) > 0.01)[0]
        return x[max(0, idx[0] - 200):idx[-1] + 400] if len(idx) else x

    spoken = 0
    for k in ks:
        d = J["samples"][k]
        dur = d["n"] / d["rate"]
        if steady(d):                        # a held, sung note (used as an instrument): the tone resynthesis stays
            if os.path.exists(os.path.join(VOICES, k + ".wav")):
                os.remove(os.path.join(VOICES, k + ".wav"))
            continue
        spoken += 1
        text = word_for(k, dur)
        t0 = len(say(text, 1.0)) / sr
        x = say(text, float(np.clip(dur * LIFT * 0.92 / max(t0, 0.05), 0.45, 2.2)))
        y = librosa.resample(x, orig_sr=sr * LIFT, target_sr=d["rate"]).astype(np.float32)
        y = y[:d["n"]]
        f = min(len(y), int(0.02 * d["rate"]))
        if f > 1:
            y[-f:] *= np.linspace(1, 0, f)
        write_wav(os.path.join(VOICES, k + ".wav"), y / max(1e-6, float(np.abs(y).max())) * 0.8, d["rate"])
    print(f"voices: {spoken} of {len(ks)} voice clips spoken (rest are steady sung notes); placeholder clips ({MODEL}, +7 semitones) -> {VOICES}")


def cut(path):
    """Cut the user's recording of the practice track: the loudest stretch of each response window."""
    x = read_wav(path, HZ)
    J = json.load(open(os.path.join(SPEC, "audio.json")))
    lay = layout()
    # align: the recording may start late; find the offset that puts the most energy inside the windows
    t, wins = 0, []
    for k, n, gap in lay:
        b = t + n + int(0.3 * HZ) + int(0.08 * HZ)
        wins.append((k, b, gap, n))
        t = b + gap
    e = np.abs(x)
    best, off = -1, 0
    for o in range(-HZ * 3, HZ * 6, HZ // 20):
        s = sum(e[max(0, b + o):max(0, b + o + g)].sum() for _, b, g, _ in wins)
        if s > best:
            best, off = s, o
    os.makedirs(VOICES, exist_ok=True)
    done = 0
    for k, b, gap, n in wins:
        seg = x[max(0, b + off):max(0, b + off + gap)]
        idx = np.nonzero(np.abs(seg) > max(0.02, 0.15 * float(np.abs(seg).max() if len(seg) else 0)))[0]
        if not len(idx):
            continue
        seg = seg[max(0, idx[0] - 300):idx[0] + int(n * 1.05)]
        d = J["samples"][k]
        y = np.interp(np.arange(0, len(seg), HZ / d["rate"]), np.arange(len(seg)), seg)
        write_wav(os.path.join(VOICES, k + ".wav"), y / max(1e-6, float(np.abs(y).max())) * 0.8, d["rate"])
        done += 1
    print(f"cut: {done}/{len(wins)} takes -> {VOICES} (offset {off / HZ:+.2f} s); rebuild with tools/build_clean.sh")


if __name__ == "__main__":
    {"scan": scan, "practice": practice, "build": lambda *a: build(), "cut": cut}[sys.argv[1]](*sys.argv[2:3])
