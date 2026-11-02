# CI efficiency — design

Date: 2026-11-02
Status: awaiting approval
Scope: CI workflows and the test harness; no game/runtime behaviour change

## Intent

Cut duplicated work in CI and stop depending on public Nostr relays for transport
tests:

1. Build `web/dist` once per CI run and reuse it for tests and Pages.
2. Merge the separate Pages workflow into CI so a `main` push builds once.
3. Run a **local** Nostr relay beside the transport tests and point the test pages at
   it, removing public-relay flakiness and retries.

The app's production signalling stays on the public relays. No public relay service
or backend is added to the project.

## Goals

- One release build per CI run, reused by transport tests and the Pages deploy.
- Transport tests use a local relay; no internet dependency.
- Pages still deploys only `web/dist`, with the existing checks and smoke test.
- Keep the release workflow separate (tag builds are rare and need their own archive).
- Keep emsdk setup to one install per run (the cache already covers repeat jobs).

## Non-goals

- A public `relay.grigic.org` or any hosted relay for players.
- Running the netplay (engine) suite on every push; it stays manual until the local
  relay is proven with it.
- Caching the full emsdk/SDL port build; restore cost is close to the saving.
- Changing room codes, join rules, TURN, or the production relay list.

## Design

### Build once, test and deploy from the artifact

- `ci.yml` build job: setup emsdk, `./scripts/build-web.sh --target release`,
  `check-web-dist.sh`, then upload `web/dist` as `release-dist` with 1-day retention.
- Transport job: download `release-dist` to `web/dist`, run
  `XB_TEST_NO_BUILD=1 python3 scripts/nettest_js.py`. No emsdk install, no rebuild.
- `nettest_js.py` gains `XB_TEST_NO_BUILD=1`: skip `build()`, still copy the test page
  and start the server/relay.
- Pages moves into `ci.yml`:
  - `pages` job (only `main` pushes and `workflow_dispatch`): download the artifact,
    `actions/configure-pages`, upload `web/dist`.
  - `deploy` job: `actions/deploy-pages`, then the existing wasm-MIME / no-`turn.json`
    smoke test.
  - Job-level permissions: `pages: write`, `id-token: write`; top-level stays
    `contents: read`.
- Delete `.github/workflows/pages.yml`; update docs/handoff references.
- Upload/download artifact paths: artifact contents are `web/dist/*`, downloaded to
  `web/dist`, so the layout is unchanged for tests and Pages.

### Local relay for transport tests

- `web/net.js`: `configure({ relayUrls })` accepts an array of `ws://`/`wss://` URLs.
  When non-empty, `enter()` passes `relayConfig: { urls, redundancy: 1 }` to Trystero's
  `joinRoom` (the vendored API supports `relayConfig.urls`). Production never sets it,
  so the default public relays are unchanged.
- `web/test/net.html`: if `globalThis.XB_TEST_RELAY` is set, call
  `XB.configure({ relayUrls: [XB_TEST_RELAY] })` before entering a room.
- `nettest_js.py`: start a relay once per run on a free local port, write
  `web/dist/test/relay.js` containing `globalThis.XB_TEST_RELAY = "ws://127.0.0.1:PORT";`,
  and include it from the test page. Stop the relay in `finally`.
- `scripts/test_relay.py`: minimal Nostr relay, test-only:
  - WebSocket server bound to `127.0.0.1`.
  - `["EVENT", event]` → `["OK", id, true, ""]` to the sender; forward it to every
    other client as `["EVENT", subId, event]` for each subscription that client
    registered (Nostr's relay-to-client shape; the client-to-relay shape is ignored
    by Trystero).
  - `["REQ", subId, ...]` → replay the in-memory events as
    `["EVENT", subId, event]`, then `["EOSE", subId]`; remember the subscription.
  - `["CLOSE", subId]` → forget it; drop subscriptions on disconnect.
  - Keep the last 2,000 events in memory so a late page sees earlier
    announcements, as a real relay would.
  - No persistence, auth, filtering or signature checks; the test clients do their own
    topic filtering. This is not a relay for players.
- Dependency: `websockets`, pinned in `requirements-test.txt`, installed only in the
  transport job (`python3 -m pip install -r requirements-test.txt`). It is not a
  runtime or build dependency. If it is missing locally, the harness prints an install
  hint.
- Keep `XB_TEST_RETRIES=1` as a safety net; with the local relay the public-relay flake
  should disappear.

### CI shape after the change

```
build (all pushes/PRs)
  └─ release-dist artifact
transport (needs build)  → download artifact, local relay, XB_TEST_NO_BUILD=1
pages (needs build, main) → download artifact, upload Pages artifact
  └─ deploy (main)        → deploy + smoke test
release workflow (tags)   → unchanged, builds its own tagged tree
```

## Risks and mitigations

- **Local relay differs from real relays.** It implements only the subset Trystero
  uses; the existing transport suite is the proof. Production continues to use the
  public relays, so a relay bug affects tests, not players.
- **Artifact path assumptions.** Verify by downloading the artifact locally
  (`gh run download`) or by inspecting one CI run after the change; the first push is
  the check.
- **Pages coupling.** Deploy is gated to `main` and `workflow_dispatch`; PRs only
  build/test. If Pages is unavailable, the deploy job fails without affecting tests.
- **New test dependency.** Pinned to one version, installed only in CI; no npm, no
  runtime bundle impact.

## Open questions

None; all three changes and the test-only dependency are approved in the design
conversation.
