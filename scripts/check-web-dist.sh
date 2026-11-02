#!/usr/bin/env bash
# Fail unless a built bundle is a publishable six-player release.
#
# Usage: ./scripts/check-web-dist.sh [web/dist]
set -euo pipefail

ROOT=$(cd "$(dirname "$0")/.." && pwd)
DIST=${1:-$ROOT/web/dist}

fail() {
	echo "check-web-dist: $*" >&2
	exit 1
}

[ -d "$DIST" ] || fail "missing $DIST"

required=(
	index.html net.js build-info.js xblast.js xblast.wasm xblast.data
	vendor/trystero/nostr/index.mjs vendor/trystero/core/index.mjs
	vendor/trystero/LICENSE.trystero vendor/trystero/LICENSE.noble
	COPYING THIRD_PARTY.md SOURCE.txt
	LICENSE/README.md LICENSE/LGPL-2.0.txt LICENSE/Bitstream-Vera.txt
)
for f in "${required[@]}"; do
	[ -f "$DIST/$f" ] || fail "missing $f"
done

[ ! -e "$DIST/turn.json" ] || fail "turn.json must not be published"
[ ! -e "$DIST/turn.example.json" ] || fail "example TURN config leaked into the build"

grep -q "target: 'release'" "$DIST/build-info.js" ||
	fail "not a release-target build"
grep -q 'maxPlayers: 6' "$DIST/build-info.js" ||
	fail "release must be the six-player build"

wasm_size=$(wc -c < "$DIST/xblast.wasm")
data_size=$(wc -c < "$DIST/xblast.data")
[ "$wasm_size" -gt 1000000 ] || fail "xblast.wasm looks empty ($wasm_size bytes)"
[ "$data_size" -gt 1000000 ] || fail "xblast.data looks empty ($data_size bytes)"
if [ "$data_size" -lt 10000000 ]; then
	fail "xblast.data is too small for a release with sounds ($data_size bytes)"
fi

echo "check-web-dist: ok ($DIST, wasm $wasm_size bytes, data $data_size bytes)"
