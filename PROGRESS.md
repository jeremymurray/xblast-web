# Progress

Updated: 2026-11-01 (M3 complete, 0.4.0)

## Milestones

| Milestone | State |
|---|---|
| M0 — engine boots in browser | **done** (0.1.0) |
| M1 — single-player playable on web | **done** (0.2.0) |
| M2 — 2-player P2P | **done** (0.3.0) |
| M3 — 6-player, reconnect, TURN, host takeover | **done** (0.4.0; mid-match migration not planned) |
| M4 — public source publication (license audit, GitHub, Pages) | in progress (GPL-2.0-or-later decided; publication checklist open) |
| M5 — polish, assets, PWA, optional 16-player (`SMPF`) build | in progress (local build targets done; 16-player acceptance pending) |

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

## M3 optional TURN

- [x] `web/turn.js` validates `turn:`/`turns:` entries and loads `turn.json`
- [x] Static `turnConfig` and `credentialsUrl` (short-lived credential endpoint) modes
- [x] Player **Advanced: TURN** override in the lobby, `sessionStorage` only, never shared
- [x] `XBNet.status()` exposes `turnConfigured`, `turnServers`, `turnSource` without credentials
- [x] No `turn.json` means STUN only; malformed files/endpoints never block the lobby
- [x] Examples, gitignored real config, build copy, `docs/hosting.md`
- [x] Tests: `turn-config` and `turn-ui` transport scenarios
- [ ] Real relay verification with coturn is manual; not part of the default suite

## M3 host takeover, backgrounding and room codes

- [x] Every guest gets a takeover prompt when the host leaves; a 500 ms claim window
      and lowest-client-id tie-break decide simultaneous claims
- [x] The winner reloads into the same room as host; other guests wait for `listening`
      and auto-rejoin/auto-connect
- [x] Config is flushed before the reload, so the player selection survives
- [x] The new-host path also covers the original host returning via **Re-host**
- [x] Two-host collision: the higher `(clientId, selfId)` steps down, leaves the room,
      rewrites the stored intent to client mode and offers **Rejoin as guest**
- [x] A new host that never reaches `listening` times out; guests can retry, and a
      stuck host in `setup` can be superseded
- [x] Host visibility is broadcast to guests; the netbar warns when the host tab is
      in the background
- [x] Room codes are `adjective-noun-NNN` from 64 five-letter adjectives and 64
      animal nouns of 3–5 letters (3,686,400 combinations)
- [x] Tests: `roomcode`, `visibility`, `hostleave`, `claim`, `collision`; netplay
      `autojoin`, `takeover`, `hostback`, `hostgone`
- [x] Mid-match migration is **not planned**; a host leaving ends the match and the
      takeover flow starts a new one

## Release notes — 0.4.0

M3 is complete. Six players can share a room; a guest can refresh and rejoin; TURN is optional;
and if the host leaves before a match, every guest is offered the room. A claim window picks one
new host, the page flushes the player config, and the others auto-rejoin. A host that refreshes
and clicks **Re-host** brings guests back automatically. The lobby warns when the host tab is
backgrounded, and room codes are now short adjective-animal-number phrases such as
`quiet-otter-482`. Mid-match host migration is deliberately not planned; a host loss ends the
match and the takeover flow starts a new one.

## M4 public publication (0.4.0)

The 0.4.0 tag exists locally; the repository is **not public yet**. The remaining
steps are the human-gated publication actions in `docs/publishing.md` §6.

- [x] Licence decision: GPL-2.0-or-later (kept; matches upstream and is already open source)
- [x] `NOTICE`/`THIRD_PARTY.md` covering engine, data, sprites, music, font, vendored JS,
      SDL stack, Emscripten and LGPL files; `LICENSE/README.md` indexes the texts
- [x] Asset/provenance audit with binary-package and upstream-sha256 comparison
      (`docs/provenance.md`); **music is bundled** and audited (six tracks, no per-track
      attribution upstream — limitation recorded)
- [x] LGPL-2.0 text for the SDL-derived files and the Bitstream Vera notice
- [x] README/AGENTS/PROGRESS/FEASIBILITY corrected; no-warranty and source-offer added;
      builds ship `COPYING`, `THIRD_PARTY.md`, `LICENSE/` and `SOURCE.txt`
- [x] History/secrets scan: no real secrets; placeholders only; no ignored artefact ever tracked
- [x] Contribution policy (`CONTRIBUTING.md`, DCO, inbound=outbound, AI disclosure) and
      `SECURITY.md`
- [x] CI (build + artifact checks + JS transport; netplay manual) and Pages workflow;
      variant artifacts are never uploaded
- [x] Release tooling: `scripts/check-web-dist.sh`, `scripts/make-release.sh`, release workflow
- [ ] Choose repo name/identity, create the public repo, push `main` + `0.4.0`, enable Pages,
      create the release and smoke-test it — human sign-off required

## M5 build targets (local only)

- [x] `scripts/build-web.sh --target …` for `release`, `16p`, `debug`, `debug-16p`,
      `lite`, `lite-16p`, `lite-debug`, `lite-debug-16p`, `small`, `small-16p`,
      `mini`, `mini-16p`
- [x] `--list`, `--all`; `release` writes `web/dist`, variants write `web/dist-<target>`
- [x] Generated `build-info.js` publishes `maxPlayers`; `web/net.js` derives
      `maxClients = maxPlayers - 1`
- [x] `debug`/`lite-debug` compile with `-DDEBUG` after the SDL2 debug-print guard
- [x] Variant outputs are gitignored and must not be published by CI
- [ ] 16-player gameplay acceptance; the build target and 15-guest transport cap are ready

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
python3 scripts/netplaytest.py --scenario autojoin  # flushed guest auto-connects after reload
python3 scripts/netplaytest.py --scenario takeover  # host leaves, guest hosts, others auto-rejoin
python3 scripts/netplaytest.py --scenario takeover-stuck  # a stuck new host is superseded
python3 scripts/netplaytest.py --scenario hostback  # host re-hosts, guest auto-rejoins
python3 scripts/netplaytest.py --scenario hostgone  # host leaves mid-match, new match starts
python3 scripts/nettest_js.py          # transport: basic, wrong-room, multi, replace, full,
                                      # turn-config, turn-ui, roomcode, visibility, hostleave,
                                      # claim, collision, peerleave
```

`scripts/netplaytest.py` needs internet access to public Nostr relays (skip with
`XB_TEST_OFFLINE=1`) and starts Chromium with
`--disable-features=WebRtcHideLocalIpsWithMdns` so the local pages can connect.

## Known issues / notes

- **TURN is optional and hoster/player supplied.** Without a relay, some NAT pairs cannot
  connect. Public Nostr relays are signalling only; they do not relay game traffic. The project's
  own deployment runs no TURN; `docs/hosting.md` covers self-hosting and the player override.
- **Host tab backgrounding can still stall the match**: browsers throttle background timers
  and the engine loop is timer-driven. The netbar warns guests and the host page reminds you,
  but keep the host tab in the foreground.
- **Host takeover is pre-match only.** If the host leaves before a match, every guest gets a
  Take over prompt; the winner reloads as host and the others auto-rejoin. If the host leaves
  mid-match, the match ends and the takeover flow starts a new one. **Mid-match migration is not
  planned** (client→server role switch, host-id remapping, level progression and desync risk).
  There is no lobby chat UI (deferred, see Possible future work); the engine's in-game chat
  still works.
- **Refresh/rejoin:** a guest who refreshes before the match starts gets a Rejoin prompt and
  the host replaces the old client (0.3.1). A refresh after the match starts fails with a
  clear message; mid-match resume/replay is not implemented. A refreshed host that clicks
  **Re-host** now brings guests back automatically.
- **Auto-rejoin reloads the page.** Config is flushed first, but the engine still reloads
  (assets are cached). If no local player was saved, the guest lands in the join menu.
- **Room codes are random and have no registry.** `adjective-noun-NNN` has 3.69 M
  combinations; a collision means two groups meet in the same room and the existing role
  checks apply.
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
- **No per-round desync hash (deferred).** A 710-frame two-browser diagnostic matched exactly;
  the feature is in possible future work. Divergence with the same winning team would still be
  silent; the existing winner-team async check catches outcome differences.
- **The room persists after a match.** Leaving a match returns to the menu but stays in
  the room; use **Leave** or *Multiplayer Lobby* on the main menu, which reloads.
- **Netplay test needs internet** and the mDNS flag (see above).
- **Audio** needs a human ear check; the mixer is wired and WebAudio unlocks on first input.
- **Fades are disabled on the web build** (`__EMSCRIPTEN__` in `sdl_pixmap.c`): they are a
  blocking `SDL_Delay` effect. Keep transitions instant until a non-blocking fade exists.
- **Quit needs `EXIT_RUNTIME=1`** so `Module.onExit` runs and the page shows "Play again".
- `©` in the intro still renders as a missing-glyph box.
- Bundle: ~3.5 MB wasm + ~15 MB LZ4 data (all sounds, including the six music tracks).

## Decisions

- Base: XBlast TNT 2.10.4 + Debian patches. Data: Debian GPL-2+ packages.
- **sdl12-compat is not used**: it dlopens `libSDL2.so`, which does not exist under
  Emscripten. The SDL backend is ported directly to SDL 2.
- SDL 2 ports: `SDL2`, `SDL2_image`, `SDL2_ttf`, `SDL2_mixer`, `SDL2_gfx`.
- Hosting target: static files, including GitHub Pages; no backend.
- Networking: WebRTC star, host is the authoritative game server.
- Signalling: vendored Trystero 0.26.0 (MIT) over public Nostr relays; no npm at build
  time and no CDN at runtime.
- TURN is optional: deployer `turn.json` (static or credential endpoint) or a player override
  in the lobby. The project runs no TURN service or credential endpoint.
- Host takeover is pre-match only: open prompt, 500 ms claim window, lowest client id wins;
  the winner reloads as host and the others auto-rejoin after a config flush. A hidden host is
  warned about but never evicted.
- Room codes are `adjective-noun-NNN`: 64 five-letter adjectives and 64 animal nouns of
  3–5 letters.
- Mid-match migration is not planned.
- Versioning: `0.MINOR.PATCH`; 0.1.0 = M0, 0.2.0 = M1, 0.3.0 = M2, 0.3.1 = reconnect,
  0.4.0 = M3.
- Attribution: every commit carries a `Signed-off-by:` and, when AI-assisted, an
  `Assisted-by:` trailer (`CONTRIBUTING.md`).

## Next tasks (M5)

1. **16-player build acceptance.** The `16p` build target and generated capacity are ready
   (`-DSMPF`, `MAX_PLAYER`/`MAX_HOSTS` 16, 2D layouts, `maxPlayers: 16` in `build-info.js`).
   Remaining work is a real 16-player layout/match test and a transport capacity test at
   15 guests. The engine's `MAX_MASK_BYTES` already covers 16 players.

## Possible future work (not planned)

- **Mid-match host migration / resume.** Not planned. It needs a client→server role switch,
  host-id/player remapping, level-progression state and a desync guard; the engine cost is
  disproportionate for a casual match. The takeover flow starts a new match after a mid-match
  host loss.
- **Lobby chat UI.** Deferred 2026-11-01: the engine's in-game chat is adequate and there is no
  separate web lobby to host a chat panel. Revisit only if a persistent lobby/social screen
  exists; it would ride `xb.ctl` with host relay.
- **Per-round desync hash.** Deferred 2026-11-01 after a diagnostic (unmerged branch
  `spike/desync-hash`, commit `8e4a8ae`). It hashed game time, RNG seed, player state, maze,
  extras and explosions every 10 frames in a two-browser match: 710 frames / 71 samples
  matched exactly on host and guest, and the normal netplay test passed. Not covered: packet
  loss, more than two peers, mixed browsers. The winner-team async check already catches
  outcome differences. Revisit if a real divergence appears; start with report-only, not
  round scoring changes.
