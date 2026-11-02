# Contributing

Thanks for helping with xblast-web. This is a browser port of XBlast TNT: the
engine is C compiled to WebAssembly, with a WebRTC transport and a plain static
web shell.

## Licence of contributions

The project is distributed under **GPL-2.0-or-later**. Contributions are accepted
under the same licence (**inbound = outbound**); there is no CLA. By submitting a
change you confirm you have the right to licence it that way. Do not contribute
code or assets you cannot license compatibly, and do not copy code from a project
whose licence is unknown or incompatible.

New third-party dependencies need a licence compatible with GPL-2.0-or-later and
must be recorded in `THIRD_PARTY.md` with their version and licence. Ask before
adding a library; browser APIs and the existing vendored code cover most needs.

## AI assistance

AI involvement must be disclosed, not hidden. If a commit was produced with an AI
assistant, end the commit message with an `Assisted-by:` trailer naming the model
and provider, for example:

```
Assisted-by: DeepSeek V4.1 Flash Free (opencode/deepseek-v4.1-flash-free)
```

The README states the project's own AI involvement. Contributions that used AI
should say so in the same way; there is no penalty for doing so.

## Developer Certificate of Origin

Sign off every commit (`git commit -s`), which adds:

```
Signed-off-by: Your Name <you@example.com>
```

This is the usual Developer Certificate of Origin statement that you wrote the
change or have the right to submit it under the project licence. It is not a
copyright assignment.

## Building and testing

Follow `README.md` and `.tool-versions` (Emscripten 6.0.13 via asdf). The quick
loop:

```sh
asdf install
./scripts/build-web.sh --target lite-debug
python3 -m http.server -d web/dist 8123
```

Before opening a pull request, run what applies to your change:

```sh
python3 scripts/nettest_js.py        # transport; needs internet + Chrome
python3 scripts/netplaytest.py       # host + two guests; needs internet + Chrome
python3 scripts/playtest.py          # solo, against a served web/dist
```

The netplay tests depend on public Nostr relays and can flake; say in the PR if a
failure was relay-related. CI runs the build and transport suite, and treats the
multi-browser netplay suite as optional/manual.

## Code conventions

- Keep browser-only behaviour in `engine/` behind `#ifdef __EMSCRIPTEN__`, with a
  `/* web port: ... */` comment, and leave the upstream branch in `#else`. Fork-wide
  SDL 1.2 → SDL 2 API changes are not guarded.
- Defaults live in the engine; persistence lives in `web/index.html`, which only
  mirrors the engine's config directory.
- Do not add a backend. Multiplayer is peer-to-peer; signalling is public Nostr
  relays; TURN is optional and supplied by the hoster or player.
- Keep `web/dist*` and other build artifacts out of commits. Variant builds are
  local-only and must not be published by CI.
- Update `PROGRESS.md` for milestone-level work and `THIRD_PARTY.md` when
  dependencies or assets change.

## Commit messages

`<area>: <imperative summary>`, a body when it helps, then trailers:

```
transport: retry the control channel on reconnect

Explain the behaviour change and any trade-off.

Signed-off-by: Your Name <you@example.com>
Assisted-by: Model Name (provider/model-id)   # only if AI-assisted
```

One commit per logical change. Keep vendored upstream imports separate from port
changes. Do not rewrite published history on `main`.

## Reporting bugs and security issues

Ordinary bugs: open an issue with browser, build target, and steps to reproduce.
Security issues: follow `SECURITY.md` and do not open a public issue first.
