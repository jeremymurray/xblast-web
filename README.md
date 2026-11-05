# xblast-web

XBlast TNT (the classic Bomberman-style game) running in the browser, with
peer-to-peer multiplayer and no game server.

Status: **0.6.2** (M4 complete). Solo and network matches
(one host plus up to five guests) work in Chromium-based desktop browsers (Chrome,
Edge, and other Chromium derivatives); three browsers are covered by the default test,
six by an opt-in one. Host takeover, readable room codes and the backgrounding warning
are in; chat, a desync hash and mid-match host migration are not planned.

**Play:** <https://jeremymurray.github.io/xblast-web/> — desktop Chromium; open a second
tab or device with the same room code for multiplayer. Source:
<https://github.com/jeremymurray/xblast-web>.

## About this project

This is a **fun side project**: a vibecoded experiment to see whether a 2005 C game
could run in a browser with peer-to-peer multiplayer and no server. It is shared
because it is fun to play with, not because it is a product. Expect rough edges, and
there is no roadmap or response-time promise.

**Contributions and issues are not being accepted at this time.** Please don't send
pull requests or file issues. If you want to take it further, fork it under
GPL-2.0-or-later and keep the licence notices and the AI-assistance disclosure intact
(see `CONTRIBUTING.md`). Security reports: `SECURITY.md`.

## Layout

- `engine/` — vendored XBlast TNT 2.10.4 with Debian patches (GPL-2.0-or-later)
- `data/` — images, model sprites (`.epm`), levels, sound effects, the six background
  music tracks and the Bitstream Vera font, from the Debian `xblast-tnt-*` packages
  (GPL-2+; the font has its own licence); see `LICENSE/`, `THIRD_PARTY.md` and
  `docs/provenance.md`
- `web/` — browser shell, SDL 2 backend and web glue; `web/net.js` is the
  WebRTC transport and `web/net_web.c` its `socket.h` shim
- `web/vendor/trystero/` — vendored Trystero 0.26.0 and noble, MIT
- `build/gen/config.h` — configuration for the Emscripten build
- `scripts/build-web.sh` — builds `web/dist/`

## Build

Requires the Emscripten SDK pinned in `.tool-versions`:

```sh
asdf plugin add emsdk
asdf install
./scripts/build-web.sh                 # release, six players, writes web/dist
python3 -m http.server -d web/dist 8123
```

Then open <http://localhost:8123>.

Build targets are local-only; CI must not publish the variant artifacts:

```sh
./scripts/build-web.sh --list          # target, capacity, profile, output
./scripts/build-web.sh --target 16p    # 16-player engine + 15-guest cap
./scripts/build-web.sh --target lite-debug  # no sounds data + debug logging
./scripts/build-web.sh --all           # all twelve targets
```

| Targets | Capacity | Notes |
|---|---|---|
| `release`, `debug`, `lite`, `lite-debug`, `small`, `mini` | 6 players | default `web/dist` for `release`, others `web/dist-<target>` |
| `16p`, `debug-16p`, `lite-16p`, `lite-debug-16p`, `small-16p`, `mini-16p` | 16 players | `-DSMPF`; separate wasm |

`lite` and `lite-debug` omit the sounds package; `debug` and `lite-debug` add
logs/assertions. `small` uses `-Oz`/emmalloc and `mini` uses compact geometry.
The build writes `build-info.js` with `maxPlayers`; `web/net.js` derives
`maxClients = maxPlayers - 1`. `web/dist-*` is ignored and is not published by CI.

Solo works over plain HTTP. Multiplayer needs
a secure context — HTTPS, or `localhost` as above — because it uses Web Crypto
and WebRTC. The `.wasm` and `.data` files will not load from `file://`.

## Play

- **Solo** — click Play, then start a local game against bots or a second
  keyboard player.
- **Multiplayer** — open the page in up to six browsers (or profiles), enter the
  same room code in each, and click **Host** in one and **Join** in the others. The
  host starts the match from the game menu; every wait screen shows the room code. A
  sixth guest is told the room is full. Once in a room, either the host or a guest can
  click **Invite** in the netbar to copy a link that opens the room prefilled for
  one-click joining; clicking the room code itself copies the code. Traffic goes
  directly between the browsers over WebRTC; Trystero only exchanges connection
  details over public Nostr relays.
  TURN is optional and supplied by the hoster or by the player; without one, a few
  network combinations cannot connect. See `docs/hosting.md`.
- **Host leaves** — before a match, every guest gets a **Take over** prompt. One
  claims the room, reloads as host, and the others rejoin automatically. The
  room code stays the same. If the host leaves mid-match, the match ends and the
  takeover flow starts a new one; mid-match migration is not planned.
- **Refresh / rejoin** — if the guest reloads before the match starts, the
  lobby offers **Rejoin** and the host replaces the old client. A reload after
  the match has started fails with a clear message; resuming a running match is
  not implemented. A host that reloads and clicks **Re-host** brings guests back
  automatically.
- **Background host** — the host should keep the tab in the foreground; guests
  warn in the netbar when the host tab is backgrounded, because browsers can
  throttle the host's timers.
- **Leave / change rooms** — use **Leave**, or *Multiplayer Lobby* on the main
  menu, which reloads the page. Leaving a match returns to the menu but keeps
  the room.

### Touch controls

On a phone or tablet the on-screen controls appear automatically: a movement pad
with a centre **Stop** on the left, **Bomb** above **Kick** on the right, and
**Pause** and **Back** on the bottom edge. Landscape puts the playfield between
the two clusters; portrait pins the playfield to the top with the controls below.
A touch-capable laptop shows them too; add `?touch=0` to hide them or `?touch=1`
to force them on.

Tap a menu item on the playfield to choose it — a tap is translated to the mouse
click the engine's menus already understand. Inside menus **Kick** also works as
Select, and **Stop** changes a combo's value. The setup screen needs **two
players** assigned (keyboards or a bot) before **Start** activates; that is the
engine's own rule, unchanged here.

The buttons send the default web bindings (arrows, Return, Tab in play and Space
in menus, BackSpace, P, Escape), so they do not follow a custom P1 keyboard
mapping. **Back** is the engine's Escape: from the main menu it quits, and during
a match it leaves the match, exactly like the keyboard.

## Test

```sh
python3 scripts/playtest.py       # solo: start a game, move, drop a bomb
python3 scripts/touchtest.py      # phone layouts + touch keys; builds web/dist
python3 scripts/nettest_js.py     # transport: real WebRTC pages, up to seven peers
python3 scripts/netplaytest.py    # three browsers: host + two guests, then a match
python3 scripts/netplaytest.py --scenario six       # six players, heavy, opt-in
python3 scripts/netplaytest.py --scenario match     # two-browser regression
python3 scripts/netplaytest.py --scenario refresh   # guest reloads, rejoins, match starts
python3 scripts/netplaytest.py --scenario midmatch  # refresh after start fails clearly
python3 scripts/netplaytest.py --scenario takeover  # host leaves, guest hosts, others auto-rejoin
python3 scripts/netplaytest.py --scenario takeover-stuck  # a stuck new host is superseded
python3 scripts/netplaytest.py --scenario hostback  # host re-hosts, guest auto-rejoins
python3 scripts/netplaytest.py --scenario hostgone  # host leaves mid-match, new match starts
python3 scripts/netplaytest.py --scenario autojoin  # flushed guest auto-connects after reload
```

`scripts/nettest_js.py` and `scripts/netplaytest.py` need Chrome. The transport
suite starts a local Nostr relay and needs no internet; install its one test
dependency first:

```sh
python3 -m pip install -r requirements-test.txt
```

The netplay suite still uses the public Nostr relays over the internet (set
`XB_TEST_OFFLINE=1` to skip it). Both launch Chromium with
`--disable-features=WebRtcHideLocalIpsWithMdns` so local pages can connect.

## Hosting

The build is a plain static bundle (`web/dist/`), so it can be served from GitHub Pages
without any backend. Signalling uses the public relays Trystero ships with. TURN is
optional and supplied by whoever hosts a copy or by a player with their own relay; without
one, some NAT pairs cannot connect. See [docs/hosting.md](docs/hosting.md) for the hosting
profiles, `turn.json` schema, a coturn checklist and the credential-endpoint contract.
A static `turn.json` credential is public: use a dedicated credential with quotas,
rotate it, and prefer the credential-endpoint mode for public play.

## Attribution

This port is vibecoded with **DeepSeek V4.1 Flash Free**
(`opencode/deepseek-v4.1-flash-free`). Every commit carries a DCO
`Signed-off-by:` and an `Assisted-by:` trailer. See `CONTRIBUTING.md`.
Upstream XBlast TNT is the work of Oliver Vogel and contributors; this project only ports it.

Vendored third-party code:

| Component | Version | Licence |
|---|---|---|
| `@trystero-p2p/nostr` / `@trystero-p2p/core` | 0.26.0 | MIT |
| `@noble/secp256k1` | 3.2.0 | MIT |

Their licences are in `web/vendor/trystero/LICENSE.trystero` and
`web/vendor/trystero/LICENSE.noble`; sources and hashes are listed in
`web/vendor/trystero/README.md`.

## Licence

The whole work is distributed under **GPL-2.0-or-later**, with complete
corresponding source in this repository. Upstream XBlast TNT code is
GPL-2.0-or-later (two SDL-derived files are LGPL-2.0-or-later); the Debian data
packages, including the six music tracks, are GPL-2+; vendored Trystero and noble
remain MIT; the Bitstream Vera font keeps its own permissive licence.

- `COPYING` — GPLv2, the base text.
- `THIRD_PARTY.md` — every component, version and licence.
- `LICENSE/` — LGPL-2.0, Bitstream Vera, third-party texts and the Debian
  copyright files.
- `docs/provenance.md` — package versions, checksums and the asset audit.

The source is the repository itself; each release also ships a source archive and
checksums, so the build can be reproduced from the exact tree that produced the
artifact. Build instructions and the pinned toolchain are above.

This software comes with **no warranty**, to the extent permitted by law; see
GPLv2 sections 11–12. Asset provenance is recorded, including the limitation
that upstream provides no per-track authorship record for the six music files.
