# Progress

Updated: 2026-10-31 (M1 in progress, release 0.1.0 tagged)

## Milestones

| Milestone | State |
|---|---|
| M0 — engine boots in browser | **done** (0.1.0) |
| M1 — single-player playable on web | **in progress** |
| M2 — 2-player P2P | not started |
| M3 — 6-player, chat, reconnect | not started |
| M4 — polish, assets, PWA | not started |

## M1 checklist

- [x] Audio: convert the unsigned 8-bit RAW files to S16 for SDL2_mixer
- [x] Audio: preload `data/sounds` and resume WebAudio on first input
- [ ] Audio: confirm it is audible in a real browser (needs a human ear)
- [x] Landing screen: explains the game and controls, Play gates the 20 MB load
- [x] On-screen key hints on both sides, driven by `control.cfg`, fading when idle;
      action captions, and a horizontal layout below the playfield on narrow screens
- [x] Esc leaves a match (player abort moved to Delete, with config migration)
- [x] Scripted playtest can assign a keyboard player and start a local game
- [ ] Controls: confirm arrows move and space drops a bomb in-game
- [ ] Level flow: win/lose → next level / scoreboard verified end to end
- [x] Settings persistence: engine config dir ⇄ `localStorage`
- [ ] Settings persistence: verify across a real page reload
- [ ] Reduce bundle size (data is ~20 MB with all sounds)

## How to run (dev)

```sh
./scripts/build-web.sh
python3 -m http.server -d web/dist 8123
# open http://localhost:8123/
```

Scripted checks:

```sh
python3 scripts/cdp_shot.py http://localhost:8123/index.html /tmp/shot.png 8
python3 scripts/playtest.py            # assigns Olaf, starts a game, moves/bombs
```

## Known issues / notes

- **Audio**: the build now defines `XBLAST_SOUND` (it was silently compiled
  out), `SUBSIZE` is 1024 for WebAudio, the default mode is `Waveout`, `Beep`
  is routed to the mixer, and `Module.SDL2.audioContext` is resumed on the
  first pointer/key event. Music tracks loop when selected; the default is
  still `None`. Needs a human ear check.
- **Player defaults**: left = W/A/S/D, Space bomb, Left Shift stop, Tab kick,
  Q abort; right = arrows, Return bomb, `/` abort, `.` cancel. Saved configs
  override these, and old left/abort bindings are migrated on load.
- **Single-player rounds end instantly** if there is only one player: the last
  player standing wins. Use a second keyboard player or a bot to actually play.
- **Fades are disabled on the web build** (`__EMSCRIPTEN__` in `sdl_pixmap.c`):
  they are a blocking `SDL_Delay` effect. Keep transitions instant until a
  non-blocking fade is implemented.
- **Quit needs `EXIT_RUNTIME=1`** so `Module.onExit` runs and the page shows the
  "Play again" overlay.
- `©` in the intro still renders as a missing-glyph box.
- Bundle: 3.5 MB wasm + 20 MB data (all sounds/music preloaded). Compress in M4.
- `web/net_stub.c` fails all socket calls; multiplayer is not wired up.

## Decisions

- Base: XBlast TNT 2.10.4 + Debian patches. Data: Debian GPL-2+ packages.
- **sdl12-compat is not used**: it dlopens `libSDL2.so`, which does not exist
  under Emscripten. The SDL backend is ported directly to SDL 2.
- SDL 2 ports: `SDL2`, `SDL2_image`, `SDL2_ttf`, `SDL2_mixer`, `SDL2_gfx`.
- Hosting target: static files, including GitHub Pages.
- Versioning: `0.MINOR.PATCH`; 0.1.0 = M0, 0.2.0 = M1.
- Attribution: every commit carries an `Assisted-by:` trailer.

## M1 next tasks

1. Human check: sound and in-game controls.
2. Verify settings survive a real reload (save on exit, restore in
   `onRuntimeInitialized`).
3. Win/lose → next level / scoreboard flow.
4. Trim the data bundle (exclude music unless selected, compress assets).
