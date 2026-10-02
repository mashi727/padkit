#!/usr/bin/env bash
# Regenerate the screenshots used in README.md.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="$ROOT/docs/images"
SRC="$ROOT/skill/examples/release-process.spd"
mkdir -p "$OUT"
for mode in standard align-depth; do
  flag=""; [ "$mode" = align-depth ] && flag="--align-depth"
  uv run --project "$ROOT" padkit svg $flag "$SRC" -o "$OUT/release-process.$mode.svg"
  uv run --project "$ROOT" python -c "import cairosvg,sys; cairosvg.svg2png(url=sys.argv[1], write_to=sys.argv[2], scale=2, background_color='white')" \
    "$OUT/release-process.$mode.svg" "$OUT/release-process.$mode.png"
  rm "$OUT/release-process.$mode.svg"
done
echo "wrote $OUT"
