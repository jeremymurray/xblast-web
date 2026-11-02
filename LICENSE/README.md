# Licence files

The combined work is distributed under **GPL-2.0-or-later**. This directory collects
the notices and licence texts for everything it contains. `THIRD_PARTY.md` at the
repository root is the readable index; this file explains the layout.

| Path | What it covers |
|---|---|
| `../COPYING` | GNU General Public License v2, the base text for GPL-2.0-or-later. |
| `../engine/COPYING` (source tree) | Upstream copy of GPLv2 kept with the vendored XBlast TNT engine; the source archive carries it. |
| `LGPL-2.0.txt` | GNU Library General Public License v2 (LGPL-2.0), for `engine/sdl_ppm.c` and `engine/SDL_vkeys.h` (LGPL-2.0-or-later). |
| `Bitstream-Vera.txt` | Bitstream Vera font licence, for `data/Vera.ttf`. |
| `data/*.copyright` | Debian copyright files for the engine and each data package (images, levels, sounds, models, music, font). These name the upstream authors and the GPL-2+ grant. |
| `third-party/` | Licence texts for the SDL stack, FreeType, HarfBuzz, libpng, zlib, libogg, libvorbis and the Emscripten runtime linked into the web build. |
| `../web/vendor/trystero/LICENSE.*` | MIT licences for the vendored Trystero and noble JavaScript. |

## Why some texts are GPLv2 and some say "or later"

- Upstream XBlast TNT is GPL-2-or-later, and the Debian data packages are GPL-2+.
  The combined work is offered as GPL-2.0-or-later: recipients may take it under
  GPLv2 or any later version. `COPYING` contains GPLv2 because that is the text
  the upstream distribution carries and the most restrictive option available.
- `engine/sdl_ppm.c` and `engine/SDL_vkeys.h` come from SDL and are offered under
  the GNU Library General Public License v2 **or later**. Their text is
  `LGPL-2.0.txt`. This is compatible with GPL-2.0-or-later.
- The Bitstream Vera font is **not** GPL. It keeps its own permissive licence,
  which requires the copyright/permission notice to travel with the font and
  requires modified fonts to be renamed. `data/Vera.ttf` is unmodified.

## Licence texts for linked build dependencies

The release `.wasm` statically links SDL2, SDL2_image, SDL2_ttf, SDL2_mixer,
SDL2_gfx and their dependencies from the pinned Emscripten SDK. Their licences
are permissive (zlib, MIT/NCSA, BSD-3-Clause, libpng-2.0, FreeType licence); the
texts are copied into `third-party/`. Exact versions are listed in
`THIRD_PARTY.md`. The toolchain itself is not redistributed.

## What is not here

No file is relicensed by being included. MIT, zlib, BSD and Bitstream-licensed
components remain under their own terms; GPL-2+ components remain available from
upstream under GPL-2+.
