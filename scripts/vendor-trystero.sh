#!/usr/bin/env bash
# Vendor the Trystero P2P stack so the static site needs no npm or CDN.
set -euo pipefail

ROOT=$(cd "$(dirname "$0")/.." && pwd)
DEST="$ROOT/web/vendor/trystero"
TMP=$(mktemp -d "${TMPDIR:-/tmp}/xblast-trystero.XXXXXX")
trap 'rm -rf "$TMP"' EXIT

NOSTR_URL="https://registry.npmjs.org/@trystero-p2p/nostr/-/nostr-0.26.0.tgz"
NOSTR_SHA="8f0cd23847de6a1f29560a61233dc58d3ff73121783ddd31d7fcbca7c4e559a1"
CORE_URL="https://registry.npmjs.org/@trystero-p2p/core/-/core-0.26.0.tgz"
CORE_SHA="e74c5cbcd83c63bbfb08418a986fe08b98cb19a3e0002248586a91438c9c47d5"
NOBLE_URL="https://registry.npmjs.org/@noble/secp256k1/-/secp256k1-3.2.0.tgz"
NOBLE_SHA="2722e0b18b696cf6d3463ab10365f97f617fb651e85a7eeed8f12121a1077018"

fetch() {
	local name=$1 url=$2 sha=$3
	curl -fsSL "$url" -o "$TMP/$name.tgz"
	echo "$sha  $TMP/$name.tgz" | shasum -a 256 -c -
	mkdir -p "$TMP/$name"
	tar -xzf "$TMP/$name.tgz" -C "$TMP/$name"
}

fetch nostr "$NOSTR_URL" "$NOSTR_SHA"
fetch core "$CORE_URL" "$CORE_SHA"
fetch noble "$NOBLE_URL" "$NOBLE_SHA"

rm -rf "$DEST/nostr" "$DEST/core" "$DEST/noble"
mkdir -p "$DEST/nostr" "$DEST/core" "$DEST/noble"

cp "$TMP/nostr/package/dist/index.mjs" "$DEST/nostr/index.mjs"
for f in "$TMP"/core/package/dist/*.mjs; do
	case "$f" in
	*.map) continue ;;
	esac
	cp "$f" "$DEST/core/"
done
cp "$TMP/noble/package/index.js" "$DEST/noble/index.js"

cp "$TMP/core/package/LICENSE" "$DEST/LICENSE.trystero"
cp "$TMP/noble/package/LICENSE" "$DEST/LICENSE.noble"

cat >"$DEST/README.md" <<EOF
# Vendored Trystero P2P stack

These files are copied verbatim from npm tarballs so the static site can use
peer-to-peer signalling without npm at build time or a CDN at runtime.

| Package | Version | Licence |
|---|---|---|
| \`@trystero-p2p/nostr\` | 0.26.0 | MIT |
| \`@trystero-p2p/core\` | 0.26.0 | MIT |
| \`@noble/secp256k1\` | 3.2.0 | MIT |

Source tarballs (with verified sha256):

- \`$NOSTR_URL\`
  - \`$NOSTR_SHA\`
- \`$CORE_URL\`
  - \`$CORE_SHA\`
- \`$NOBLE_URL\`
  - \`$NOBLE_SHA\`

The combined work is distributed under GPL-2.0-or-later; the vendored
packages keep their MIT licences in \`LICENSE.trystero\` and \`LICENSE.noble\`.

Regenerate with:

\`\`\`sh
./scripts/vendor-trystero.sh
\`\`\`
EOF

echo "vendored Trystero into $DEST"
