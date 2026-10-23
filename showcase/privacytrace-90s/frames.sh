#!/usr/bin/env bash
# Regenerate the 10 fps frame bank that film-showcase.html replays on a canvas.
#
# The 276 JPEGs are derived from assets/recording-browser.mp4 and stay out of the
# repository; run this once after cloning before re-rendering the film.
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"

ffmpeg -hide_banner -loglevel error -y \
  -i assets/recording-browser.mp4 \
  -vf fps=10 -q:v 3 assets/rec/f_%04d.jpg

printf 'frames: %s\n' "$(ls assets/rec | wc -l | tr -d ' ')"
