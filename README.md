# xblast-web

XBlast TNT (the classic Bomberman-style game) running in the browser, with
peer-to-peer multiplayer and no game server.

Status: **M0 — build spike**. The engine compiles to WebAssembly and renders,
but this is not yet a playable release.

- `engine/` — vendored XBlast TNT 2.10.4 with Debian patches (GPL-2.0-or-later)
- `data/` — images, levels, sounds, music and the Bitstream Vera font, from the
  Debian `xblast-tnt-*` packages (GPL-2+); see `LICENSE/data/`
- `web/` — browser shell, SDL 1.2 compatibility layer and web glue
- `build/gen/config.h` — configuration for the Emscripten build
- `scripts/build-web.sh` — builds `web/dist/`

## Build

Requires the Emscripten SDK pinned in `.tool-versions`:

```sh
asdf plugin add emsdk
asdf install
./scripts/build-web.sh
python3 -m http.server -d web/dist 8000
```

Then open <http://localhost:8000>. Serve over HTTP; the `.wasm` and `.data`
files will not load from `file://`.

## Licence

The whole work is distributed under GPL-2.0-or-later. Upstream code is
GPL-2.0-or-later (parts LGPL-2+); data packages are GPL-2+. See `LICENSE/` and
the headers in `engine/`.
