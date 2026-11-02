# XBlast in the browser with P2P multiplayer — feasibility report

Date: 2026-10-31
Status: M2 done (two-player P2P, release 0.3.0)
Target: a publicly publishable, browser-playable XBlast TNT with peer-to-peer multiplayer
Source: XBlast TNT 2.10.4 (upstream release + Debian patches), data from the Debian GPL-2+ packages

---

## 1. Verdict

**Feasible, medium-high effort.** Nothing in the engine blocks a browser port. The hard parts are
not rendering or simulation — they are (a) the engine's blocking main loop, (b) replacing the
socket layer with WebRTC, and (c) building the lobby/signalling layer that the 2006 game
never had. Budget **6–10 weeks of focused work for one experienced developer** to reach a solid
2–6 player P2P release, plus a 1–2 day de-risking spike first.

Confidence: **high** on architecture and netcode analysis (read the source), **medium** on
build/port effort (no `emcc` build was attempted — see §8).

---

## 2. What we are actually porting

| | XBlast TNT |
|---|---|
| Version | 2.10.4 (+ Debian patches, maintained to 2026) |
| Code | ~80.8k lines C/H (69.9k `.c`) |
| Backends | X11 **and** SDL 1.2 |
| Assets | Debian GPL-2+ packages (~28 MB raw: images, levels, sounds) |
| Build | autotools, SConstruct, Windows |

We use the 2.10.4 tree unchanged as the engine, because it already has an SDL backend (6.6k lines,
a much better seam than X11), current compiler fixes, and Debian's asset packages give clean
licensing.

### Architecture, and why it suits a port

- **Clean GUI seam.** `gui.h` declares ~60 functions (`GUI_DrawSprite`, `GUI_LoadPixmap`,
  `GUI_WaitEvent`, …). All drawing/input/audio goes through it. The SDL backend is a set of
  `sdl_*.c` files that can be swapped wholesale.
- **SDL usage is shallow.** Mostly `SDL_BlitSurface`, `SDL_FillRect`, `SDL_UpdateRect`,
  `SDL_MapRGB`, `SDL_SetColorKey`, plus SDL_ttf and SDL_mixer. `configure.in` demands SDL_gfx but
  the code barely uses it. This is close to a worst-case-friendly Emscripten target.
- **Simulation is separate from rendering** (`bomb.c`, `player.c`, `bot.c`, `map.c`, `action.c`),
  and rendering is 2D tile/sprite blitting at a fixed logical resolution.
- **Deterministic RNG** (`random.c`, Marsaglia/Zaman) with the server broadcasting the seed
  (`S2C_SendRandomSeed`), and almost no floating point in simulation. Same wasm binary on all
  clients ⇒ identical frames. This is the single most important enabler.
- **Inputs are already compact.** `action.h` encodes a player's intent into a small bitmask; the
  whole game is driven by per-frame action masks.

### Netcode today (host-authoritative relay, 20 Hz)

- `FRAME_TIME 50`, `TIME_STEP 48`, `GAME_TIME = 60*48 + 8` ⇒ 20 logic ticks/second, ~60 s rounds.
- **TCP** control stream (join, level sync, config, chat, player list).
- **UDP** action datagrams: 2-byte game time + 4-byte mask + up to 6 actions, `MAX_DGRAM_SIZE 255`.
- Host inserts all players' actions for frame *n*, then clients replay frame *n* and **block until
  the host's frame arrives**. No prediction, no rollback. Loss ⇒ `XBDI_LOSS` + repeat; `LINK_LOST`
  after 10 s.
- Bandwidth: ~20 B/frame/peer ⇒ **~400 B/s per client at 20 Hz**. Trivial by modern standards.

This maps directly onto a **WebRTC star**: host browser = game server. One reliable-ordered
DataChannel for control/level/chat, one unreliable-unordered DataChannel for per-frame actions.
No server-side simulation is needed.

---

## 3. Performance and stability

**Will it run?** Yes, comfortably. The game is a 2D blitter with a 20 Hz logic tick and a ~60 s
round; the heaviest work is sprite composition, not physics. Client-side CPU in wasm should be a
few percent of a core; the real cost is the browser compositor and the occasional large sprite blit.

**Stability risks, in order:**

1. **Blocking loops.** `GUI_WaitEvent` and `game_client.c:WaitForServerEvent` block, and the client
   waits for the host frame each tick. Browsers cannot block the main thread. Mitigations:
   - **Asyncify** (Emscripten, works everywhere, ~1.5–2× code size and some CPU overhead), or
   - **JSPI** (cleaner, but still not universal), or
   - run the engine in a **Web Worker** with `OffscreenCanvas` and drive it with a message pump.
   Recommended: Asyncify first (smallest code change), keep the worker option as a follow-up.
2. **Tab backgrounding.** The host's tab throttles timers. `requestAnimationFrame` stops entirely
   in a hidden tab. Mitigations: run the loop in a Worker (workers are throttled less, and WebRTC
   keeps the context alive), `navigator.wakeLock`, an audible/WebRTC keepalive, and a clear "don't
   minimise the host tab" warning. Also: **host migration** is not in the engine and is the biggest
   missing robustness feature.
3. **No prediction.** On a 60–120 ms RTT link, inputs feel ~1 frame late but the game's own 20 Hz
   cadence and block-until-frame model hide much of it. Do **not** add rollback initially; the
   deterministic sim makes it possible later if needed.
4. **Reliability of the action channel.** Unreliable-unordered is right (matches UDP), but WebRTC
   can drop bursts under congestion. The engine already repeats the last action and has
   `XBDI_LOSS`; verify the repeat window is generous enough for 100–200 ms bursts.
5. **Desync.** Only possible if a client's wasm diverges (different build, uninitialised memory,
   locale-dependent formatting). Add a per-round hash of game state to detect it (§7).
6. **Audio.** SDL_mixer → WebAudio needs a user gesture to start; the 5 music tracks are ~7.3 MB of
   raw PCM and must be converted (see §4).

**Measured/hard numbers from the source:** 20 ticks/s, 48 sub-ticks, ~400 B/s upstream per client,
6 players max per action datagram, 10 s link timeout, ~4 KB per level file, 1216 levels.

---

## 4. Assets and delivery size

Current raw data is far too big to ship as-is, but shrinks well:

| Data | Raw | Plan | Est. shipped |
|---|---|---|---|
| Music | 7.3 MB raw PCM (5 tracks) | OGG/Opus, streamed | 0.8–1.5 MB |
| SFX | 56 `.raw` files, ~3.7 MB | short WAV/WebAudio buffers | < 250 KB |
| Images | 12 MB (`sprite` 8.6 MB, `block` 2.3 MB, …) | pack to PNG atlas / WebP | 1.5–3 MB |
| Levels | 4.8 MB (1216 `.xal`) | gzip/br bundle, lazy per pack | 300–600 KB |
| Fonts | `Vera.ttf` | keep or subset | ~50 KB |

Initial load can be **~3–4 MB**, with music and level packs lazy-loaded. The `.epm`/`.pbm`/`.ppm`
sprite formats are custom and already have loaders in `sdl_sprite.c`/`sdl_pixmap.c`; converting
offline to atlases is an optimisation, not a requirement — decoding them in wasm also works.

---

## 5. Implementation paths

### Path A — Emscripten + SDL1.2 (via `sdl12-compat`) + WebRTC bridge  ★ recommended
Keep the C engine. `sdl12-compat` on top of SDL2 is what Emscripten supports well. Replace
`sdl_socket.c` with a WebRTC-backed implementation of the existing socket API in `socket.h`;
keep TCP semantics on the reliable channel and datagram semantics on the unreliable one.

- Pros: least rewriting, preserves gameplay exactly, all levels/bots/menus come for free, GPL
  obligations straightforward.
- Cons: Asyncify overhead, SDL_mixer/SDL_ttf via Emscripten ports, socket shim must model both
  stream and datagram semantics, `select()`-style polling needs care.
- Effort: **6–9 weeks**.

### Path B — Emscripten + custom canvas/WebAudio backend
Same C engine, but write a `web_*.c` backend against `gui.h` (canvas2d + WebAudio + key/pointer
events) instead of using SDL. Worker + `OffscreenCanvas` to avoid Asyncify.

- Pros: no SDL dependency, much smaller wasm, no Asyncify, modern input/touch naturally.
- Cons: reimplement ~60 GUI functions and the event pump; more up-front work; easy to miss
  quirks (colour keys, sprite masks, scaling).
- Effort: **8–12 weeks**.

### Path C — TypeScript rewrite, reuse only data
Reimplement the sim and rendering in TS/WebGL, borrow assets and level format.

- Pros: best long-term maintainability, easiest mobile/touch, smallest payload.
- Cons: reimplementing bombs, chains, bots, menus, 1200 levels' quirks is a large, bug-prone
  effort; loses the "same game" guarantee. Only worth it if the goal is a modernised product.
- Effort: **4–6 months**.

### Path D — Keep a relay server
Port as in A, but run the authoritative host on a small Node/Go relay instead of a browser peer.

- Pros: no NAT problems, no host backgrounding, easy matchmaking, spectators.
- Cons: contradicts the "no backend" requirement; still worth keeping as an **optional** fallback
  mode for players behind symmetric NAT (see §7).

### Signalling without a backend
WebRTC needs signalling. Options:
- **Trystero** (Nostr/MQTT/BitTorrent/IPFS/Supabase/Firebase strategies) — serverless lobby keyed
  by a room code; no infrastructure to run.
- **Manual copy/paste of SDP** — 100% serverless, no dependencies, clunky.
- A tiny static signalling relay (Cloudflare Worker/Durable Object) — still "a backend", but a
  trivial one, and useful as TURN-adjacent infrastructure.

Note: **TURN is still required for some NAT pairs.** Plan for a public/free TURN or a "host your
own TURN" note; without it, some players simply cannot connect. This is a hard constraint of
browser P2P, not of XBlast.

---

## 6. Recommendation

**Path A**, staged:

- **Milestone 0 — Spike (1–2 days).** Get `emcc` + `sdl12-compat` building the unmodified
  2.10.4 SDL build to a canvas, with Asyncify on. Success criterion: menu renders and a
  single-player round runs. This retires the largest unknown.
- **M1 — Single-player on the web.** Local game, keyboard, audio, all levels, bots. Ship as a
  static site. (~2–3 weeks)
- **M2 — Two-player P2P.** Host/join by room code via Trystero; reliable control channel,
  unreliable action channel; deterministic-seed check. (~2–3 weeks)
- **M3 — Full multiplayer.** 6 players, chat, level/config menus, reconnection, desync detection,
  host-background warning, mobile/touch controls. (~2–4 weeks)
- **M4 — Polish.** Asset pipeline/compression, loading screen, PWA/offline, optional TURN and
  optional relay fallback. (ongoing)

Do **not** attempt rollback netcode, a new level editor, or a rewrite before M1 ships.

---

## 7. Missing features and gaps

> **Superseded at M2 (0.3.0):** the lobby UI, WebRTC transport shim and lobby
> lifecycle listed below are implemented; see `PROGRESS.md` for current status.
> This section is kept as the original M1 gap analysis.

Engine-level (must add):
- **Lobby/matchmaking UI** — no room codes, player discovery, or "waiting for players" flow for
  web peers. The existing central-server client (`central.c`) is obsolete; don't revive it.
- **WebRTC transport shim** — `socket.h` has stream + datagram APIs; map them onto two
  DataChannels, including the existing `select`/poll and timeout behaviour.
- **Lobby lifecycle** — host leaving currently kills the game; no reassignment.
- **Reconnection / resume** — join is all-or-nothing.
- **Desync detection** — cheap per-round state hash exchanged and compared.
- **Background-tab handling** — warning, wake lock, worker-based loop.
- **Touch/mobile controls** — virtual d-pad + bomb button; menus need pointer input.
- **Audio unlock** — gesture-gated WebAudio start.
- **Chat** — engine has `chat.c`, but the web lobby needs its own UI/transport.
- **NAT fallback** — TURN config and a clear error path when P2P fails.

Nice-to-have:
- Spectators (trivial: another channel that receives frames but sends no actions).
- Replays/demos (`cfg_demo.c` already exists — expose as shareable recordings).
- Gamepad API support (`sdl_joystick.c` exists).
- Level editor (the X11 editor is `menu_edit.c`; heavy, defer).
- Persistent stats/profile (engine has `cfg_stat.c`; would need storage).
- Server-relay mode for hostile NATs.
- PWA/offline install.

---

## 8. Licensing and publication

- **Code:** GPL-2.0-or-later. `sdl_ppm.c` and `SDL_vkeys.h` are LGPL-2+ (compatible).
- **Assets:** Debian's `xblast-tnt-images`, `xblast-tnt-levels`, `xblast-tnt-sounds` are
  **GPL-2+** — safe to bundle in a GPL web app.
- **Obligation:** publishing the web build requires offering the **complete corresponding source**
  (engine + your web/JS glue + build scripts) under GPL-2+. Linking to a source repo alongside the
  download satisfies this; also keep the licence notices and the "no warranty" text.
- **Emscripten runtime/`sdl12-compat`** are permissive (MIT/zlib/BSD) and compatible.
- **Trystero** is MIT. **Do not** bundle non-GPL-compatible JS into the same work without checking.
- Recommendation: publish the whole thing as GPL-2.0-or-later, source on a public forge, with a
  `NOTICE`/`COPYING` bundling the Debian asset copyright files.

---

## 9. Unknowns / confidence gaps

1. **No build attempted.** `emcc` is not installed, Docker is unavailable, and Homebrew lacks an
   SDL1.2 dev stack. SDK availability for `sdl12-compat` + Emscripten ports is the main risk —
   this is exactly what Milestone 0 tests.
2. **Asyncify vs JSPI** — code-size and CPU impact unmeasured.
3. **Real-world P2P latency** for a 20 Hz block-until-frame loop, especially on mobile networks.
4. **Exact asset licensing** of every file in the Debian packages — resolved by the
   2026-11-01 hash-level audit in `docs/provenance.md`; re-audit if assets change.
5. **Browser tab-throttling behaviour** for Worker-hosted WebRTC loops in current Safari/Chrome.

---

## 10. Handoff prompt for a fresh session

```
Project: xblast-web (the current working directory; see README.md)
Goal: play XBlast TNT (GPL-2+) in the browser with P2P multiplayer, no backend.
Base: XBlast TNT 2.10.4 + Debian patches, vendored in engine/.
Data: Debian xblast-tnt-images/-levels/-sounds/-models/-musics (GPL-2+) plus Vera.ttf;
      provenance and checksums in docs/provenance.md.
Plan: Path A — Emscripten + a direct SDL2 backend (no sdl12-compat), keep the engine,
replace socket.h with two WebRTC DataChannels (reliable control, unreliable actions),
lobby via vendored Trystero. M3 and 0.4.0 are done.
Read AGENTS.md and PROGRESS.md first; the publication checklist is docs/publishing.md.
```

---

## Appendix — key files

| Concern | Files |
|---|---|
| GUI seam | `gui.h`, `sdl_*.c` |
| Socket seam | `socket.h`, `sdl_socket.c` |
| Client frame sync | `game_client.c` (`WaitForServerEvent`) |
| Host loop | `game_server.c`, `server.c` |
| Action datagrams | `com_dgram.c`, `com_dg_client.c`, `com_dg_server.c` |
| Determinism | `random.c`, `action.h` |
| Timing constants | `xblast.h` (`FRAME_TIME`, `TIME_STEP`, `GAME_TIME`) |
| Build | `configure.in`, `Makefile.am` |
