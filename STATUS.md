# Yoshi's Story clean room: status

**Not published yet.** ROM is on disk (`D:/n64work/yoshistory/baserom.us.z64`, sha1 ok). Clean ROM boots and level 1
plays in headless Edge with regenerated graphics. Audio is generated but hangs the game at boot (being bisected).

## What works (2026-10-01, loop 2)
- Route: clean ROM + EmulatorJS (mupen64plus_next). Dev site `D:/n64work/yoshistory/devsite` (port 8471; 8093 is
  used by another session).
- `games/yoshistory`: `smsr.py` (CMPR/SMSR00 codec), `classify.py` + `extract_spec.py` (dirty) -> `spec/archive.*`,
  `generate.py` (clean ROM), `texscan.py` (overlay textures), `audio.py` (soundfonts / samples).
- Regenerated: 1495 images + 707 palettes (archive sprites/tiles, Yoshi body parts, 375 overlay textures, the three
  title pages). All smooth 4x4-grid renders; 25 files that outgrew their slot live in the free end of the ROM.
- Audio spec: 62 fonts, 445 samples (355 s), sequences kept. Samples resynthesised (pitched ones as steady partials
  that loop on whole periods), own codebooks and loop states.

## Decisions (log)
- Web route = 3 (clean ROM + WASM emulator): no PC port, decomp splits only `main`; assets found by our scanners.
- Compressed files are packed 4-aligned and the header size field is ~12 bytes larger than the stored file: a slot
  ends where the next file starts (zeroing "16 + comp" bytes clipped the next file = scrambled levels; fixed).
- Oversized regenerated files move to the 0xFF padding after 0xEBDA70 and their descriptors are re-pointed.
- Audio engine = EAD (SF64-style fonts). Tables: fonts 0xB4F60, sequences 0xB5460, sample banks 0xB5880;
  Audiobank 0xB58B0, Audiotable 0xE1AD0, Audioseq 0x4F3930.

## Next
1. Audio hang (bisect: gaps / data / books / loops with `tools/dev/audio_test.py`).
2. Taint scan for the ROM (every spec item differs from retail, list kept regions), then publish.
3. Readability: title logo + (c) line, menu words (Story Mode, Trial Mode, Options, Practice), big red font
   (tile set 0x561540), "PUSH START", fruit-select title. Faces: Yoshi parts, Shy Guys, HUD smile meter.
4. Palette-less CI sprites (57 "nopal" images rendered as grey levels) need their palettes found.
5. Fault font in `main`, any textures in main data. White dots at tile corners are an emulator artefact (also retail).
6. Placeholder voices (Piper) for Yoshi's vocal samples + practice pack in `D:/n64work/yoshistory/practice/`.

## For the morning
- Nothing to record yet; practice pack not built.
