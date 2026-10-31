# Progress

Updated: 2026-10-31 (M0 build spike)

## Milestones

| Milestone | State |
|---|---|
| M0 — engine boots in browser | **in progress** |
| M1 — single-player playable on web | not started |
| M2 — 2-player P2P | not started |
| M3 — 6-player, chat, reconnect | not started |
| M4 — polish, assets, PWA | not started |

## M0 checklist

- [x] Pin Emscripten via `asdf` (`.tool-versions`, emsdk 6.0.13)
- [x] Vendor XBlast TNT 2.10.4 + Debian patches (`engine/`)
- [x] Add GPL-2+ data from Debian packages (`data/`, `LICENSE/data/`)
- [x] Replace SDL 1.2 with SDL 2 shim + Emscripten ports
      (`web/compat/`, `web/sdl_web.c`, patched `engine/sdl_*.c`)
- [x] Build to wasm (`scripts/build-web.sh`, 3.5 MB wasm, 9.2 MB data)
- [x] Boot in headless Chrome: config load, `SDL_Init`, 960x736 window,
      first present, all init steps through `tiles ready`
- [ ] Capture a screenshot proving the menu renders
- [ ] Keyboard/mouse input reaches the engine
- [ ] Sound (SDL_mixer U8 → S16 conversion, WebAudio autoplay unlock)
- [ ] Asyncify vs worker loop decision; remove debug instrumentation
- [ ] M0 write-up and merge to `main`

## How to run (dev)

```sh
./scripts/build-web.sh
python3 -m http.server -d web/dist 8123
# open http://localhost:8123/
```

Headless check used during M0:

```sh
"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" \
  --headless=new --disable-gpu --no-sandbox \
  --virtual-time-budget=60000 --dump-dom --enable-logging=stderr \
  http://localhost:8123/index.html
```

## Known issues / notes

- `video_bpp` reads 0 because `SDL_GetVideoInfo()` is called before
  `SDL_SetVideoMode()`; harmless, the shim ignores bpp (always 32-bit ARGB).
- The game loop yields with `emscripten_sleep(16)` in `SelectSockets`, so
  Chrome's virtual-time budget never expires while it sleeps. Prefer a real-time
  CDP screenshot harness for evidence (or reduce idle sleep during tests).
- Sounds/music are not preloaded yet (`data/sounds` 11 MB); only image + level
  + font are packed.
- `web/net_stub.c` fails all socket calls; multiplayer is not wired up.
- Debug `fprintf(stderr, "xb: ...")` probes in `engine/sdl_init.c` and
  `web/sdl_web.c` must be removed or gated before M0 is done.

## Decisions

- Base: XBlast TNT 2.10.4 + Debian patches. Data: Debian GPL-2+ packages.
- **sdl12-compat is not used**: it dlopens `libSDL2.so`, which does not exist
  under Emscripten. We port the SDL backend directly to SDL 2 instead.
- SDL 2 ports used: `SDL2`, `SDL2_image`, `SDL2_ttf`, `SDL2_mixer`, `SDL2_gfx`.
- Hosting target: static files, including GitHub Pages (see AGENTS.md).
- Attribution: every commit carries an `Assisted-by:` trailer for the model.
