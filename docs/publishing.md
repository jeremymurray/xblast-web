# Publishing to public GitHub — M4 checklist

Status as of 2026-11-02: **published.** Source:
<https://github.com/jeremymurray/xblast-web>; site:
<https://jeremymurray.github.io/xblast-web/>; release `0.5.0` with source archive, web
bundle and `SHA256SUMS`. `0.4.0` remains the historical M3 tag. The 0.5.0 tag's CI check
is red from a transport-harness race fixed on `main` after the tag; the artifact and site
are unaffected (see §8).

This is an engineering/licensing checklist, not legal advice. If a point is
uncertain, exclude the asset or get qualified advice.

Scope: publish the 0.5.0 source repository and the static web build, with no backend.

## 1. Licence decision (blocking)

- [x] **Decision (2026-11-01): keep GPL-2.0-or-later.** It matches upstream, is already
      open source, and remains compatible with GPLv2-only downstream code. GPL-3.0-or-later
      is feasible but not needed; revisit only if outside contributions are ever opened.
- [x] Record the decision and the audit table in this file (below).
- [x] Confirm no GPL-2-only code, no non-free asset, and no unaudited music track.
- [x] Decide the contribution policy (2026-11-01): **this is a fun side project and is not
      accepting outside contributions or issues at this time.** The README and
      `CONTRIBUTING.md` say so. Inbound=outbound GPL-2.0-or-later, DCO sign-off and the AI
      disclosure rule are written down for if that ever changes; no CLA is needed.
- [x] Done **before** accepting outside contributions (none are being accepted).

### Evidence (audited 2026-11-01)

- **Engine:** GPL-2+ headers. `bot.c` and `xbsndsrv.c` say "either version 2 or
  later". `sdl_ppm.c` and `SDL_vkeys.h` are LGPL-2.0-or-later; compatible.
  `engine/m4/*.m4` are permissive build macros (FSF unlimited copy/distribute
  permission), not part of the wasm runtime; `sdl.m4` has no separate grant and is
  build-only.
- **Data:** every file in `data/` was compared byte-for-byte (SHA-256) with both the
  Debian binary package and the upstream source tarball. All match; no edits.
  Full table: `docs/provenance.md`.
  - images, levels, sounds and model sprites: GPL-2+ from the Debian packages;
  - **music: six tracks are bundled** (`xbsng1..6.raw`, 8.18 MiB) and audited; the
    Debian package and upstream tarball grant GPL-2+. No per-track authorship
    record exists upstream; the limitation is stated in `THIRD_PARTY.md` and
    `docs/provenance.md`.
  - `data/Vera.ttf` is Bitstream Vera (permissive, not GPL), unmodified, name kept.
- **Vendored JS:** Trystero 0.26.0 and `@noble/secp256k1` 3.2.0, MIT.
- **Linked toolchain:** Emscripten 6.0.13 (MIT/NCSA), musl libc (MIT), SDL2
  2.32.10, SDL2_image 2.6.0, SDL2_ttf 2.20.2, SDL2_mixer 2.8.0, SDL2_gfx
  2b147ffe (zlib), FreeType 2.14.3 (dual FTL/GPLv2; the project elects GPLv2),
  HarfBuzz 3.2.0, libpng 1.6.59, zlib 1.3.2, libogg 1.3.5, libvorbis 1.3.7.
  Texts in `LICENSE/third-party/`. No proprietary dependency.
- **GPL-2+ permits** distribution of the combined work under GPL-3.0-or-later. It
  does **not** relicense upstream code, which remains available under GPL-2+.
  GPL-3 is not compatible with GPL-2-only components; none were found.

### Audit summary

| Item | Result |
|---|---|
| GPL-2-only code | none found |
| Non-free asset | none found |
| Music present? | yes, 6 tracks, GPL-2+, hash-audited |
| Unreviewed/unknown asset | none |
| Licence texts for linked libs | complete in `LICENSE/third-party/` |
| Complete source for the build | repository + `git archive` source tarball |

## 2. Top-level licence and notices (blocking)

- [x] Top-level `COPYING` (GPLv2 text; project is GPL-2.0-or-later). `LICENSE/` is
      the directory of notices, not a licence file; GitHub detects `COPYING`.
- [x] Keep `engine/COPYING` (GPLv2) and explain the combined-work licence in
      `README.md`, `LICENSE/README.md` and `THIRD_PARTY.md`.
- [x] `THIRD_PARTY.md` covers engine, Debian patches, data packages, model sprites,
      music, Bitstream Vera, Trystero/noble, SDL2 stack, Emscripten, LGPL files and
      build-only gettext/autotools.
- [x] LGPL-2.0 text for the SDL-derived files: `LICENSE/LGPL-2.0.txt`.
- [x] Bitstream Vera notice: `LICENSE/Bitstream-Vera.txt` plus the Debian copyright.
- [x] Vendored Trystero/noble licence files kept; nothing strips notices.
- [x] GPL-3 not chosen, so no GPLv3 text is needed.
- [x] "No warranty" statement and GPL source-offer pointer in `README.md`; every
      build ships `COPYING`, `THIRD_PARTY.md`, `LICENSE/`, `docs/provenance.md` and
      `SOURCE.txt`, and the landing screen links to them.

## 3. Asset provenance and music (blocking)

- [x] Every `data/` tree mapped to its Debian package/copyright and upstream source
      archive in `docs/provenance.md`: images, `.epm` models, levels, sounds,
      music, Vera.ttf.
- [x] Confirmed the tree contains no unexpected media: no `data/musics` directory,
      no video; the six tracks live with the sounds because the engine loads them
      from `sounds/`.
- [x] README/AGENTS/PROGRESS/FEASIBILITY corrected: music **is** bundled.
- [x] Kept `LICENSE/data/xblast-tnt-musics_*.copyright`; it now documents a shipped
      package, not a reference to an absent one.
- [x] Music audit done per file by hash; the no-per-track-attribution limitation is
      recorded honestly rather than papered over.
- [x] `.epm` model sprite artists covered by the models copyright file.
- [x] Provenance/checksum note stored: `docs/provenance.md`.
- [x] No asset with unclear or non-free licence.

## 4. Complete corresponding source and build

- [x] Public repository will include engine + Debian patches + web shell/transport +
      scripts + data + build instructions.
- [x] Toolchain pinned (`emsdk 6.0.13` in `.tool-versions`) and documented.
- [x] Source published with the build: the repository is the source; `make-release.sh`
      produces a `git archive` source tarball of the tagged tree, and Pages serves
      `SOURCE.txt` naming the commit and repository.
- [x] Source archive and checksums included in the GitHub release
      (`.github/workflows/release.yml`).
- [x] Build targets documented, including which flags produce which artifact
      (`README.md`, `scripts/build-web.sh --list`); variant artifacts stay local.
- [x] No proprietary build dependency; Emscripten/SDL/licence texts included.

## 5. Repository hygiene and security

- [x] Ignored: `.downloads/`, `web/dist/`, `web/dist-*/`, `build/out/`,
      `build/release/`, `web/turn.json`, local configs, `.superpowers/`.
- [x] Full history scanned for secrets, tokens, private keys, TURN credentials and
      accidental downloads. Result: no real secrets. Only placeholders
      (`replace-with-a-long-random-secret`, `pass@relay.example.org`) in docs; the
      largest blobs are the six music tracks. Local absolute paths appeared in two
      early FEASIBILITY revisions and are removed from the current tree; they are
      not secrets. Git author identity is a personal address — see open decisions.
- [x] No telemetry, analytics, backend or hidden network calls. The public Nostr
      relay dependency and optional TURN are documented in `README.md` and
      `docs/hosting.md`.
- [x] Public repo `jeremymurray/xblast-web`: description "A browser port of XBlast TNT",
      Issues and Discussions disabled, GitHub detects GPL-2.0, topics can be added later.
- [x] `CONTRIBUTING.md` and `SECURITY.md`: no outside contributions or issues for now,
      fork guidance, AI-attribution policy, and a best-effort private security path.
- [x] CI: build + artifact checks + JS transport tests (`.github/workflows/ci.yml`);
      the transport job retries once on relay failure, and netplay is
      `workflow_dispatch` only so relay flakiness does not block PRs. CI never uploads
      variant artifacts; Pages uploads only `web/dist`.
- [x] GitHub Pages serves `.wasm` as `application/wasm`, returns `.data` successfully,
      has no `turn.json`, and the workflow smoke test passed after deploy.

## 6. Public release steps (human-gated)

1. [x] Public repository name/description/topics and author identity decided by the
       maintainer; Issues and Discussions disabled.
2. [x] Public repository created; `main`, `0.4.0` and `0.5.0` pushed.
3. [x] GitHub Pages enabled with **GitHub Actions** as the source; the Pages workflow
       and its smoke test pass.
4. [x] `0.5.0` release published with the source archive, web bundle and `SHA256SUMS`.
       The notes were corrected after the first upload (the workflow captured the commit
       message instead of the tag annotation; fixed in `release.yml`).
5. [x] Public site loads, boots to the game menus and serves all notices; the Pages smoke
       test passes. A human host/join/takeover match on the public URL remains the final
       manual acceptance step.
6. [x] The public build has no TURN credentials or local config; `SOURCE.txt` names
       commit `a38f966` and the public repository.
7. [x] Release artifact and site re-checked against this checklist.

## 7. Open decisions

1. **Licence: decided GPL-2.0-or-later (2026-11-01).** Revisit only if outside
   contributions are ever opened.
2. **Music: keep and audit (2026-11-01).** Six tracks ship; evidence and the
   no-per-track-attribution limitation are recorded. If a future build drops
   `data/sounds` (the `lite` targets), do not claim music is present.
3. **Public build target:** `release` (six players) only. 16-player/lite/debug
   remain local M5 work and must not be uploaded by CI.
4. **Public name and git identity (resolved 2026-11-02):** published as
   `jeremymurray/xblast-web` with the maintainer's personal author address. History
   was not rewritten; this is accepted for a hobby repo.

## 8. Post-publication check (2026-11-02)

- Repo public, default branch `main`, GPL-2.0 detected, Issues and Discussions disabled.
- Pages: `https://jeremymurray.github.io/xblast-web/`; `.wasm` →
  `application/wasm`, `.data` HTTP 200, `turn.json` HTTP 404, notices and
  `docs/provenance.md` HTTP 200.
- `SOURCE.txt`: repository URL plus commit `a38f966`; built from the tag's tree.
- Release `0.5.0`: source tarball 11.2 MB, web zip 12.4 MB, `SHA256SUMS`; notes match
  the annotated tag after correction.
- Public build boots to the XBlast menus; the game loads ~19 MB on first click.
- Known red check: the `0.5.0` tag's **CI** run failed because the transport harness
  checked `XBNet` before `net.js` finished importing. Fixed on `main` and released as
  **0.5.1** (wait for `ready`/`done`, and treat module failure as done); 0.5.0 is not
  moved because it is public. The build and site were unaffected. The known
  public-relay `full` flake remains, mitigated by per-scenario retries
  (`XB_TEST_RETRIES=2` in CI).
