#!/usr/bin/env bash
# Build the standalone socket.h WebRTC harness (not shipped with the game).
set -euo pipefail

ROOT=$(cd "$(dirname "$0")/.." && pwd)
OUT="$ROOT/web/dist"
mkdir -p "$OUT"

emcc \
	-std=gnu99 -O1 -DHAVE_CONFIG_H \
	-I"$ROOT/build/gen" -I"$ROOT/web" -I"$ROOT/engine" \
	"$ROOT/web/net_web.c" "$ROOT/web/net_test.c" \
	-sALLOW_MEMORY_GROWTH=1 \
	-sASYNCIFY \
	-sASYNCIFY_STACK_SIZE=131072 \
	-sSTACK_SIZE=1048576 \
	"-sEXPORTED_FUNCTIONS=['_xb_test_run','_malloc','_free']" \
	"-sEXPORTED_RUNTIME_METHODS=['stringToUTF8','lengthBytesUTF8','UTF8ToString']" \
	-o "$OUT/nettest.js"
cp "$ROOT/web/nettest.html" "$OUT/nettest.html"
echo "built $OUT/nettest.js"
