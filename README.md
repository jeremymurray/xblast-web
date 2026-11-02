# xblast-web

XBlast TNT (the classic Bomberman-style game) running in the browser, with
peer-to-peer multiplayer and no game server.

Status: **0.4.0 (M3 complete)**. Solo and network matches
(one host plus up to five guests) work in Chromium-based desktop browsers (Chrome,
Edge, and other Chromium derivatives); three browsers are covered by the default test,
six by an opt-in one. Host takeover, readable room codes and the backgrounding warning
are in; chat, a desync hash and mid-match host migration are not planned.

- `engine/` — vendored XBlast TNT 2.10.4 with Debian patches (GPL-2.0-or-later)
- `data/` — images, model sprites (`.epm`), levels, sounds and the Bitstream Vera font,
  from the Debian `xblast-tnt-*` packages (GPL-2+); no music tracks are bundled; see
  `LICENSE/data/` and `docs/publishing.md`
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
- **Multiplayer** — open the page in up to six browsers (or profiles), enter the
  same room code in each, and click **Host** in one and **Join** in the others. The
  host starts the match from the game menu; every wait screen shows the room code. A
  sixth guest is told the room is full. Traffic goes directly between the browsers
  over WebRTC; Trystero only exchanges connection details over public Nostr relays.
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

## Test

```sh
python3 scripts/playtest.py       # solo: start a game, move, drop a bomb
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

`scripts/nettest_js.py` and `scripts/netplaytest.py` need internet access to
public Nostr relays (set `XB_TEST_OFFLINE=1` to skip the netplay test) and launch
Chromium with `--disable-features=WebRtcHideLocalIpsWithMdns` so local pages can
connect.

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
and noble remain MIT; the Bitstream Vera font keeps its own licence. See
`LICENSE/`, `docs/publishing.md` and the headers in `engine/`.
