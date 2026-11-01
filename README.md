# xblast-web

XBlast TNT (the classic Bomberman-style game) running in the browser, with
peer-to-peer multiplayer and no game server.

Status: **0.3.0 — two-player P2P**. Single-player and a two-player network
match work in Chromium-based desktop browsers (Chrome, Edge, and other Chromium
derivatives); six players, chat and reconnect are still to come.

- `engine/` — vendored XBlast TNT 2.10.4 with Debian patches (GPL-2.0-or-later)
- `data/` — images, levels, sounds, music and the Bitstream Vera font, from the
  Debian `xblast-tnt-*` packages (GPL-2+); see `LICENSE/data/`
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
./scripts/build-web.sh
python3 -m http.server -d web/dist 8123
```

Then open <http://localhost:8123>. Solo works over plain HTTP. Multiplayer needs
a secure context — HTTPS, or `localhost` as above — because it uses Web Crypto
and WebRTC. The `.wasm` and `.data` files will not load from `file://`.

## Play

- **Solo** — click Play, then start a local game against bots or a second
  keyboard player.
- **Multiplayer** — open the page in two browsers (or two profiles), enter the
  same room code in both, and click **Host** in one and **Join** in the other.
  The host starts the match from the game menu; both wait screens show the room
  code. Share the code with the other player. Traffic goes directly between the
  browsers over WebRTC; Trystero only exchanges connection details over public
  Nostr relays. TURN is required for some NAT pairs and is not wired up yet, so
  a few network combinations cannot connect.
- **Refresh / rejoin** — if the guest reloads before the match starts, the
  lobby offers **Rejoin** and the host replaces the old client. A reload after
  the match has started fails with a clear message; resuming a running match is
  not implemented. Re-hosting after a host reload starts a fresh room.
- **Leave / change rooms** — use **Leave**, or *Multiplayer Lobby* on the main
  menu, which reloads the page. Leaving a match returns to the menu but keeps
  the room.

## Test

```sh
python3 scripts/playtest.py       # solo: start a game, move, drop a bomb
python3 scripts/nettest_js.py     # transport: real WebRTC pages, two/three peers
python3 scripts/netplaytest.py    # two headless browsers: host/join, then a match
python3 scripts/netplaytest.py --scenario refresh   # guest reloads, rejoins, match starts
python3 scripts/netplaytest.py --scenario midmatch  # refresh after start fails clearly
```

`scripts/nettest_js.py` and `scripts/netplaytest.py` need internet access to
public Nostr relays (set `XB_TEST_OFFLINE=1` to skip the netplay test) and launch
Chromium with `--disable-features=WebRtcHideLocalIpsWithMdns` so local pages can
connect.

## Hosting

The build is a plain static bundle (`web/dist/`), so it can be served from GitHub Pages
without any backend. Signalling uses the public relays Trystero ships with. TURN is
required for some NAT pairs; relay mode is not wired up yet, so those pairs cannot connect.

## Attribution

This port is vibecoded with **DeepSeek V4.1 Flash Free**
(`opencode/deepseek-v4.1-flash-free`). Every commit carries an `Assisted-by:` trailer.
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

The whole work is distributed under GPL-2.0-or-later. Upstream code is
GPL-2.0-or-later (parts LGPL-2+); data packages are GPL-2+; vendored Trystero
and noble remain MIT. See `LICENSE/` and the headers in `engine/`.
