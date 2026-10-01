# Yoshi's Story clean room: status

## BLOCKED: ROM
- Needed: **Yoshi's Story (USA) (En,Ja)**, .z64 (big-endian), 16 MB.
  sha1 `b13072fef6c6df48c07d8822c01e5bc59036f6da`, md5 `586a092e22604840973b82dfaceac77a` (the decomp's `us` target).
- Looked for `*yoshi*` in `C:/Users/andre/Downloads` and `D:/` (root): not there (last check 2026-10-01, loop 1).
  Re-checked every 20 minutes. Drop the zip in either place; nothing else is needed.

## Decisions (log)
- 2026-10-01 loop 1. Decomp cloned LF, depth 1: `D:/n64work/yoshistory/pristine` (decompals/yoshis-story, 5 MB).
- **Web route = 3: clean ROM + WASM N64 emulator** (EmulatorJS 4.2.3 + mupen64plus_next, as Conker / DK64 / BK).
  Why: no PC port and no recomp port exists; the decomp splits only the `main` code segment (IDO 7.1/5.3, mostly asm)
  and keeps ROM 0xB58B0..0x1000000 as a single `unkbin` blob, so there is nothing to compile for the web.
- **Clean ROM = the game's code (kept fact) + regenerated assets**, rebuilt by our own ROM tool like Conker/DK64
  (`games/<g>/romtool.py` there). The decomp does not split any asset: every texture, sprite, background, font and
  sample lives in `unkbin` and has to be found by our own scanners once the ROM is here.
- `ports/ejs` copied from the Conker session and adapted: page (keys: X = A jump, C = B tongue, Z = Z, S = R, Enter),
  `make_site.py` (refuses the retail sha1, writes `yoshistory.z64`), `patch_core.py` (core ROM-DB slot
  "Yoshi's Story (U) (M2) [b1]" -> our MD5, so the clean ROM gets EEPROM 16 KB + rumble).
  EmulatorJS runtime to reuse: `D:/n64work/conker/devsite/data` (+ `LICENSE`).
- Disk: 36 GB free on D: at start (limit: stop heavy work under 10 GB).

## Next (as soon as the ROM is there)
1. Unzip to `D:/n64work/yoshistory/baserom.us.z64`, check sha1; retail boot in headless Edge (dev only).
2. Map `unkbin`: DMA/file tables referenced from `main`, compression, overlays (`loadfragment2`), audio bank/table/seq.
3. Identity rebuild (sha1 match), then texture/sprite/background scan -> spec (format, size, 4x4 grid, 2-bit alpha).
4. Generate, taint (0 failing), boot, publish; then readable text, faces/sprites, pictures; placeholder voices + practice pack.

## For the morning
- Put the ROM zip in Downloads (see top) if this still says BLOCKED.
