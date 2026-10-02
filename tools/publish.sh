#!/bin/sh
# Publish the current clean build (after tools/build_clean.sh printed "taint: 0 failing").  tools/publish.sh "message"
set -e
W=/d/n64work/yoshistory
python -m games.yoshistory.taint $W/baserom.us.z64 $W/build/clean.z64 | tail -1 | grep -q "taint: 0 failing" || { echo "taint not clean"; exit 1; }
python ports/ejs/make_site.py $W/build/clean.z64 $W/devsite $W/site
cd $W/site && git add -A >/dev/null 2>&1 && git -c user.name=andre -c user.email=treesixtyweather@gmail.com commit -q -m "$1

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>" && git push -q -f origin gh-pages 2>&1 | grep -v "^remote:" || true
echo "site pushed"
