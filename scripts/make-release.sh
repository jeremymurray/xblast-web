#!/usr/bin/env bash
# Assemble a release: source archive, web bundle, checksums.
#
# Usage:
#   ./scripts/build-web.sh                 # build web/dist first (release target)
#   ./scripts/make-release.sh 0.4.0
#
# Writes build/release/. The source archive is `git archive` of HEAD, so the
# exact tree that produced the bundle travels with it (GPL corresponding
# source). Set XB_SOURCE_URL when building so SOURCE.txt in web/dist names the
# public repository, e.g.
#   XB_SOURCE_URL=https://github.com/OWNER/xblast-web ./scripts/build-web.sh
set -euo pipefail

ROOT=$(cd "$(dirname "$0")/.." && pwd)
DIST=${XB_DIST:-$ROOT/web/dist}
OUT=$ROOT/build/release
VERSION=${1:-}

usage() {
	cat <<'EOF'
Usage: ./scripts/make-release.sh VERSION

VERSION must be the annotated tag on HEAD, e.g. 0.4.0. Build web/dist with
./scripts/build-web.sh (release target) before running this.
EOF
}

case "$VERSION" in
[0-9]*.[0-9]*.[0-9]*) ;;
*) usage >&2; exit 2 ;;
esac

[ -d "$DIST" ] || { echo "missing $DIST; run ./scripts/build-web.sh" >&2; exit 1; }
"$ROOT/scripts/check-web-dist.sh" "$DIST"
if grep -q 'source: (local build' "$DIST/SOURCE.txt"; then
	echo "refusing: SOURCE.txt has no public source URL." >&2
	echo "rebuild with XB_SOURCE_URL=<repository-url> ./scripts/build-web.sh --target release" >&2
	exit 1
fi

tag=$(git -C "$ROOT" describe --tags --exact-match HEAD 2>/dev/null || true)
if [ "$tag" != "$VERSION" ]; then
	echo "warning: HEAD is not tagged $VERSION (tag: ${tag:-none}); packaging anyway" >&2
fi

rm -rf "$OUT"
mkdir -p "$OUT"
SRC="xblast-web-$VERSION-source.tar.gz"
WEB="xblast-web-$VERSION-web.zip"
git -C "$ROOT" archive --format=tar.gz --prefix="xblast-web-$VERSION/" \
	-o "$OUT/$SRC" HEAD
(cd "$DIST" && zip -q -r "$OUT/$WEB" .)
(
	cd "$OUT"
	if command -v sha256sum >/dev/null 2>&1; then
		sha256sum "$SRC" "$WEB"
	else
		shasum -a 256 "$SRC" "$WEB"
	fi
) > "$OUT/SHA256SUMS"

echo "release $VERSION:"
ls -lh "$OUT"
echo
cat "$OUT/SHA256SUMS"
