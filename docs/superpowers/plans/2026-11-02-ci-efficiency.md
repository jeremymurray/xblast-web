# CI Efficiency Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Build once per CI run, reuse the artifact for transport tests and Pages, and run transport tests against a local Nostr relay.

**Architecture:** CI's build job uploads `web/dist`; transport downloads it and skips its rebuild; Pages moves into `ci.yml` and deploys the same artifact. A test-only localhost relay (`scripts/test_relay.py`, pinned `websockets`) replaces public relays for `nettest_js`; `net.js` gains a relay override used only by the test page. Production signalling is unchanged.

**Tech Stack:** GitHub Actions, Python 3 CDP harness, `websockets` 17.4 (test only), vendored Trystero 0.26.0.

**Spec:** `docs/superpowers/specs/2026-11-02-ci-efficiency-design.md`

## Global Constraints

- No runtime dependency change; `websockets` is test-only and pinned.
- Production `net.js` still uses the vendored default public relays when no override is configured.
- The relay binds `127.0.0.1` only; no persistence, auth or signature checks.
- Pages deploys only `web/dist`; it must never deploy variant builds or `turn.json`.
- CI artifact reuse must not skip `check-web-dist.sh` in the build job.
- Keep the release workflow (tag builds) separate.
- Do not change room codes, join rules, TURN, or the app's default relay list.

## Review Focus

- **Artifact layout**: `web/dist` uploaded as artifact and downloaded back to `web/dist` must keep `index.html`, `xblast.js`, `xblast.wasm`, `xblast.data`, `vendor/`, notices and `test/net.html` in the right places.
- **No-build mode**: `XB_TEST_NO_BUILD=1` must not invoke emcc and must still copy the test page and generate `relay.js`.
- **Relay isolation**: only the test page configures the relay; opening the production site must never use `ws://127.0.0.1`.
- **Missing test dependency**: without `websockets`, the harness fails with a clear install hint, not a hang.
- **Pages gating**: PRs build/test but never deploy; only `main` pushes and manual dispatch do.
- **Stale build reuse**: build job cleans `web/dist` before building, so the uploaded artifact cannot contain old test pages or a local `turn.json`.

---

### Task 1: No-build test mode and CI artifact reuse (tests only)

**Files:**
- Modify: `scripts/nettest_js.py` (`build()`, `main()`)
- Modify: `.github/workflows/ci.yml` (build upload; transport download)

**Interfaces:**
- Produces: env `XB_TEST_NO_BUILD=1` — skip the emcc build, still copy the test page.
- Produces: artifact `release-dist` containing `web/dist` contents.

- [ ] **Step 1: Add `XB_TEST_NO_BUILD` to `build()`**

```python
def build():
    if os.environ.get("XB_TEST_NO_BUILD") == "1":
        print("== using existing web/dist (XB_TEST_NO_BUILD=1) ==", flush=True)
    else:
        print("== building web/dist ==", flush=True)
        subprocess.run([os.path.join(SCRIPTS, "build-web.sh")], cwd=ROOT, check=True)
    os.makedirs(os.path.dirname(TEST_DST), exist_ok=True)
    shutil.copyfile(TEST_SRC, TEST_DST)
```

- [ ] **Step 2: Verify the no-build path locally**

Run:

```sh
./scripts/build-web.sh --target release
before=$(shasum -a 256 web/dist/xblast.wasm | cut -d' ' -f1)
XB_TEST_NO_BUILD=1 python3 scripts/nettest_js.py roomcode
after=$(shasum -a 256 web/dist/xblast.wasm | cut -d' ' -f1)
test "$before" = "$after"
```

Expected: `roomcode` passes and the wasm hash is unchanged (no rebuild).

- [ ] **Step 3: Upload the artifact from the build job**

Add after `check-web-dist.sh`:

```yaml
      - uses: actions/upload-artifact@v4
        with:
          name: release-dist
          path: web/dist
          retention-days: 1
          if-no-files-found: error
```

- [ ] **Step 4: Download and reuse it in the transport job**

Replace the transport job's emsdk setup + run step with:

```yaml
      - uses: actions/download-artifact@v4
        with:
          name: release-dist
          path: web/dist
      - name: Run transport scenarios
        env:
          XB_TEST_NO_BUILD: '1'
          XB_TEST_RETRIES: '1'
        run: python3 scripts/nettest_js.py
```

Expected: the transport job no longer installs emsdk or rebuilds.

- [ ] **Step 5: Commit**

```bash
git add scripts/nettest_js.py .github/workflows/ci.yml
git commit -s -m "ci: reuse the release build for transport tests"
```

---

### Task 2: Relay override, test relay and harness wiring

**Files:**
- Modify: `web/net.js` (config + `configure` + `enter`)
- Modify: `web/test/net.html` (configure relay before enter)
- Create: `scripts/test_relay.py`
- Create: `requirements-test.txt`
- Modify: `scripts/nettest_js.py` (start/stop relay, write `relay.js`)

**Interfaces:**
- Produces: `XBNet.configure({ relayUrls: [url, ...] })`; only `ws://`/`wss://` strings are kept.
- Produces: `globalThis.XB_TEST_RELAY` in `web/dist/test/relay.js`.
- Produces: `python3 scripts/test_relay.py --port PORT` prints `READY` and serves until killed.

- [ ] **Step 1: Write the relay**

`scripts/test_relay.py` (stdlib + `websockets.sync.server`):

```python
#!/usr/bin/env python3
"""Minimal localhost Nostr relay for the transport tests. Not for players."""
import argparse
import json
import threading
from websockets.sync.server import serve

clients = set()
lock = threading.Lock()

def handler(ws):
    with lock:
        clients.add(ws)
    try:
        for raw in ws:
            try:
                msg = json.loads(raw)
            except ValueError:
                continue
            if not isinstance(msg, list) or not msg:
                continue
            if msg[0] == "EVENT" and len(msg) > 1 and isinstance(msg[1], dict):
                ws.send(json.dumps(["OK", msg[1].get("id", ""), True, ""]))
                with lock:
                    others = [c for c in clients if c is not ws]
                for other in others:
                    try:
                        other.send(raw)
                    except Exception:
                        pass
            elif msg[0] == "REQ" and len(msg) > 1:
                ws.send(json.dumps(["EOSE", msg[1]]))
            elif msg[0] == "CLOSE":
                pass
    finally:
        with lock:
            clients.discard(ws)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, required=True)
    args = parser.parse_args()
    with serve(handler, "127.0.0.1", args.port) as server:
        print("READY", flush=True)
        server.serve_forever()

if __name__ == "__main__":
    main()
```

`requirements-test.txt`:

```
websockets==17.4
```

- [ ] **Step 2: Verify the relay with a small client**

```sh
python3 -m pip install -r requirements-test.txt
python3 scripts/test_relay.py --port 7788 &
python3 - <<'PY'
import asyncio, json, websockets
async def main():
    async with websockets.connect("ws://127.0.0.1:7788") as ws:
        await ws.send(json.dumps(["REQ", "s1", {"kinds": [1]}]))
        print(await ws.recv())          # ["EOSE","s1"]
        await ws.send(json.dumps(["EVENT", {"id": "e1", "kind": 1}]))
        print(await ws.recv())          # ["OK","e1",true,""]
asyncio.run(main())
PY
kill %1
```

Expected: `["EOSE", "s1"]` then `["OK", "e1", true, ""]`.

- [ ] **Step 3: Add the relay override to `net.js`**

In `config`, add `relayUrls: []`. In `configure(opts)`:

```js
if (Array.isArray(opts.relayUrls)) {
  config.relayUrls = opts.relayUrls.filter(
    (url) => typeof url === 'string' && /^wss?:\/\//i.test(url));
}
```

In `enter()`, after `const roomConfig = { appId: APP_ID };`:

```js
if (config.relayUrls.length) {
  roomConfig.relayConfig = { urls: config.relayUrls, redundancy: 1 };
}
```

- [ ] **Step 4: Configure it from the test page**

In `web/test/net.html`, add before the module script:

```html
<script src="relay.js"></script>
```

After `await import('../net.js')` and the `XB` check:

```js
if (globalThis.XB_TEST_RELAY) {
  XB.configure({ relayUrls: [globalThis.XB_TEST_RELAY] });
}
```

- [ ] **Step 5: Start the relay and write `relay.js` in the harness**

Add to `nettest_js.py`:

```python
def start_relay():
    port = free_port()
    proc = subprocess.Popen(
        [sys.executable, os.path.join(SCRIPTS, "test_relay.py"), "--port", str(port)],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    end = time.time() + 15
    while time.time() < end:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                pass
            return proc, f"ws://127.0.0.1:{port}"
        except OSError:
            if proc.poll() is not None:
                out = proc.stdout.read() if proc.stdout else ""
                raise RuntimeError(
                    "test relay failed; install requirements-test.txt\n" + out)
            time.sleep(0.1)
    proc.kill()
    raise RuntimeError("test relay did not start")
```

In `main()`, after `server, base = start_server()`:

```python
relay, relay_url = start_relay()
with open(os.path.join(DIST, "test", "relay.js"), "w", encoding="utf-8") as f:
    f.write(f'globalThis.XB_TEST_RELAY = {json.dumps(relay_url)};\n')
```

Stop it in `finally`: `relay.terminate(); relay.wait(timeout=5)`.

- [ ] **Step 6: Run a relay-backed scenario**

`XB_TEST_NO_BUILD=1 python3 scripts/nettest_js.py basic roomcode`
Expected: PASS with no public-relay console errors.

- [ ] **Step 7: Commit**

```bash
git add web/net.js web/test/net.html scripts/test_relay.py scripts/nettest_js.py requirements-test.txt
git commit -s -m "test: run transport tests against a local relay"
```

---

### Task 3: Merge Pages into CI, install the test dependency, verify

**Files:**
- Modify: `.github/workflows/ci.yml` (pages/deploy jobs, pip install, permissions)
- Delete: `.github/workflows/pages.yml`
- Modify: `README.md` (test prerequisite), `PROGRESS.md`, `docs/publishing.md`

**Interfaces:**
- Consumes: `release-dist` artifact from Task 1; relay from Task 2.
- Produces: Pages deployment from the same artifact; `requirements-test.txt` install in transport.

- [ ] **Step 1: Add the pip install to transport**

```yaml
      - name: Install test dependencies
        run: python3 -m pip install -r requirements-test.txt
```

- [ ] **Step 2: Move Pages into `ci.yml`**

Add jobs:

```yaml
  pages:
    name: Pages artifact
    needs: build
    if: github.ref == 'refs/heads/main' && (github.event_name == 'push' || github.event_name == 'workflow_dispatch')
    runs-on: ubuntu-latest
    permissions:
      contents: read
      pages: write
      id-token: write
    steps:
      - uses: actions/download-artifact@v4
        with:
          name: release-dist
          path: web/dist
      - uses: actions/configure-pages@v5
      - uses: actions/upload-pages-artifact@v3
        with:
          path: web/dist

  deploy:
    name: Deploy Pages
    needs: pages
    if: github.ref == 'refs/heads/main' && (github.event_name == 'push' || github.event_name == 'workflow_dispatch')
    runs-on: ubuntu-latest
    permissions:
      pages: write
      id-token: write
    environment:
      name: github-pages
      url: ${{ steps.deployment.outputs.page_url }}
    steps:
      - id: deployment
        uses: actions/deploy-pages@v4
      - name: Smoke-test the deployed site
        env:
          PAGE_URL: ${{ steps.deployment.outputs.page_url }}
        run: |
          # keep the existing wasm MIME / no-turn.json checks from pages.yml
```

Copy the existing smoke-test body from `.github/workflows/pages.yml`.

- [ ] **Step 3: Delete the separate workflow**

```bash
git rm .github/workflows/pages.yml
```

- [ ] **Step 4: Verify YAML and local no-build run**

```sh
ruby -ryaml -e 'ARGV.each{|f| YAML.load_file(f)}' .github/workflows/ci.yml
XB_TEST_NO_BUILD=1 python3 scripts/nettest_js.py roomcode
```

Expected: YAML parses; `roomcode` passes using the existing dist and local relay.

- [ ] **Step 5: Full transport run with the local relay**

```sh
XB_TEST_NO_BUILD=1 XB_TEST_RETRIES=1 python3 scripts/nettest_js.py
```

Expected: `ALL PASS`; no `nostr.robosats`/public-relay failures.

- [ ] **Step 6: Update docs**

- README test section: tests need `python3 -m pip install -r requirements-test.txt`; transport tests use a local relay and no longer need internet.
- PROGRESS: CI builds once and uses a local relay; `XB_TEST_OFFLINE` note revised (netplay still needs internet).
- `docs/publishing.md` §8: Pages now deploys from the CI artifact.
- AGENTS: record the CI decision briefly.

- [ ] **Step 7: Commit**

```bash
git add .github/workflows/ci.yml README.md PROGRESS.md docs/publishing.md AGENTS.md
git rm .github/workflows/pages.yml
git commit -s -m "ci: build once, deploy Pages from the artifact, use a local relay"
```

---

## Self-Review

- Spec coverage: build reuse (Task 1), local relay (Task 2), Pages merge and dependency install (Task 3), docs.
- Review Focus: artifact layout (Task 1 step 4 + verification), no-build (step 1–2), relay isolation (only test page reads `XB_TEST_RELAY`), missing dependency (start_relay error), Pages gating (job `if`), stale build (existing clean in `build-web.sh`).
- Interfaces consistent: `relayUrls`, `relay.js`, `XB_TEST_RELAY`, `XB_TEST_NO_BUILD`, `release-dist`.
- No netplay-in-CI change; public relay default untouched.
