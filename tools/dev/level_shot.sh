#!/bin/sh
# DEV: boot <rom> on the dev site, walk into level 1 and take two shots -> shots/<name>_sheet.png
rom=$1; name=$2
CDP_MUTE=1 python ports/ejs/cdp_shot.py /d/n64work/yoshistory/shots/$name --port 9471 --url "http://localhost:8471/index.html?rom=$rom" --gpu --script "24:Enter:0.2,32:Enter:0.2,44:Enter:0.2,48:x:0.2,56:x:0.2,60:x:0.2,68:x:0.2,76:x:0.2,84:shot,86:ArrowRight:3,90:shot" && python -m games.yoshistory.look /d/n64work/yoshistory/shots/$name 2
