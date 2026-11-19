# Progress

Updated: 2026-11-04 (mobile touch controls; 0.6.2 filtered test relay; 0.6.0 invite links)

## Milestones

| Milestone | State |
|---|---|
| M0 — engine boots in browser | **done** (0.1.0) |
| M1 — single-player playable on web | **done** (0.2.0) |
| M2 — 2-player P2P | **done** (0.3.0) |
| M3 — 6-player, reconnect, TURN, host takeover | **done** (0.4.0; mid-match migration not planned) |
| M4 — public source publication (license audit, GitHub, Pages) | **done** (0.5.0 public; 0.5.1 patch) |
| M5 — polish, assets, PWA, optional 16-player (`SMPF`) build | in progress (build targets, invite links in 0.6.0; 16-player acceptance pending) |

## M2 checklist

- [x] Vendor Trystero 0.26.0 (nostr + core) and `@noble/secp256k1`, no npm at build time
- [x] Transport: one Trystero room per page, two negotiated DataChannels per peer
- [x] Channels: reliable-ordered `xb.ctl` for control/level/chat, unreliable-unordered
      `xb.act` for per-frame actions
- [x] Room lobby on the landing page: room code, New, Host, Join, room-code copy, Leave
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

## M4 public publication (0.5.0)

M4 is **published**: source at <https://github.com/jeremymurray/xblast-web>, site at
<https://jeremymurray.github.io/xblast-web/>, release `0.5.0` with source archive, web
bundle and `SHA256SUMS`. Pages serves `.wasm` as `application/wasm`, has no
`turn.json`, and `SOURCE.txt` names the tagged commit. `0.4.0` stays as the M3 tag.

The `0.5.0` tag's CI check is red from a test-harness race (the harness polled for
`__test` before `net.js` finished importing). It is fixed and released as **0.5.1**;
0.5.0 stays as the M4 publication tag. The transport suite still has a known
public-relay flake, mitigated by per-scenario retries (`XB_TEST_RETRIES=2` in CI).

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
- [x] Contribution policy (`CONTRIBUTING.md`, README): fun side project, contributions and
      issues not accepted for now; fork guidance, AI disclosure and a best-effort security
      note
- [x] CI (build + artifact checks + JS transport; netplay manual) and Pages workflow;
      variant artifacts are never uploaded
- [x] Release tooling: `scripts/check-web-dist.sh`, `scripts/make-release.sh`, release workflow
- [x] Public repo `jeremymurray/xblast-web` with Issues/Discussions disabled; `main`,
      `0.4.0` and `0.5.0` pushed; Pages enabled from GitHub Actions; release `0.5.0`
      published; public build boots and the Pages smoke test passes

## Release notes — 0.6.2

Test-infrastructure patch; no gameplay change. The local Nostr test relay now
honours the REQ kind/topic filters and replays only recent matching events, so late
CI scenarios are not flooded with every earlier event and WebRTC handshakes stop
timing out. 0.6.1 remains the first CI-efficiency release; 0.6.2 is the clean tag.

## Release notes — 0.6.1

CI and test-infrastructure bugfix; no gameplay change. CI builds the web bundle once
and reuses that artifact for the transport tests and the Pages deploy. Transport tests
run against a localhost Nostr relay instead of the public relays, with retries only for
the scenario that failed. Pages now deploys from the same CI artifact.

## Release notes — 0.6.0

Invite links. A host or guest can click **Invite** in the netbar to copy a URL; opening
it fills in the room code and offers **Join**, so a newcomer does not have to type the
code. The room code itself is now the copy-code control. Nothing connects until Join is
clicked, and a link still only works while the host is waiting; mid-match joins are
unchanged. No gameplay or netcode change.

## Release notes — 0.5.1

Patch release; no gameplay change. Fixes the transport harness so it waits for
`net.js` to finish loading before checking `XBNet`, which made CI red on slow runners
(including the 0.5.0 tag). The release workflow now fetches annotated tags before
reading the notes, so GitHub releases use the tag message rather than the commit
message. 0.5.0 remains the M4 publication release.

## Release notes — 0.5.0

M4 has no gameplay change. It makes the project publishable: a hash-level asset audit
(`docs/provenance.md`), complete third-party notices, LGPL and Bitstream Vera texts,
contributor and security policies, CI/Pages/release workflows, reproducible release
packaging, and a source offer shipped with every build. Correction: six music tracks
were always bundled and are now documented and audited as such; earlier notes wrongly
said no music was included. Gameplay, netcode and the six-player capacity are unchanged
from 0.4.0.

## M5 invite links

- [x] `?room=` prefills the lobby and shows an invite prompt for host or guest
- [x] Netbar **Invite** copies the absolute URL; clicking the room code copies the code
- [x] `nettest_js.py roomcode` covers URL building, sanitization, prefill, consumed
      query and no auto-connect
- [x] Local two-browser check: invite prefills, Join starts the client, room-code
      click copies/falls back; `netplaytest --scenario midmatch` still refuses
- [ ] Public-site invite smoke test after the next deploy

## CI (0.6.1)

- [x] Build once per run; transport downloads the `release-dist` artifact and uses
      `XB_TEST_NO_BUILD=1`
- [x] Transport tests use a localhost test relay (`scripts/test_relay.py`) with pinned
      `websockets==17.4`, test-only; public relays remain the production default
- [x] Pages deploys from the same artifact in `ci.yml`; the separate `pages.yml` is gone
- [x] Per-scenario retries (`XB_TEST_RETRIES`), not whole-suite reruns; refused-guest
      EOF wait widened
- [x] First public CI run confirmed: build 2m14s, transport 1m56s (artifact reused),
      Pages deployed from the same artifact, smoke test passed; total run 3m27s

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

## M5 mobile touch controls (2026-11-04)

- [x] `XBWeb_SendKey` C bridge pushes real SDL key events; exported from the build
- [x] Landscape grid (pad | playfield | actions) and portrait (playfield top, controls below)
- [x] Pointer layer: slide/re-entry, direction+bomb multi-touch, blur/visibility release, no dead buttons
- [x] Pads hidden until the runtime is ready and after exit; `?touch=1` / `?touch=0` overrides
- [x] Playfield taps select engine menu items; Kick acts as Select in menus
- [x] Lobby scrolls on short screens; safe-area padding; status line kept visible
- [x] Landscape grid keeps the pad clear of the canvas down to 568x320
- [x] `scripts/touchtest.py` (CDP): bridge, both layouts, small landscape, desktop unchanged,
      lobby scroll, pointer safety, menu taps and player assignment
- [ ] Manual iOS Safari + Android Chrome acceptance, portrait and landscape, solo and netplay.
      A full match start is manual: the setup screen needs two players and its modal combo
      close is ambiguous through the key bridge.
- Known: touch sends the default web bindings; a remapped P1 keyboard layout is not mirrored.
- Known: `scripts/playtest.py` is stale — it never assigns two players, so its Return cannot
  start the setup menu. Reproduced on the 0.6.2 baseline, so it is not a touch regression.

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
python3 scripts/playtest.py            # solo: assigns Olaf, starts a game, moves/bombs (stale, see above)
python3 scripts/touchtest.py           # phone layouts + touch keys; builds web/dist
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
./scripts/check-web-dist.sh            # fail unless web/dist is a publishable release
XB_SOURCE_URL=<repo-url> ./scripts/build-web.sh --target release
XB_SOURCE_URL=<repo-url> ./scripts/make-release.sh 0.6.1   # source + web + SHA256SUMS
```

`scripts/nettest_js.py` uses a local test relay and needs no internet; install
its test-only dependency with `python3 -m pip install -r requirements-test.txt`.
`scripts/netplaytest.py` still needs internet access to public Nostr relays (skip
with `XB_TEST_OFFLINE=1`). Both start Chromium with
`--disable-features=WebRtcHideLocalIpsWithMdns` so local pages can connect.

## Known issues / notes

- **Antialiased text (web only).** `engine/sdl_text.c` renders with
  `TTF_RenderUTF8_Blended` and draws the outline by stamping blended glyphs, under
  `__EMSCRIPTEN__`; desktop keeps the 1-bit `Solid` path. The canvas is still CSS-scaled
  with `image-rendering: pixelated`, so non-integer scales leave some blockiness.
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
  room, so it is cosmetic for players. The transport test suite no longer depends on them
  (local relay); netplay still does, so it stays manual/optional.
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
  0.4.0 = M3, 0.5.0 = M4, 0.5.1 = harness/release-notes fix, 0.6.0 = invite links, 0.6.1 = CI efficiency, 0.6.2 = filtered test relay.
- Attribution: every commit carries a `Signed-off-by:` and, when AI-assisted, an
  `Assisted-by:` trailer (see `README.md` and `AGENTS.md`).

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
