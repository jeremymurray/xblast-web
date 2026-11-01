# Progress

Updated: 2026-10-31 (M2 done, release 0.3.0)

## Milestones

| Milestone | State |
|---|---|
| M0 — engine boots in browser | **done** (0.1.0) |
| M1 — single-player playable on web | **done** (0.2.0) |
| M2 — 2-player P2P | **done** (0.3.0) |
| M3 — 6-player, chat, reconnect | not started |
| M4 — polish, assets, PWA | not started |

## M2 checklist

- [x] Vendor Trystero 0.26.0 (nostr + core) and `@noble/secp256k1`, no npm at build time
- [x] Transport: one Trystero room per page, two negotiated DataChannels per peer
- [x] Channels: reliable-ordered `xb.ctl` for control/level/chat, unreliable-unordered
      `xb.act` for per-frame actions
- [x] Room lobby on the landing page: room code, New, Host, Join, Copy, Leave
- [x] Engine entry hooks: `XBWeb_ServerListen` / `XBWeb_ClientConnect` behind `socket.h`
- [x] Socket shim (`web/net_web.c`) over the JS transport, replacing `net_stub.c`
- [x] Wait screens show `Room <code> - waiting for players` /
      `Room <code> - waiting for the host to start`
- [x] Two-browser test (`scripts/netplaytest.py`) reaches a match and exchanges
      control and action traffic
- [x] Docs, known issues and 0.3.0 release notes

## Release notes — 0.3.0

Two players can play a real match in two browsers, with no game server. One page hosts,
the other joins with the same room code; signalling runs over public Nostr relays via
vendored Trystero, and game traffic goes browser-to-browser over WebRTC. The web main
menu is now Solo, Multiplayer Lobby, Options, Quit; the old IRC/central-server screens
are gone from the web build. Single-player is unchanged from 0.2.0.

## How to run (dev)

```sh
./scripts/build-web.sh
python3 -m http.server -d web/dist 8123
# open http://localhost:8123/
```

Solo: click Play. Multiplayer: open a second browser (or a second profile/window),
type the same room code in both, click **Host** in one and **Join** in the other, then
start a network game from the menu. The room code is the game/room identifier.

Scripted checks:

```sh
python3 scripts/cdp_shot.py http://localhost:8123/index.html /tmp/shot.png 8
python3 scripts/playtest.py            # solo: assigns Olaf, starts a game, moves/bombs
python3 scripts/netplaytest.py         # two headless browsers: host/join, then a match
```

`scripts/netplaytest.py` needs internet access to public Nostr relays (skip with
`XB_TEST_OFFLINE=1`) and starts Chromium with
`--disable-features=WebRtcHideLocalIpsWithMdns` so both local pages can connect.

## Known issues / notes

- **No TURN.** Some NAT pairs cannot connect. Public relays are signalling only; they do
  not relay game traffic.
- **Host tab backgrounding can stall the match**: browsers throttle background timers and
  the engine loop is timer-driven. Keep the host tab in the foreground.
- **No reconnect, host migration or chat UI.** Closing the host tab ends the match; a
  dropped guest is gone.
- **Only two players (one host, one guest) have been verified**; 6-player is M3.
- **No per-round desync hash.** Divergence would be silent; M3 adds a state hash.
- **The room persists after a match.** Leaving a match returns to the menu but stays in
  the room; use **Leave** or *Multiplayer Lobby* on the main menu, which reloads.
- **Netplay test needs internet** and the mDNS flag (see above).
- **Audio** needs a human ear check; the mixer is wired and WebAudio unlocks on first input.
- **Fades are disabled on the web build** (`__EMSCRIPTEN__` in `sdl_pixmap.c`): they are a
  blocking `SDL_Delay` effect. Keep transitions instant until a non-blocking fade exists.
- **Quit needs `EXIT_RUNTIME=1`** so `Module.onExit` runs and the page shows "Play again".
- `©` in the intro still renders as a missing-glyph box.
- Bundle: 3.5 MB wasm + 15 MB LZ4 data (all sounds/music preloaded).

## Decisions

- Base: XBlast TNT 2.10.4 + Debian patches. Data: Debian GPL-2+ packages.
- **sdl12-compat is not used**: it dlopens `libSDL2.so`, which does not exist under
  Emscripten. The SDL backend is ported directly to SDL 2.
- SDL 2 ports: `SDL2`, `SDL2_image`, `SDL2_ttf`, `SDL2_mixer`, `SDL2_gfx`.
- Hosting target: static files, including GitHub Pages; no backend.
- Networking: WebRTC star, host is the authoritative game server.
- Signalling: vendored Trystero 0.26.0 (MIT) over public Nostr relays; no npm at build
  time and no CDN at runtime.
- Versioning: `0.MINOR.PATCH`; 0.1.0 = M0, 0.2.0 = M1, 0.3.0 = M2.
- Attribution: every commit carries an `Assisted-by:` trailer.

## Next tasks (M3)

1. Six players: accept multiple guests, player slots in the lobby and game setup.
2. Chat UI over the reliable channel.
3. Reconnect and host migration; handle host tab backgrounding or warn about it.
4. Per-round state hash to detect and report desync.
5. TURN: optional relay fallback for restrictive NATs.
