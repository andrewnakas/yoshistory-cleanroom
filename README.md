# Yoshi's Story: clean-room web build

Play: https://andrewnakas.github.io/yoshistory-cleanroom/

The game's program runs unchanged (code, level layouts, geometry, text, note sequences). **Every picture and sound
is regenerated**: nothing of the original pixels or samples is shipped.

- Images (sprites, tiles, textures, palettes, title pages): rebuilt from a coarse 4x4 colour grid per frame plus the
  1-bit outline (2-bit level for intensity images). `games/yoshistory/extract_spec.py` -> `spec/`, `generate.py`.
- Audio: every sample resynthesised from a coarse spectral outline, length, loop points and median pitch; our own
  ADPCM codebooks. `games/yoshistory/audio.py`.
- `games/yoshistory/taint.py` checks that no regenerated item still equals the original (must print `0 failing`).
- Runs in the browser with EmulatorJS (mupen64plus-next core); see `ports/ejs` and the site's `THIRD_PARTY.md`.

No ROM is included or needed to play. Building from source needs your own copy of the US ROM (dirty-room scripts
read it; clean outputs come from `spec/` + code). Work in progress: see `STATUS.md`.

Keys: arrows move, X = A (jump / flutter), C = B (tongue), Z = Z (egg / ground pound), S = R (sniff), Enter = Start.
Gamepads work.
