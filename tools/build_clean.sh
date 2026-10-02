#!/bin/sh
# Clean ROM -> taint -> dev site (core settings entry follows the ROM's MD5).  tools/build_clean.sh
set -e
W=/d/n64work/yoshistory
python -m games.yoshistory.generate $W/baserom.us.z64 $W/build/clean.z64 | grep -v "  audio "
python -m games.yoshistory.taint $W/baserom.us.z64 $W/build/clean.z64 | tail -1 || true
cp $W/build/clean.z64 $W/devsite/clean.z64
python ports/ejs/patch_core.py $W/build/clean.z64 $W/cores_orig $W/devsite/data/cores
