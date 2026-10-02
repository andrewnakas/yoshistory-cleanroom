# Yoshi's Story clean room: status

**PUBLISHED** https://andrewnakas.github.io/yoshistory-cleanroom/ (repo andrewnakas/yoshistory-cleanroom, site = gh-pages).
Boots, level 1 plays, regenerated graphics and audio, taint 0 failing. Checked in headless Edge only (not by ear).

## What works (2026-10-01, loop 2)
- Build: `sh tools/build_clean.sh` (generate -> taint -> dev site + core patch), publish: `sh tools/publish.sh "msg"`.
  Dev site `D:/n64work/yoshistory/devsite` on port 8471 (8093 belongs to another session).
- Images: 1495 images + 776 palettes regenerated (archive sprites/tiles, Yoshi body parts, 375 overlay textures,
  title pages); smooth 4x4-grid renders + kept 1-bit outline; 27 oversized files moved to the free end of the ROM.
- Readable: title page (logo, (C) line, simple drawn Yoshis), menu words (Story Mode, Trial Mode, Options,
  Practice, Start From P.n) re-typeset with our stroke font in `games/yoshistory/drawn.py`. Message font is crisp.
- Audio: 62 fonts, 445 samples resynthesised (pitched ones as steady partials looping on whole periods), own
  codebooks + loop states, sequences kept. Header checksum (CIC-6106) recomputed.
- Voices: 98 voice clips found (speech detector); 97 Piper placeholders (amy, +7 semitones, made-up Yoshi words)
  in `games/yoshistory/voices/`; practice pack in `D:/n64work/yoshistory/practice/` (6 min track + SCRIPT.txt).

## Decisions (log)
- Web route = 3 (clean ROM + WASM emulator): no PC port, decomp splits only `main`; assets found by our scanners.
- Compressed files are packed 4-aligned and the header size field is ~12 bytes larger than the stored file: a slot
  ends where the next file starts (zeroing "16 + comp" bytes clipped the next file = scrambled levels; fixed).
- Oversized regenerated files move to the 0xFF padding after 0xEBDA70 and their descriptors are re-pointed.
- Audio engine = EAD (SF64-style fonts). Tables: fonts 0xB4F60, sequences 0xB5460, sample banks 0xB5880;
  Audiobank 0xB58B0, Audiotable 0xE1AD0, Audioseq 0x4F3930.

- The N64 boot code checksums ROM 0x1000..0x101000 (audio bank + first samples live there): recompute the header
  CRC pair (6106 variant) or the game freezes at boot. The emulator core finds game settings (EEPROM 16K) by ROM MD5:
  `patch_core.py` must run for every new build (build_clean.sh does).
- Palettes: a descriptor's palette entry can be a block of N x 256-colour variants; some palettes are stored next to
  the image without a descriptor (aliases / `add_pals` override).

## Next
1. Text in pictures still mushy: big orange headings (fruit select, Yoshi select), tile font 0x561540, Japanese menu
   tiles (left as grid). HUD: smile meter, fruit frame. Story-page caption box.
2. Faces: Yoshi body parts, Shy Guys, enemies are 4x4-grid blobs (recognisable silhouettes, no eyes).
3. 38 palette-less images rendered as grey levels: check which are CI with a palette elsewhere.
4. Fault (crash screen) font in `main` is still the decomp-extracted one; white dots at tile corners are an
   emulator artefact (retail shows them too): try core options.
5. Listen to the audio (no dropouts verified only by the game running); music instruments are in tune by
   construction but octave errors of the pitch detector are possible.

## For the morning
- **Play**: https://andrewnakas.github.io/yoshistory-cleanroom/ (X jump, C tongue, Z egg, S sniff, Enter start).
- **Record** (optional): `D:/n64work/yoshistory/practice/practice_yoshi_call_and_response.wav` with the voice kit
  (98 short Yoshi sounds, 6 min). Then `python -m games.yoshistory.voices cut <recording.wav>` and
  `sh tools/build_clean.sh`.
- **Listen**: placeholder voices say made-up words ("Yoshi!", "Woo hoo!"); tell me if music sounds out of tune.
