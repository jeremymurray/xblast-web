# Progress

Updated: 2026-11-01 (M2 done, 0.3.0; M3 reconnect/replace and six-player slices done, 0.3.1)

## Milestones

| Milestone | State |
|---|---|
| M0 — engine boots in browser | **done** (0.1.0) |
| M1 — single-player playable on web | **done** (0.2.0) |
| M2 — 2-player P2P | **done** (0.3.0) |
| M3 — 6-player, chat, reconnect | in progress (reconnect/replace and six players done, 0.3.1) |
| M4 — polish, assets, PWA, optional 16-player (`SMPF`) build | not started |

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

Local playtest: Chrome and Firefox on the same machine played a match together.

## M3 reconnect/replace (0.3.1)

- [x] Stable per-tab client id in hello v2; guest ids survive a reload via `sessionStorage`
- [x] Host replaces an old peer with the same id; the old stream EOFs and the engine frees the slot
- [x] Host stage/status (`setup`/`listening`/`match`/`idle`); mid-match refresh fails clearly
- [x] Lobby remembers the last room and offers Rejoin/Re-host after a reload
- [x] Tests: JS replacement, end-to-end refresh/rejoin, mid-match refusal
- [ ] Mid-match resume/replay (later; needs engine state snapshot)

## Release notes — 0.3.1

A guest who refreshes before the match starts can rejoin the same room; the host replaces the
stale client instead of keeping a dead slot. A refresh after the match has started now fails
quickly with a clear "host is already in a match / not accepting players" message instead of
hanging. Host migration and mid-match resume remain future work.

## M3 six players (multi-guest)

- [x] Host accepts five guests and refuses a sixth with "The room is full (6 players)."
      (`CTL_REJECT`); a rejoin by an existing client id still replaces while the room is full
- [x] A host in `match`/`idle` sends no reject: its hello's stage gives the clearer reason
- [x] Host lobby shows `n of 5 guests connected` and `room full`
- [x] `--scenario guests` (host + two guests) is the default netplay run
- [x] `--scenario six` (host + five guests, plus a refused seventh page) is opt-in
- [x] Intro dismissal uses harmless clicks, so multi-engine runs no longer lose input
- [ ] 16-player `-DSMPF` build (optional, M4)

## How to run (dev)

```sh
./scripts/build-web.sh
python3 -m http.server -d web/dist 8123
# open http://localhost:8123/
```

Solo: click Play. Multiplayer: open up to six browsers (or profiles), type the same
room code in each, click **Host** in one and **Join** in the others, then start a network
game from the menu. The room code is the game/room identifier; a sixth guest is refused
with "The room is full (6 players).".

Scripted checks:

```sh
python3 scripts/cdp_shot.py http://localhost:8123/index.html /tmp/shot.png 8
python3 scripts/playtest.py            # solo: assigns Olaf, starts a game, moves/bombs
python3 scripts/netplaytest.py         # three browsers: host + two guests, then a match
python3 scripts/netplaytest.py --scenario six       # six players + a refused seventh (heavy)
python3 scripts/netplaytest.py --scenario match     # two-browser regression
python3 scripts/netplaytest.py --scenario refresh   # guest reloads, rejoins, match starts
python3 scripts/netplaytest.py --scenario midmatch  # refresh after start fails clearly
python3 scripts/nettest_js.py          # transport: basic, wrong-room, multi, replace, full
```

`scripts/netplaytest.py` needs internet access to public Nostr relays (skip with
`XB_TEST_OFFLINE=1`) and starts Chromium with
`--disable-features=WebRtcHideLocalIpsWithMdns` so the local pages can connect.

## Known issues / notes

- **No TURN.** Some NAT pairs cannot connect. Public relays are signalling only; they do
  not relay game traffic.
- **Host tab backgrounding can stall the match**: browsers throttle background timers and
  the engine loop is timer-driven. Keep the host tab in the foreground.
- **No reconnect, host migration or chat UI.** Closing the host tab ends the match; a
  dropped guest is gone.
- **Refresh/rejoin:** a guest who refreshes before the match starts gets a Rejoin prompt and
  the host replaces the old client (0.3.1). A refresh after the match starts fails with a
  clear message; **mid-match resume/replay is not implemented** and is the remaining reconnect
  item. A refreshed host restarts the room; guests must rejoin.
- **Public Nostr relays can be down.** `nostr.robosats.org` was returning 502 during the
  playtest; the browser logs the failed WebSocket, but the other default relays carry the
  room, so it is cosmetic. Signalling is still a public dependency (see TURN/NAT above).
- **DevTools 404s are harmless.** Chrome probes
  `/.well-known/appspecific/com.chrome.devtools.json`, and DevTools requests the
  `*.mjs.map` files we intentionally stripped from the vendored bundle. No normal page
  load requests either.
- **Verified player counts:** three browsers end to end (host + two guests) are the default
  test; six (host + five guests) run on demand with `--scenario six`, which needs six engine
  pages and several minutes.
- **A full room needs a reload to retry.** A refused guest's channels are closed; the lobby's
  Rejoin after a reload is the way back in once a slot frees.
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

1. Chat UI over the reliable channel.
2. Per-round state hash to detect and report desync.
3. TURN: optional relay fallback for restrictive NATs.
4. Host migration and a host-backgrounding warning.
5. **Later:** mid-match resume/replay — a refreshed guest rejoining an in-progress match. Needs
   an engine state snapshot/replay and is separate from the pre-match reconnect/replace slice.
6. **Optional, later:** 16-player build. Upstream's `--enable-SMPF` (`-DSMPF`) raises
   `MAX_PLAYER` from 6 to 16 and with it `MAX_HOSTS`; it also switches the status bar,
   scoreboard, intro and host menu to their 2D layouts (`status.c`, `intro.c`,
   `menu_network.c`, `map.c`). The web transport would need the JS capacity derived from the
   engine instead of the 6-player constant, and more action datagrams per frame (the engine's
   `MAX_MASK_BYTES` already allows it). It is off in `scripts/build-web.sh` and is not part of
   M3; revisit as an opt-in build in M4.
