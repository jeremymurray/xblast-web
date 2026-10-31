#!/usr/bin/env bash
# Build the XBlast engine to WebAssembly with Emscripten.
set -euo pipefail

ROOT=$(cd "$(dirname "$0")/.." && pwd)
BUILD="$ROOT/build"
OUT="$ROOT/web/dist"
mkdir -p "$OUT"

if ! command -v emcc >/dev/null 2>&1; then
	echo "emcc not found; run 'asdf install' in $ROOT" >&2
	exit 1
fi

CORE="
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

SDL_BACKEND="
sdl_common.c sdl_event.c sdl_atom.c sdl_config.c
sdl_msgbox.c sdl_init.c sdl_image.c sdl_text.c
sdl_tile.c sdl_sprite.c sdl_pixmap.c sdl_keysym.c
sdl_joystick.c sdl_sound.c
"

WEB_GLUE="
net_stub.c sdl_web.c
"

SOURCES=""
for f in $CORE; do SOURCES="$SOURCES engine/$f"; done
for f in $SDL_BACKEND; do SOURCES="$SOURCES engine/$f"; done
for f in $WEB_GLUE; do SOURCES="$SOURCES web/$f"; done

CFLAGS=(
	-std=gnu99 -O2
	-DHAVE_CONFIG_H
	-I"$ROOT/build/gen"
	-I"$ROOT/web/compat"
	-I"$ROOT/engine"
	-Wno-implicit-function-declaration
	-Wno-int-conversion
	-Wno-incompatible-pointer-types
	-Wno-pointer-sign
)

LDFLAGS=(
	-sUSE_SDL=2
	-sUSE_SDL_IMAGE=2
	-sUSE_SDL_TTF=2
	-sUSE_SDL_MIXER=2
	-sUSE_SDL_GFX=2
	"-sSDL2_IMAGE_FORMATS=['bmp','png','xpm','pnm']"
	-sALLOW_MEMORY_GROWTH=1
	-sASYNCIFY
	-sASYNCIFY_STACK_SIZE=131072
	-sFORCE_FILESYSTEM=1
	-sEXIT_RUNTIME=1
	-sEXPORTED_RUNTIME_METHODS=['FS']
	-sSTACK_SIZE=1048576
	--preload-file "$ROOT/data/image@/data/image"
	--preload-file "$ROOT/data/level@/data/level"
	--preload-file "$ROOT/data/sounds@/data/sounds"
	--preload-file "$ROOT/data/Vera.ttf@/Vera.ttf"
)

# shellcheck disable=SC2086
emcc "${CFLAGS[@]}" $SOURCES "${LDFLAGS[@]}" -o "$OUT/xblast.js"

echo "built $OUT/xblast.js"
cp "$ROOT/web/index.html" "$OUT/index.html"
