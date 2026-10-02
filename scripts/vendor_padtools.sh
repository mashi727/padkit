#!/usr/bin/env bash
# Vendor padtools_ts at a pinned commit into src/padkit/_vendor/padtools_ts.
# Only the runtime subset is committed (dist + manifests + LICENSE); node_modules
# is installed later by `padkit setup` from the pinned package-lock.json.
set -euo pipefail
COMMIT="${1:?usage: vendor_padtools.sh <commit-sha>}"
REPO="steelpipe75/padtools_ts"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DEST="$ROOT/src/padkit/_vendor/padtools_ts"
WORK="$ROOT/.vendor-work"; rm -rf "$WORK"; mkdir -p "$WORK"
trap 'rm -rf "$WORK"' EXIT

curl -sSL -o "$WORK/pt.tar.gz" "https://codeload.github.com/$REPO/tar.gz/$COMMIT"
SHA256="$(shasum -a 256 "$WORK/pt.tar.gz" | cut -d' ' -f1)"
mkdir "$WORK/src" && tar xzf "$WORK/pt.tar.gz" -C "$WORK/src" --strip-components=1

rm -rf "$DEST" && mkdir -p "$DEST"
cp -R "$WORK/src/dist" "$DEST/dist"
cp "$WORK/src/package.json" "$WORK/src/package-lock.json" "$WORK/src/LICENSE" "$WORK/src/README.md" "$DEST/"
# The grammar is the normative SPD definition; keep it next to the engine for reference.
cp "$WORK/src/src/spd/langium/spd.langium" "$DEST/spd.langium"

# Local changes to the engine live as patches, so that upgrading the pin is
# "re-vendor and re-apply" rather than hand-merging edited files.
PATCHES=()
for pf in "$ROOT"/patches/*.patch; do
  [ -e "$pf" ] || continue
  patch -p1 -d "$DEST" --forward --quiet < "$pf"
  PATCHES+=("\"$(basename "$pf")\"")
done
PATCH_LIST="$(IFS=,; echo "${PATCHES[*]}")"

cat > "$DEST/PIN.json" <<JSON
{
  "repo": "$REPO",
  "commit": "$COMMIT",
  "tarball_sha256": "$SHA256",
  "patches": [$PATCH_LIST],
  "vendored_at": "$(date -u +%Y-%m-%d)"
}
JSON
echo "vendored $REPO@$COMMIT -> $DEST"
