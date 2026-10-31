# Progress

Updated: 2026-10-31 (M0 complete)

## Milestones

| Milestone | State |
|---|---|
| M0 — engine boots in browser | **done** |
| M1 — single-player playable on web | next |
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
- [x] Intro, main menu and local-game screens render
- [x] Keyboard input works (Space dismisses intro, Tab moves menu focus)
- [x] Local game starts and runs (level intro → maze, bombs, HUD)
- [x] Quit shows a "Play again" overlay instead of a dead black canvas
- [x] Transitions no longer block the browser (fades skipped on web)
- [x] Screenshot harness without extra dependencies (`scripts/cdp_shot.py`)
- [x] Remove debug probes

Evidence: `docs/screenshots/m0-menu.png`, `docs/screenshots/m0-game.png`.

## How to run (dev)

```sh
./scripts/build-web.sh
python3 -m http.server -d web/dist 8123
# open http://localhost:8123/
```

Headless screenshot (real time, no virtual-time quirks):

```sh
python3 scripts/cdp_shot.py http://localhost:8123/index.html /tmp/shot.png 8
# with keys:  ... /tmp/shot.png 8 "space:0,space:3"
```

## Known issues / notes

- **Audio not wired**: `data/sounds` (11 MB) is not preloaded and SDL_mixer is
  asked for `AUDIO_U8`, which SDL2_mixer rejects. Convert U8 → S16 and gate on a
  user gesture before M1.
- **Mouse in menus** works (verified by clicking Options and Quit). Menu items
  only fire when they are the focused item; the button handler sets focus from
  the click position, so a normal click is enough.
- **Fades are disabled on the web build** (`GUI_InitFade`/`GUI_DoFade` return
  immediately under `__EMSCRIPTEN__`). They are a blocking `SDL_Delay` effect
  that stalls the Asyncify loop and made transitions feel very slow. Menus and
  levels still redraw normally; only the wipe/black-hold is gone.
- **Quit needs `EXIT_RUNTIME=1`**: with `EXIT_RUNTIME=0`, Emscripten keeps the
  runtime alive and never calls `Module.onExit`, leaving the last frame on
  screen. The page now shows a "Play again" overlay on exit.
- `©` in the intro renders as a missing-glyph box. Check UTF-8/Latin-1 handling
  in `sdl_text.c` later.
- Only `data/image`, `data/level` and `Vera.ttf` are packed into `xblast.data`.
- `web/net_stub.c` fails all socket calls; multiplayer is not wired up.
- Data package is 9.2 MB and uncompressed-ish; revisit asset compression in M4.

## Decisions

- Base: XBlast TNT 2.10.4 + Debian patches. Data: Debian GPL-2+ packages.
- **sdl12-compat is not used**: it dlopens `libSDL2.so`, which does not exist
  under Emscripten. We port the SDL backend directly to SDL 2 instead.
- SDL 2 ports used: `SDL2`, `SDL2_image`, `SDL2_ttf`, `SDL2_mixer`, `SDL2_gfx`.
- Hosting target: static files, including GitHub Pages (see AGENTS.md).
- Attribution: every commit carries an `Assisted-by:` trailer for the model.

## M1 next tasks

1. Fix audio: preload `data/sounds`, convert U8 raw samples to S16, unlock
   WebAudio on first input.
2. Player controls: assign keyboard players in Setup, verify movement/bombs.
3. Level flow: win/lose, next level, score screen.
4. Config persistence: keep settings in `localStorage` (the engine writes
   `config/*.cfg` to MEMFS and loses them on reload).
5. Replace the dev preload list with a build-time asset manifest.
