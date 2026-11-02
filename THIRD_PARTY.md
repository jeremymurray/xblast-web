# Third-party components and notices

This file lists every third-party component in the repository or linked into the
web build, with its licence and where the licence text lives. Paths are repository
paths; the deployed bundle contains the same notices as `COPYING`, `THIRD_PARTY.md`,
`LICENSE/` and `docs/provenance.md`, with the vendored JavaScript under `vendor/`.
The combined work is distributed under **GPL-2.0-or-later**; see `COPYING` and
`LICENSE/README.md`. Asset-by-asset provenance and checksums are in
`docs/provenance.md`.

## Engine, data and font

| Component | Version | Licence | Where / notice |
|---|---|---|---|
| XBlast TNT engine | 2.10.4 + Debian 2.10.4-6 patches | GPL-2.0-or-later | `engine/`; `engine/COPYING`; `LICENSE/data/xblast-tnt_2.10.4-6_amd64.copyright` |
| XBlast TNT images | Debian 20050106-5 | GPL-2+ | `data/image/{misc,score,explosion,block}`; `LICENSE/data/xblast-tnt-images_20050106-5_all.copyright` |
| XBlast TNT models (`.epm` sprites) | Debian 20050106-6 | GPL-2+ | `data/image/sprite`; `LICENSE/data/xblast-tnt-models_20050106-6_all.copyright` (names Mark Weyer, Oliver Vogel, Bernhard R. Link, Daniela Lipps, Immanuel Halupczok) |
| XBlast TNT levels | Debian 20050106+repack-3 | GPL-2+ | `data/level`; `LICENSE/data/xblast-tnt-levels_20050106+repack-3_all.copyright` |
| XBlast TNT sounds | Debian 20040429-5 | GPL-2+ | `data/sounds/*.raw` (50 effects); `LICENSE/data/xblast-tnt-sounds_20040429-5_all.copyright` |
| XBlast TNT music | Debian 20050106-5 | GPL-2+ | `data/sounds/xbsng1..6.raw` (6 tracks); `LICENSE/data/xblast-tnt-musics_20050106-5_all.copyright` |
| Bitstream Vera font | 1.10 (Debian 1.10-11) | Bitstream Vera licence (permissive, not GPL) | `data/Vera.ttf`; `LICENSE/Bitstream-Vera.txt`; `LICENSE/data/ttf-bitstream-vera.copyright` |

Upstream authors named by the Debian copyright files: Oliver Vogel & others,
Fernando Benites, Kruno Sever, Rhonda D'Vine. The engine also carries the SDL
pointer files below.

### Music: audit limitation

The six music tracks are byte-identical to upstream `musics-2005-01-06.tar.gz`
and to the Debian `xblast-tnt-musics` payload; Debian applies no patches and its
copyright file grants GPL-2+ for all files. **There is no per-track authorship
record upstream** — no composer or individual licence is named for any of the six
files. The project ships them under the package-level GPL-2+ grant and records the
limitation rather than inventing credits. Full hashes: `docs/provenance.md`.

## SDL-derived source files inside the engine

| File | Licence | Text |
|---|---|---|
| `engine/sdl_ppm.c` | LGPL-2.0-or-later (GNU Library GPL v2+) | `LICENSE/LGPL-2.0.txt` |
| `engine/SDL_vkeys.h` | LGPL-2.0-or-later (GNU Library GPL v2+) | `LICENSE/LGPL-2.0.txt` |

These are compatible with GPL-2.0-or-later. The Debian copyright file for the
engine records the same terms. Their headers carry the original Sam Lantinga
copyright.

## Vendored JavaScript (runtime)

| Component | Version | Licence | Files |
|---|---|---|---|
| `@trystero-p2p/nostr` | 0.26.0 | MIT | `web/vendor/trystero/nostr/`; `web/vendor/trystero/LICENSE.trystero` |
| `@trystero-p2p/core` | 0.26.0 | MIT | `web/vendor/trystero/core/`; `web/vendor/trystero/LICENSE.trystero` |
| `@noble/secp256k1` | 3.2.0 | MIT | `web/vendor/trystero/noble/`; `web/vendor/trystero/LICENSE.noble` |

They are vendored unminified with their notices; `scripts/vendor-trystero.sh`
regenerates them and `web/vendor/trystero/README.md` records sources and hashes.
They stay MIT and are not relicensed by inclusion.

## Linked into the web build (via the pinned Emscripten SDK)

The release artifact is built with Emscripten 6.0.13 (`.tool-versions`) and
statically links the following libraries. Versions are those resolved by that
SDK; licence texts are in `LICENSE/third-party/`.

| Component | Version | Licence | Text |
|---|---|---|---|
| Emscripten runtime | 6.0.13 | MIT / NCSA | `Emscripten.txt` |
| musl libc (inside the Emscripten runtime) | 1.2.x (SDK-pinned) | MIT | `musl.txt` |
| SDL2 | 2.32.10 | zlib | `SDL2.txt` |
| SDL2_image | 2.6.0 | zlib | `SDL2_image.txt` |
| SDL2_ttf | 2.20.2 | zlib | `SDL2_ttf.txt` |
| SDL2_mixer | 2.8.0 | zlib | `SDL2_mixer.txt` |
| SDL2_gfx | git 2b147ffe | zlib | `SDL2_gfx.txt` |
| FreeType | 2.14.3 | GPLv2-or-later option (dual FTL/GPLv2) | `FreeType.txt`; GPLv2 in `../COPYING` |
| HarfBuzz | 3.2.0 | Old MIT | `HarfBuzz.txt` |
| libpng | 1.6.59 | libpng-2.0 | `libpng.txt` |
| zlib | 1.3.2 | zlib | `zlib.txt` |
| libogg | 1.3.5 | BSD-3-Clause | `libogg.txt` |
| libvorbis | 1.3.7 | BSD-3-Clause | `libvorbis.txt` |

FreeType is dual-licensed (FTL or GPLv2-or-later). This project elects the
**GPLv2-or-later option**, so the combined work stays GPL-2.0-or-later; its
dual-licence notice is in `FreeType.txt`, but it is included for reference and
is not the elected option (the FTL is compatible with GPLv3, not GPLv2). The
Emscripten output also contains musl libc code, covered by `musl.txt`. Other
runtime pieces are covered by the Emscripten licence text and upstream notices;
they are not vendored here.

## Build-only, not distributed

| Component | Licence | Note |
|---|---|---|
| GNU gettext `m4/*.m4` macros in `engine/m4/` | permissive (FSF unlimited copy/distribute permission) | Autotools macros; the web build uses `build/gen/config.h` and does not run them. `sdl.m4` (SDL's autoconf macro) carries no separate grant and is build-only. |
| autotools generated files (`configure`, `aclocal.m4`, …) in `engine/` | GPL-2+ as part of the engine distribution | Not used by `scripts/build-web.sh`. |
| Node.js bundled with the Emscripten SDK | MIT | Build tool only; not shipped. |
| Python standard library | PSF licence | Test and helper scripts; not shipped in the web build. |

## Upstream files that are not compiled for web

`engine/time.c` (Wu Yongwei's `timeval.h`), `engine/try.c` and
`engine/randomlib.c` carry no separate licence grant in their headers. They are
part of the GPL-2+ upstream distribution. `time.c` is guarded by `#ifdef W32`,
`try.c` is a standalone scratch program, and none of the three is compiled by
`scripts/build-web.sh`. No GPL-2-only component was found.

## No warranty

The software is provided "as is", without warranty of any kind, as stated in
GPLv2 sections 11 and 12 and in the upstream notices. See `COPYING`.
