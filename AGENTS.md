# xblast-web — project agent notes

## Goal
Browser-playable XBlast TNT with peer-to-peer multiplayer, no backend, publicly publishable under
GPL-2.0-or-later.

## Decisions (durable)
- **Base code:** `/Users/murray/Projects/sourceforge/xblast/xblast-2.10.4` (SDL1.2 build),
  vendored into this repo.
- **Assets/data:** Debian `xblast-tnt-images`, `xblast-tnt-levels`, `xblast-tnt-sounds` (GPL-2+).
- **Port path:** Emscripten + `sdl12-compat` + Asyncify; keep the C engine and the `gui.h` seam.
- **Network:** WebRTC star, host = authoritative game server. Two DataChannels: reliable-ordered
  for control/level/chat, unreliable-unordered for per-frame actions. Map onto `socket.h`.
- **Lobby/signalling:** Trystero (serverless room codes). TURN still required for some NATs;
  relay mode is an optional fallback, never the default.
- **Licensing:** whole work published as GPL-2.0-or-later with complete corresponding source.
- No rollback/prediction, no TypeScript rewrite, no central server before M1 ships.

## Read first
`FEASIBILITY.md` — architecture, netcode, risks, milestones.

## Next milestone
M0 spike: pin toolchain via `asdf` `.tool-versions`, install `emcc`, build the SDL target with
Asyncify, render a menu and run one single-player round on canvas. Report blockers before porting.

## Process rules
- Keep this file short; rewrite rather than append when context grows.
- Record any change of base/path/network decisions here.
- No new libraries without asking; prefer established, maintained ones.
