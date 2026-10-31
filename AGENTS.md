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
  for control/level/chat, unreliable-unordered for per-frame actions. Map onto `socket.h`.
- **Lobby/signalling:** Trystero (serverless room codes). TURN still required for some NATs;
  relay mode is an optional fallback, never the default.
- **Hosting:** plain static files, deployable to GitHub Pages. No server-side code anywhere in the
  default path.
- **Licensing:** whole work published as GPL-2.0-or-later with complete corresponding source.
- No rollback/prediction, no TypeScript rewrite, no central server before M1 ships.
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

## Progress tracking
Update `PROGRESS.md` at each milestone and whenever context is about to be compacted: checklist,
known issues, next tasks, how to run. Keep it concise and current; it is the handoff document.

## Next milestone
M0: prove the menu renders in a real browser and input works; remove debug probes; then merge
`m0-sdl2-port` into `main`.

## Process rules
- Keep this file short; rewrite rather than append when context grows.
- Record any change of base/path/network/hosting decisions here.
- No new libraries without asking; prefer established, maintained ones.
