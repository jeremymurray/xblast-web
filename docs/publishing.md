# Publishing to public GitHub — M4 checklist

Status: planning. **Do not publish the repository or a Pages build until the blocking items
below are checked.** This is an engineering/licensing checklist, not legal advice; if a point is
uncertain, exclude the asset or get qualified advice.

Scope: publish the 0.4.0 source repository and the static web build, with no backend.

## 1. License decision (blocking)

- [x] **Decision (2026-11-01): keep GPL-2.0-or-later.** It matches upstream, is already
      open source, and remains compatible with GPLv2-only downstream code. GPL-3.0-or-later is
      feasible but not needed; revisit only before accepting outside contributions.
- [ ] Record the decision and the audit table in this file.
- [ ] Confirm no GPL-2-only code, no non-free asset, and no unreviewed music track is included.
- [ ] Decide the contribution policy (inbound=outbound / DCO is enough for GPL; no CLA needed).
- [ ] Do this **before** accepting outside contributions.

### Current evidence

- Engine: GPL-2+ headers. `bot.c` and `xbsndsrv.c` say "either version 2 or later".
  `sdl_ppm.c` and `SDL_vkeys.h` are LGPL-2+; compatible.
- `engine/m4/*.m4` gettext macros are GPL-3+ build scripts; not part of the wasm runtime.
- Data: images/levels/sounds are GPL-2+; `data/image/sprite/*.epm` are model sprites from the
  GPL-2+ `xblast-tnt-models` package. `data/Vera.ttf` is Bitstream Vera (not GPL).
- **No music tracks are currently bundled.** The Debian `xblast-tnt-musics` package exists and its
  Debian copyright file says GPL-2+, but we do not ship its files. The current README/AGENTS
  "music" claim is wrong and must be fixed.
- Trystero/noble: MIT. Emscripten runtime/SDL2/image/ttf/mixer/gfx: permissive
  (MIT/NCSA/zlib; the Emscripten SDL2_gfx port is zlib).
- GPL-2+ permits distribution of the combined work under GPL-3.0-or-later. It does **not**
  relicense upstream code: upstream remains available under GPL-2+. GPL-3 is not compatible with
  GPL-2-only components; none were found, but re-audit if assets/code change.

## 2. Top-level licence and notices (blocking)

- [x] Add a top-level `COPYING` (GPLv2 text; the project is GPL-2.0-or-later). `LICENSE/` is
      the directory of Debian/third-party copyrights, not a licence file; GitHub now detects
      `COPYING`.
- [ ] Keep `engine/COPYING` (GPLv2) for the upstream engine and explain the combined-work licence
      in `NOTICE`/`README`.
- [ ] Add `NOTICE` or `THIRD_PARTY.md` covering:
      engine (GPL-2+), Debian patches, data packages, model sprites, Bitstream Vera,
      Trystero/noble (MIT), SDL2/image/ttf/mixer/gfx and Emscripten (permissive),
      SDL_ppm/SDL_vkeys (LGPL-2+), gettext m4 (build-only).
- [ ] Add the LGPL-2+ text for the SDL-derived files.
- [ ] Keep the vendored Trystero/noble licence files; do not strip notices when vendoring or
      minifying.
- [ ] If GPL-3 is chosen, add the GPLv3 text and keep a GPLv2 copy for the upstream engine;
      update README/FEASIBILITY/AGENTS and any new source headers with the chosen SPDX id.
- [ ] Add a clear "no warranty" statement and the GPL source-offer pointer to the README.

## 3. Asset provenance and music (blocking)

- [ ] Record every `data/` tree against its Debian package/copyright:
      `data/image` (images + `.epm` models), `data/level`, `data/sounds`, `data/Vera.ttf`.
- [ ] Confirm the current tree contains **no** `data/musics` or full music tracks.
- [ ] Correct README/AGENTS/PROGRESS: images, levels, sounds and model sprites are bundled;
      music is not.
- [ ] Decide whether to keep `LICENSE/data/xblast-tnt-musics_*.copyright` as a reference notice
      or remove it; do not imply music is bundled.
- [ ] If `xblast-tnt-musics` is added later, audit each track and its upstream authorship and
      licence. The Debian package copyright is evidence, not a blanket substitute for that audit.
- [ ] Confirm the `.epm` model sprite artists are covered by the models copyright file.
- [ ] Store a provenance/checksum note (package versions, sources, hashes) with the data.
- [ ] Do not add any asset whose licence is unclear or non-free.

## 4. Complete corresponding source and build

- [ ] Public repository includes engine + Debian patches + web shell/transport + scripts + data +
      build instructions.
- [ ] Pin the toolchain (`emsdk 6.0.13` in `.tool-versions`) and document the build command.
- [ ] Publish source alongside the Pages/build artifact; GPL requires complete corresponding
      source, not just a link from the minified wasm.
- [ ] Include the source archive and checksums with the GitHub release.
- [ ] If build targets are added (6p/16p/lite/debug), document which source and flags produce which
      artifact.
- [ ] No proprietary build dependency; confirm Emscripten/SDL licences are included.

## 5. Repository hygiene and security

- [ ] Confirm ignored: `.downloads/`, `web/dist/`, `build/out/`, `web/turn.json`, local configs.
- [ ] Scan the full git history for secrets, TURN credentials, tokens, private URLs and accidental
      large downloads. `.downloads/` is ignored, but verify history too.
- [ ] No telemetry, analytics, backend or hidden network calls; document the public Nostr relay
      and optional TURN dependencies.
- [ ] Choose the public repo name/description, add topics, and verify GitHub detects the licence.
- [ ] Add `CONTRIBUTING.md` and (optionally) `SECURITY.md`; state the AI-attribution policy and
      the GPL inbound=outbound rule.
- [ ] Add CI for the build and JS transport tests; mark netplay tests (internet + Chrome) as
      optional/manual so public-relay flakiness does not block every PR. CI must **not** upload
      the variant build artifacts (`16p`, `debug`, `lite`, `small`, `mini`) — build/test only.
- [ ] Verify GitHub Pages serves `.wasm` as `application/wasm`, `.data` correctly, and does not
      ship `turn.json`.

## 6. Public release steps

- [ ] Create the public repository and push `main` plus the annotated `0.4.0` tag.
- [ ] Create the `0.4.0` GitHub release with source archive, build artifact, checksums and notes.
- [ ] Deploy Pages; smoke-test solo, host/join, host takeover, room codes and a real match.
- [ ] Verify the public build has no TURN credentials and no local config.
- [ ] Publish the source-offer/source-link from the Pages build and README.
- [ ] Re-check the release artifact against this checklist after upload.

## 7. Open decisions

1. **Licence: decided GPL-2.0-or-later (2026-11-01).**
   GPL-2+ matches upstream and is maximally compatible with GPLv2-only downstream code; GPLv3
   remains feasible but is not needed. Revisit only before accepting outside contributions.
2. **Ship music later or never?** Current build ships no music; keep the separate music package
   out until its tracks are audited.
3. **Public build targets:** default six-player first; 16-player/lite/debug are M5 work.
