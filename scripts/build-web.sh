#!/usr/bin/env bash
# Build the XBlast engine to WebAssembly with Emscripten.
#
# Usage:
#   ./scripts/build-web.sh                     # default: release (6 players)
#   ./scripts/build-web.sh --target lite-debug
#   ./scripts/build-web.sh --all               # every target (local only)
#   ./scripts/build-web.sh --list
#
# The default release writes web/dist (the test harness and Pages build use it).
# Every other target writes web/dist-<target>. These are local builds; CI should
# not publish the variant artifacts.
set -euo pipefail

ROOT=$(cd "$(dirname "$0")/.." && pwd)
TARGETS=(
	release 16p
	debug debug-16p
	lite lite-16p
	lite-debug lite-debug-16p
	small small-16p
	mini mini-16p
)

usage() {
	cat <<'EOF'
Build the XBlast engine to WebAssembly with Emscripten.

Usage:
  ./scripts/build-web.sh                     # default: release (6 players)
  ./scripts/build-web.sh --target lite-debug
  ./scripts/build-web.sh --all               # every target (local only)
  ./scripts/build-web.sh --list

The default release writes web/dist (the test harness and Pages build use it).
Every other target writes web/dist-<target>. These are local builds; CI should
not publish the variant artifacts.
EOF
}

has_target() {
	local t
	for t in "${TARGETS[@]}"; do
		[ "$t" = "$1" ] && return 0
	done
	return 1
}

profile_for() {
	case "$1" in
	release|16p) echo release ;;
	debug|debug-16p) echo debug ;;
	lite|lite-16p) echo lite ;;
	lite-debug|lite-debug-16p) echo lite-debug ;;
	small|small-16p) echo small ;;
	mini|mini-16p) echo mini ;;
	*) return 1 ;;
	esac
}

capacity_for() {
	case "$1" in
	16p|debug-16p|lite-16p|lite-debug-16p|small-16p|mini-16p) echo 16 ;;
	*) echo 6 ;;
	esac
}

out_for() {
	if [ "$1" = release ]; then
		echo "$ROOT/web/dist"
	else
		echo "$ROOT/web/dist-$1"
	fi
}

list_targets() {
	printf '%-14s %-4s %-11s %s\n' target cap profile output
	local t
	for t in "${TARGETS[@]}"; do
		printf '%-14s %-4s %-11s %s\n' "$t" "$(capacity_for "$t")" \
			"$(profile_for "$t")" "$(out_for "$t")"
	done
}

build_target() {
	local target=$1
	local profile cap out
	profile=$(profile_for "$target")
	cap=$(capacity_for "$target")
	out=$(out_for "$target")
	# Start from a clean directory: stale test pages, maps or a local turn.json
	# must never leak into a published bundle.
	rm -rf "$out"
	mkdir -p "$out"

	local core="
xblast.c util.c str_util.c intro.c introdat.c map.c sprite.c
color.c status.c player.c action.c bomb.c event.c image.c
shrink.c func.c info.c ini_file.c atom.c scramble.c
demo.c debug.c level.c random.c
game_local.c game_demo.c game_server.c game_client.c game.c
menu.c menu_player.c menu_level.c menu_control.c menu_game.c
menu_network.c menu_extras.c mi_tool.c mi_base.c
mi_button.c mi_color.c mi_combo.c mi_cyclic.c
mi_host.c mi_int.c mi_keysym.c mi_label.c mi_player.c
mi_string.c mi_tag.c mi_toggle.c mi_map.c mi_stat.c client.c
server.c network.c com.c browse.c com_to_server.c
com_listen.c com_to_client.c com_stream.c com_dg_client.c
com_dg_server.c com_dgram.c com_query.c com_browse.c
com_reply.c com_base.c net_socket.c net_tele.c
net_dgram.c central.c com_newgame.c com_to_central.c
com_from_central.c com_central.c user.c dat_rating.c
cfg_main.c cfg_level.c cfg_player.c cfg_game.c
cfg_control.c cfg_stat.c cfg_demo.c cfg_xblast.c
bot.c menu_edit.c chat.c version.c
"
	local sdl_backend="
sdl_common.c sdl_event.c sdl_atom.c sdl_config.c
sdl_msgbox.c sdl_init.c sdl_image.c sdl_text.c
sdl_tile.c sdl_sprite.c sdl_pixmap.c sdl_keysym.c
sdl_joystick.c sdl_sound.c
"
	local web_glue="net_web.c sdl_web.c"

	local sources=""
	local f
	for f in $core; do sources="$sources engine/$f"; done
	for f in $sdl_backend; do sources="$sources engine/$f"; done
	for f in $web_glue; do sources="$sources web/$f"; done

	local opt=(-O2)
	local debug=0
	local size=0
	local preload_sounds=1
	local smpf=0
	local mini=0
	local asserts=()
	case "$profile" in
	debug|lite-debug)
		opt=(-O0 -g)
		debug=1
		# SAFE_HEAP trips on a harmless unaligned access in the SDL/engine
		# path and aborts the page; assertions and the stack check are enough
		# for a usable local debug build.
		asserts=(-sASSERTIONS=2 -sSTACK_OVERFLOW_CHECK=2 -sGL_ASSERTIONS=1)
		;;
	lite)
		preload_sounds=0
		;;
	lite-debug)
		preload_sounds=0
		;;
	small)
		opt=(-Oz)
		size=1
		;;
	mini)
		mini=1
		;;
	esac
	case "$profile" in
	lite|lite-debug) preload_sounds=0 ;;
	esac
	[ "$cap" = 16 ] && smpf=1

	local cflags=("${opt[@]}" -std=gnu99 -DHAVE_CONFIG_H
		-I"$ROOT/build/gen" -I"$ROOT/web" -I"$ROOT/web/compat" -I"$ROOT/engine"
		-Wno-implicit-function-declaration -Wno-int-conversion
		-Wno-incompatible-pointer-types -Wno-pointer-sign
		-DXBLAST_SOUND)
	[ "$smpf" = 1 ] && cflags+=(-DSMPF)
	[ "$mini" = 1 ] && cflags+=(-DMINI_XBLAST)
	if [ "$debug" = 1 ]; then
		cflags+=(-DDEBUG -DDEBUG_GAME -DDEBUG_CLIENT -DDEBUG_SERVER \
			-DDEBUG_NETWORK -DDEBUG_ACTION)
	fi

	local ldflags=(-sUSE_SDL=2 -sUSE_SDL_IMAGE=2 -sUSE_SDL_TTF=2 -sUSE_SDL_MIXER=2
		-sUSE_SDL_GFX=2 "-sSDL2_IMAGE_FORMATS=['bmp','png','xpm','pnm']"
		-sALLOW_MEMORY_GROWTH=1 -sASYNCIFY -sASYNCIFY_STACK_SIZE=131072
		-sFORCE_FILESYSTEM=1 -sLZ4=1 -sEXIT_RUNTIME=1
		"-sEXPORTED_FUNCTIONS=['_main','_XBWeb_FlushConfig','_XBWeb_SendKey','_XBWeb_IsMenu','_XBWeb_LocalPlayerCount']"
		-sEXPORTED_RUNTIME_METHODS=['FS'] -sSTACK_SIZE=1048576)
	[ "$size" = 1 ] && ldflags+=(-sMALLOC=emmalloc)
	[ ${#asserts[@]} -gt 0 ] && ldflags+=("${asserts[@]}")
	ldflags+=(--preload-file "$ROOT/data/image@/data/image"
		--preload-file "$ROOT/data/level@/data/level"
		--preload-file "$ROOT/data/Vera.ttf@/Vera.ttf")
	[ "$preload_sounds" = 1 ] && ldflags+=(--preload-file "$ROOT/data/sounds@/data/sounds")

	echo "target: $target (${cap} players, $profile) -> $out"
	# shellcheck disable=SC2086
	emcc "${cflags[@]}" $sources "${ldflags[@]}" -o "$out/xblast.js"

	cat > "$out/build-info.js" <<EOF
globalThis.XB_BUILD = Object.freeze({
  target: '$target',
  profile: '$profile',
  maxPlayers: $cap,
  smpf: $([ "$smpf" = 1 ] && echo true || echo false),
  sound: true,
  soundData: $([ "$preload_sounds" = 1 ] && echo true || echo false),
  debug: $([ "$debug" = 1 ] && echo true || echo false)
});
EOF
	cp "$ROOT/web/index.html" "$out/index.html"
	cp "$ROOT/web/net.js" "$out/net.js"
	if [ -f "$ROOT/web/turn.js" ]; then cp "$ROOT/web/turn.js" "$out/turn.js"; fi
	if [ -f "$ROOT/web/turn.json" ]; then
		if [ "$target" = release ]; then
			echo "error: web/turn.json is local-only; the release target must not bundle TURN credentials." >&2
			echo "       use a local dev target (e.g. lite-debug) or remove web/turn.json." >&2
			exit 1
		fi
		cp "$ROOT/web/turn.json" "$out/turn.json"
	fi
	mkdir -p "$out/vendor"
	cp -R "$ROOT/web/vendor/." "$out/vendor/"

	# Licence notices and source offer travel with every build (GPL compliance).
	cp "$ROOT/COPYING" "$out/COPYING"
	cp "$ROOT/THIRD_PARTY.md" "$out/THIRD_PARTY.md"
	mkdir -p "$out/LICENSE"
	cp -R "$ROOT/LICENSE/." "$out/LICENSE/"
	mkdir -p "$out/docs"
	cp "$ROOT/docs/provenance.md" "$out/docs/provenance.md"
	local source_url=${XB_SOURCE_URL:-"(local build; repository URL not set)"}
	local commit
	commit=$(git -C "$ROOT" rev-parse --short=12 HEAD 2>/dev/null || echo unknown)
	{
		echo "xblast-web build $target ($cap players, $profile)"
		echo "commit: $commit"
		echo "source: $source_url"
		echo "built:  $(date -u '+%Y-%m-%dT%H:%M:%SZ')"
		echo
		echo "The complete corresponding source is this build's repository at the"
		echo "commit above. Licence texts are in COPYING, THIRD_PARTY.md and LICENSE/."
	} > "$out/SOURCE.txt"
	if [ -f "$out/turn.json" ]; then
		echo "note: this local build includes web/turn.json; do not publish it" >&2
	fi
	echo "built $out (target $target)"
}

ALL=0
TARGET=release
while [ $# -gt 0 ]; do
	case "$1" in
	--target)
		[ $# -ge 2 ] || { echo "--target needs a value" >&2; exit 2; }
		TARGET=$2
		shift 2
		;;
	--all)
		ALL=1
		shift
		;;
	--list)
		list_targets
		exit 0
		;;
	--help|-h)
		usage
		exit 0
		;;
	*)
		echo "unknown argument: $1" >&2
		usage >&2
		exit 2
		;;
	esac
done

if [ "$ALL" = 1 ] && [ "$TARGET" != release ]; then
	echo "--all and --target cannot be combined" >&2
	exit 2
fi
has_target "$TARGET" || { echo "unknown target: $TARGET" >&2; list_targets >&2; exit 2; }
command -v emcc >/dev/null 2>&1 || {
	echo "emcc not found; run 'asdf install' in $ROOT" >&2
	exit 1
}

if [ "$ALL" = 1 ]; then
	for target in "${TARGETS[@]}"; do
		build_target "$target"
	done
else
	build_target "$TARGET"
fi
