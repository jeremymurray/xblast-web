# xblast-web — project agent notes

## Goal
Browser-playable XBlast TNT with peer-to-peer multiplayer, no backend, publicly publishable under
GPL-2.0-or-later.

## Read first
`PROGRESS.md` — current milestone, checklist, known issues, how to run.
`FEASIBILITY.md` — architecture, netcode, risks, milestones.

## Decisions (durable)
- **Base code:** XBlast TNT 2.10.4 + Debian patches, vendored into `engine/`.
- **Assets/data:** Debian `xblast-tnt-images/-levels/-sounds/-models/-musics` (GPL-2+) plus
  Bitstream Vera (`data/Vera.ttf`, Bitstream licence).
- **Port path:** Emscripten, keep the C engine and the `gui.h` seam.
  **No sdl12-compat** — it dlopens SDL2, which is unavailable in wasm. The SDL backend is ported
  directly to SDL 2 (`web/compat/`, `web/sdl_web.c`).
- **Network:** WebRTC star, host = authoritative game server. Two DataChannels: reliable-ordered
  `xb.ctl` for control/level/chat, unreliable-unordered `xb.act` for per-frame actions. Map onto
  `socket.h`.
- **Signalling:** vendored Trystero 0.26.0 (`nostr` + `core`) and `@noble/secp256k1`, MIT, no npm
  at build time and no CDN at runtime. `./scripts/vendor-trystero.sh` regenerates them.
- **Room lifecycle:** the room is page-owned (`web/index.html`), not fd-owned. It is joined when
  **Host** or **Join** is clicked and the code is the game/room identifier; the engine's socket
  shim only attaches synthetic fds. Closing a stream never leaves the room; only **Leave** or the
  **Multiplayer Lobby** main-menu entry (a page reload) does.
- **Web main menu:** Solo, Multiplayer Lobby, Options, Quit. The legacy IRC/central-server
  screens are unreachable on web: the main menu replaces them, and old entry points redirect or
  reload the lobby. They are not removed from the shared engine source.
- **Netplay test:** `scripts/netplaytest.py` needs internet (public Nostr relays) and starts
  Chromium with `--disable-features=WebRtcHideLocalIpsWithMdns` so two local pages connect.
- **M2 playtest:** Chrome + Firefox on one machine played a match. Public-relay 502s and DevTools
  source-map 404s are cosmetic.
- **Reconnect/replace (0.3.1):** hello v2 carries a stable per-tab client id; the host replaces an
  old peer with the same id, closing its channels so the engine frees the slot. A host stage
  status (`setup`/`listening`/`match`/`idle`) makes a mid-match refresh fail clearly. The lobby
  stores the last room and offers Rejoin/Re-host.
- **Host takeover (M3):** pre-match only. If the host leaves, every guest gets a Take over
  prompt; a 500 ms claim window and lowest-client-id tie-break pick one. The winner reloads as
  host, the others wait for `listening` then auto-rejoin/auto-connect. The page flushes the
  engine config first; `xb:takeover` carries the intent across the reload. The same new-host
  path covers a host that refreshes and clicks **Re-host**. A two-host collision is resolved by
  `(clientId, selfId)`; the higher host steps down and offers Rejoin as guest. Mid-match
  migration is **not planned**; that match ends and takeover starts a new one.
- **Backgrounding warning:** the host broadcasts `hostVisible`; guests warn in the netbar, and
  the host page reminds you to keep the tab in the foreground. A hidden host is never treated as
  gone or evicted.
- **Room codes (M3):** `adjective-noun-NNN` from 64 five-letter adjectives and 64 animal nouns
  of 3–5 letters; 3,686,400 combinations. Custom codes still work. Generated in the lobby, no
  registry.
- **Hosting:** plain static files, deployable to GitHub Pages. No server-side code anywhere in the
  default path. Multiplayer needs HTTPS or localhost (secure context). Signalling uses public
  Nostr relays; **TURN is optional and hoster/player supplied** for the NAT pairs that need it.
  The project's own deployment runs no TURN and no credential endpoint; `docs/hosting.md` covers
  `turn.json`, coturn, the credential endpoint contract and the player override. Player TURN
  credentials are local (`sessionStorage`) and never shared.
- **Room capacity:** five guests + host = six players (`MAX_PLAYER` 6; `-DSMPF` would make it 16
  and is off). A sixth client gets `CTL_REJECT` → "The room is full (6 players)."; a rejoin by
  client id still replaces. `--scenario guests` (3 browsers) is the default netplay test,
  `--scenario six` is the heavy opt-in.
- **Licensing:** whole work published as GPL-2.0-or-later with complete corresponding source;
  vendored Trystero/noble stay MIT.
- No rollback/prediction, no TypeScript rewrite, no central server.
- **Web build skips screen fades** (`__EMSCRIPTEN__` in `sdl_pixmap.c`): the
  blocking `SDL_Delay` wipe stalls Asyncify and feels slow. Keep transitions
  instant until a non-blocking fade is implemented.
- **`EXIT_RUNTIME=1`** so quitting calls `Module.onExit` and the page can show
  the "Play again" overlay.

## Attribution
This port is vibecoded with **DeepSeek V4.1 Flash Free** (`opencode/deepseek-v4.1-flash-free`).
- README must state it.
- Every commit must end with:
  `Assisted-by: DeepSeek V4.1 Flash Free (opencode/deepseek-v4.1-flash-free)`
- Do not hide or downplay AI involvement.

## Git workflow
- `main` holds working, self-contained states; do exploration on a branch and merge it back with a
  merge commit when the unit of work is done.
- One commit = one logical change. Keep vendored upstream imports separate from port changes.
- Commit messages: `<area>: <imperative summary>`, then body if needed, then the assisted-by trailer.

## Versioning
- Semantic-ish tags: `0.MINOR.PATCH`. Current release: **0.3.1**; M3 is complete on the branch.
  0.4.0 is the next tag when the human partner asks.
- Bump MINOR when a milestone lands (M3 → 0.4.0), PATCH for playtest fixes.
- Tag annotated releases on `main` after the merge. Only git tags record the version; there is no
  version file, so keep this line and `PROGRESS.md` current.

## Engine change conventions
- Browser-only behaviour changes in `engine/` are wrapped in
  `#ifdef __EMSCRIPTEN__` with a `/* web port: ... */` comment, keeping the
  upstream branch in `#else`. This keeps the port's diff separable.
- Fork-wide changes (SDL 1.2 → SDL 2 API calls) are not guarded.
- Defaults live in the engine; persistence lives in the wrapper
  (`web/index.html`), which only mirrors the engine's config directory.

## Progress tracking
Update `PROGRESS.md` at each milestone and whenever context is about to be compacted: checklist,
known issues, next tasks, how to run. Keep it concise and current; it is the handoff document.

## Next milestone
M4. M3 is complete: six players, reconnect/replace, optional TURN, host takeover,
backgrounding warning and readable room codes. A lobby chat UI, a per-round desync hash and
mid-match host migration/resume are deliberately not planned (see `PROGRESS.md`); the
takeover flow starts a new match after a mid-match host loss. An optional 16-player `-DSMPF`
build is the main M4-era idea; the web build stays 6-player until then.

## Process rules
- Keep this file short; rewrite rather than append when context grows.
- Record any change of base/path/network/hosting decisions here.
- No new libraries without asking; prefer established, maintained ones.
