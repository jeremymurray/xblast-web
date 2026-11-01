# Optional TURN relay Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add optional TURN support to the static browser build: deployer-supplied `turn.json`, an optional credential endpoint, and an advanced player-supplied override, all defaulting to off.

**Architecture:** A new dependency-free `web/turn.js` validates and resolves TURN configuration. `web/net.js` accepts the resolved list and passes it to Trystero's `joinRoom`; `web/index.html` owns the lobby panel, the `turn.json` fetch and the player override. The project's own deployment remains Tier 0 and creates no infrastructure.

**Tech Stack:** Plain ES modules, Trystero 0.26.0 over WebRTC, the existing Python/CDP test harness, no new dependencies.

**Spec:** `docs/superpowers/specs/2026-11-01-optional-turn-design.md`

## Global Constraints

- No new npm packages or runtime dependencies.
- Default deployment and all existing tests stay TURN-free; `turn.json` is optional.
- Only `turn:` and `turns:` URLs are accepted. Never accept arbitrary `rtcConfig` or an ICE policy.
- Credentials are local to the browser. Never log them, put them in `status()`, send them to peers, or put them in a URL query.
- Player overrides live in `sessionStorage` only.
- The project hosts no TURN service and no credential endpoint.
- Work on branch `feat/optional-turn`; merge to `main` with `--no-ff` when green. No release tag.
- Every commit ends with `Assisted-by: DeepSeek V4.1 Flash Free (opencode/deepseek-v4.1-flash-free)`.

## Review Focus

- A missing, malformed or 500-ing `turn.json` / credential endpoint must leave the lobby usable and fall back to STUN.
- Player credentials must never appear in `status()`, console output, errors, the room or another peer's browser.
- `turn:` URL parsing must reject `stun:`, embedded userinfo, missing host, bad ports and non-TURN schemes; portless `turn:`/`turns:` URLs are valid per RFC 7065.
- Endpoint failure must fall back to static `turnConfig`, and a player override must take precedence over both.
- A malformed player override must not silently connect through an unexpected relay; it must be rejected visibly and leave the deployer path usable.

---

### Task 1: TURN config primitives and the test scenario

**Files:**
- Create: `web/turn.js`
- Modify: `web/test/net.html:60-130` (test helpers and module branch)
- Modify: `scripts/nettest_js.py:95-135, 700-715`
- Modify: `scripts/build-web.sh:105-115`
- Test: `scripts/nettest_js.py` scenario `turn-config`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `parseTurnUrl(value: string): string | null`
  - `normalizeTurnConfig(value: unknown): Array<{urls: string | string[], username: string, credential: string}>`
  - `web/test/net.html` test helper `T.check(name, condition)`
  - `scripts/nettest_js.py` `run_turn_config(base)`; `Page(url, wait_for="window.__test !== undefined")`

- [ ] **Step 1: Write the failing test**

Add `T.check` in `web/test/net.html`:

```js
check(name, condition) {
  if (!condition) throw new Error(name);
  this.log('ok: ' + name);
},
```

Add a `turn-config` branch before the existing `wrong-room` branch:

```js
if (T.scenario === 'turn-config') {
  try {
    const turn = await import('../turn.js');
    const cfg = (urls, username = 'u', credential = 'p') =>
      ({ urls, username, credential });
    T.check('accepts turn url', turn.normalizeTurnConfig([
      cfg('turn:relay.example.org:3478?transport=udp')]).length === 1);
    T.check('accepts turns url', turn.normalizeTurnConfig([
      cfg('turns:relay.example.org:5349')]).length === 1);
    T.check('accepts multiple urls', turn.normalizeTurnConfig([
      cfg(['turn:relay.example.org:3478', 'turns:relay.example.org:5349'])]).length === 1);
    T.check('rejects stun', turn.normalizeTurnConfig([
      cfg('stun:stun.example.org:3478')]).length === 0);
    T.check('rejects embedded userinfo', turn.normalizeTurnConfig([
      cfg('turn:user:pass@relay.example.org:3478')]).length === 0);
    T.check('rejects bad port', turn.normalizeTurnConfig([
      cfg('turn:relay.example.org:99999')]).length === 0);
    T.check('rejects missing credential', turn.normalizeTurnConfig([
      { urls: 'turn:relay.example.org:3478', username: 'u', credential: '' }]).length === 0);
    T.check('drops only invalid entries', turn.normalizeTurnConfig([
      cfg('stun:stun.example.org:3478'), cfg('turn:relay.example.org:3478')]).length === 1);
    T.check('non-array is empty', turn.normalizeTurnConfig('nope').length === 0);
    T.ready = true;
    T.finish(true);
  } catch (e) {
    T.ready = true;
    T.finish(false, e);
  }
} else if (T.scenario === 'wrong-room') {
```

Add the scenario in `scripts/nettest_js.py`:

```python
def run_turn_config(base):
    page = Page(f"{base}/test/net.html?scenario=turn-config")
    try:
        page.wait_js("__test.ready === true", 20, "turn-config ready")
        page.wait_js("__test.done === true", 20, "turn-config done")
        err = page.ev("__test.error")
        if err:
            raise AssertionError(f"turn-config failed: {err}")
        check(page.ev("__test.ok") is True, "turn-config did not pass")
        for line in page.ev("__test.lines"):
            print(line, flush=True)
    finally:
        page.close()
```

Add `"turn-config": run_turn_config` to `SCENARIOS` and append `"turn-config"` to the default
list in `main()` so the full suite runs it.

Add an optional wait expression to `Page`:

```python
def __init__(self, url, wait_for="window.__test !== undefined"):
```

and replace the constructor's final wait with:

```python
self.wait_js(wait_for, 30, "test page")
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python3 scripts/nettest_js.py turn-config`

Expected: the page cannot import `../turn.js` (module not found), so the scenario times out or
reports a module failure.

- [ ] **Step 3: Implement `parseTurnUrl` and `normalizeTurnConfig`**

Create `web/turn.js` with no imports. Use this URL rule:

```js
const TURN_URL = /^(turns?):(\[[0-9a-fA-F:]+\]|[A-Za-z0-9._-]+)(?::(\d{1,5}))?(?:\?([A-Za-z0-9=&%._-]+))?$/;
const MAX_FIELD = 512;
const MAX_URL = 2048;

export function parseTurnUrl(value) {
  if (typeof value !== 'string') return null;
  const text = value.trim();
  if (!text || text.length > MAX_URL) return null;
  const match = TURN_URL.exec(text);
  if (!match) return null;
  const port = match[3] ? Number(match[3]) : null;
  if (port !== null && (port < 1 || port > 65535)) return null;
  return text;
}

export function normalizeTurnConfig(value) {
  if (!Array.isArray(value)) return [];
  const out = [];
  for (const entry of value) {
    if (!entry || typeof entry !== 'object') continue;
    const rawUrls = Array.isArray(entry.urls) ? entry.urls : [entry.urls];
    if (!rawUrls.length) continue;
    const urls = rawUrls.map(parseTurnUrl);
    if (urls.some((url) => !url)) continue;
    if (typeof entry.username !== 'string' || !entry.username ||
        entry.username.length > MAX_FIELD) continue;
    if (typeof entry.credential !== 'string' || !entry.credential ||
        entry.credential.length > MAX_FIELD) continue;
    out.push({
      urls: Array.isArray(entry.urls) ? urls : urls[0],
      username: entry.username,
      credential: entry.credential,
    });
  }
  return out;
}
```

- [ ] **Step 4: Copy the helper into the built bundle**

In `scripts/build-web.sh`, after the `net.js` copy, add:

```bash
if [ -f "$ROOT/web/turn.js" ]; then
	cp "$ROOT/web/turn.js" "$OUT/turn.js"
fi
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `python3 scripts/nettest_js.py turn-config`

Expected: `turn-config: PASS` and every `ok:` line printed.

- [ ] **Step 6: Commit**

```bash
git add web/turn.js web/test/net.html scripts/nettest_js.py scripts/build-web.sh
git commit -m "web: validate TURN configuration

Assisted-by: DeepSeek V4.1 Flash Free (opencode/deepseek-v4.1-flash-free)"
```

---

### Task 2: File, endpoint and resolution loaders

**Files:**
- Modify: `web/turn.js`
- Modify: `web/test/net.html` (extend `turn-config` branch)
- Test: `scripts/nettest_js.py` scenario `turn-config`

**Interfaces:**
- Consumes: `normalizeTurnConfig`, `parseTurnUrl`.
- Produces:
  - `parseTurnFile(data: unknown, opts?: {baseUrl?: string}): {turnConfig, credentialsUrl, warning}`
  - `loadTurnFile(opts?: {fetchImpl?, url?, timeoutMs?}): Promise<{turnConfig, credentialsUrl, warning}>`
  - `parseCredentialResponse(data: unknown): {turnConfig, warning}`
  - `fetchCredentials(url, opts?: {fetchImpl?, timeoutMs?}): Promise<{turnConfig, warning}>`
  - `resolveTurnConfig({file?, playerOverride?, fetchImpl?, timeoutMs?}): Promise<{turnConfig, source, warning}>`

- [ ] **Step 1: Write the failing tests**

Extend `web/test/net.html` with a fake fetch helper and these checks inside the
`turn-config` branch:

```js
const fakeFetch = (responses) => async (url) => {
  const hit = responses[String(url)];
  if (!hit) return { ok: false, status: 404, json: async () => ({}) };
  if (hit.throw) throw new Error('network down');
  return { ok: true, status: 200, json: async () => hit.body };
};

const staticFile = { turnConfig: [cfg('turn:relay.example.org:3478')] };
T.check('parses static file', turn.parseTurnFile(staticFile).turnConfig.length === 1);
T.check('parses endpoint file', turn.parseTurnFile(
  { credentialsUrl: '/turn-credentials' }, { baseUrl: 'https://game.example/' }
).credentialsUrl === 'https://game.example/turn-credentials');
T.check('rejects http endpoint', turn.parseTurnFile(
  { credentialsUrl: 'http://evil.example/creds' }, { baseUrl: 'https://game.example/' }
).credentialsUrl === null);

const missing = await turn.loadTurnFile({
  fetchImpl: fakeFetch({}), url: '/turn.json', timeoutMs: 50,
});
T.check('missing file is empty', missing.turnConfig.length === 0 && !!missing.warning);
const loaded = await turn.loadTurnFile({
  fetchImpl: fakeFetch({ '/turn.json': { body: staticFile } }),
  url: '/turn.json', timeoutMs: 50,
});
T.check('loads static file', loaded.turnConfig.length === 1);

const endpoint = await turn.fetchCredentials('https://game.example/creds', {
  fetchImpl: fakeFetch({
    'https://game.example/creds': { body: { turnConfig: [cfg('turns:relay.example.org:5349')] } },
  }), timeoutMs: 50,
});
T.check('endpoint response', endpoint.turnConfig.length === 1);

const viaEndpoint = await turn.resolveTurnConfig({
  file: { turnConfig: [], credentialsUrl: 'https://game.example/creds' },
  fetchImpl: fakeFetch({
    'https://game.example/creds': { body: { turnConfig: [cfg('turns:relay.example.org:5349')] } },
  }), timeoutMs: 50,
});
T.check('resolves endpoint', viaEndpoint.source === 'endpoint');
const fallback = await turn.resolveTurnConfig({
  file: { turnConfig: [cfg('turn:relay.example.org:3478')],
          credentialsUrl: 'https://game.example/creds' },
  fetchImpl: fakeFetch({ 'https://game.example/creds': { throw: true } }), timeoutMs: 50,
});
T.check('falls back to file', fallback.source === 'file');
const override = await turn.resolveTurnConfig({
  file: { turnConfig: [cfg('turn:file.example.org:3478')], credentialsUrl: null },
  playerOverride: [cfg('turn:mine.example.org:3478')], timeoutMs: 50,
});
T.check('player wins', override.source === 'player');
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python3 scripts/nettest_js.py turn-config`

Expected: FAIL because `parseTurnFile` is not exported.

- [ ] **Step 3: Implement the loaders in `web/turn.js`**

Add a JSON fetch helper with an `AbortController` timeout. `loadTurnFile` uses
`cache: 'no-cache'`; `fetchCredentials` uses `cache: 'no-store'`, `mode: 'cors'`,
`credentials: 'omit'` and `headers: { Accept: 'application/json' }`. Both swallow every error
and return an empty list plus a warning. `parseTurnFile` accepts only `turnConfig` and
`credentialsUrl`; `credentialsUrl` must resolve to `https:` or an http localhost URL, and must
not contain username/password. `parseCredentialResponse` accepts `{ turnConfig: [...] }` or a
bare ICE-server object. `resolveTurnConfig` tries player override, then endpoint, then static
file, then empty, in that order.

- [ ] **Step 4: Run the test to verify it passes**

Run: `python3 scripts/nettest_js.py turn-config`

Expected: `turn-config: PASS`.

- [ ] **Step 5: Commit**

```bash
git add web/turn.js web/test/net.html
git commit -m "web: load TURN configuration from file or endpoint

Assisted-by: DeepSeek V4.1 Flash Free (opencode/deepseek-v4.1-flash-free)"
```

---

### Task 3: Player override parsing and session storage

**Files:**
- Modify: `web/turn.js`
- Modify: `web/test/net.html` (extend `turn-config` branch)
- Test: `scripts/nettest_js.py` scenario `turn-config`

**Interfaces:**
- Consumes: `normalizeTurnConfig`, `parseTurnUrl`.
- Produces:
  - `parsePlayerOverride(value): {turnConfig, error}`
  - `readPlayerOverride(storage?): {urls, username, credential} | null`
  - `writePlayerOverride(storage, value): boolean`
  - `clearPlayerOverride(storage?): void`
  - `PLAYER_STORAGE_KEY = 'xb:turn'`

- [ ] **Step 1: Write the failing tests**

Add to the `turn-config` branch:

```js
const split = turn.parsePlayerOverride({
  urls: 'turn:a.example:3478, turns:b.example:5349', username: 'u', credential: 'p',
});
T.check('splits override urls', split.turnConfig.length === 1 &&
  split.turnConfig[0].urls.length === 2);
T.check('rejects empty override', !!turn.parsePlayerOverride(
  { urls: '', username: '', credential: '' }).error);
T.check('rejects bad override', !!turn.parsePlayerOverride(
  { urls: 'stun:stun.example', username: 'u', credential: 'p' }).error);

const mem = (() => {
  const data = new Map();
  return {
    getItem: (k) => data.has(k) ? data.get(k) : null,
    setItem: (k, v) => data.set(k, String(v)),
    removeItem: (k) => data.delete(k),
  };
})();
T.check('writes override', turn.writePlayerOverride(mem, {
  urls: ['turn:relay.example.org:3478'], username: 'u', credential: 'p',
}) === true);
T.check('reads override', turn.readPlayerOverride(mem).credential === 'p');
turn.clearPlayerOverride(mem);
T.check('clears override', turn.readPlayerOverride(mem) === null);
mem.setItem(turn.PLAYER_STORAGE_KEY, '{not json');
T.check('bad stored json is null', turn.readPlayerOverride(mem) === null);
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python3 scripts/nettest_js.py turn-config`

Expected: FAIL because `parsePlayerOverride` is not exported.

- [ ] **Step 3: Implement the override helpers**

`parsePlayerOverride` trims fields, splits a string `urls` on `/[\s,]+/`, drops empty parts,
and returns `{ turnConfig: [], error: 'Enter a turn: or turns: URL, username and credential.' }`
when validation fails. `readPlayerOverride` uses `sessionStorage` by default, parses JSON, and
returns only the three fields; any exception returns `null`. `writePlayerOverride` stores only
those three fields, catches storage exceptions and returns `false`. `clearPlayerOverride`
removes `PLAYER_STORAGE_KEY` and swallows exceptions.

- [ ] **Step 4: Run the test to verify it passes**

Run: `python3 scripts/nettest_js.py turn-config`

Expected: `turn-config: PASS`.

- [ ] **Step 5: Commit**

```bash
git add web/turn.js web/test/net.html
git commit -m "web: store a player TURN override for the tab

Assisted-by: DeepSeek V4.1 Flash Free (opencode/deepseek-v4.1-flash-free)"
```

---

### Task 4: Pass TURN configuration through `net.js`

**Files:**
- Modify: `web/net.js:14-55, 124-130, 534-560, 988-1010`
- Modify: `web/test/net.html` (extend `turn-config` branch)
- Test: `scripts/nettest_js.py` scenario `turn-config`

**Interfaces:**
- Consumes: `normalizeTurnConfig` from `./turn.js`.
- Produces:
  - `XBNet.configure({ turnConfig, turnSource })`
  - `XBNet.status().turnConfigured`, `.turnServers`, `.turnSource`
  - `joinRoom` receives `turnConfig` only when the list is non-empty.

- [ ] **Step 1: Write the failing tests**

Add to the `turn-config` branch:

```js
XB.configure({ turnConfig: [cfg('turn:relay.example.org:3478')], turnSource: 'player' });
let status = XBNet.status();
T.check('status count', status.turnConfigured === true && status.turnServers === 1);
T.check('status source', status.turnSource === 'player');
T.check('status hides credential', !JSON.stringify(status).includes('"p"'));
XB.configure({ turnConfig: [cfg('stun:stun.example.org')], turnSource: 'file' });
status = XBNet.status();
T.check('invalid config clears', status.turnConfigured === false &&
  status.turnServers === 0 && status.turnSource === null);
XB.configure({ turnConfig: [cfg('turn:relay.example.org:3478')], turnSource: 'bogus' });
T.check('bogus source is null', XBNet.status().turnSource === null);
XB.configure({ turnConfig: [] });
T.check('empty clears', XBNet.status().turnConfigured === false);
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python3 scripts/nettest_js.py turn-config`

Expected: FAIL because `status().turnConfigured` is undefined.

- [ ] **Step 3: Implement the integration**

Import `normalizeTurnConfig` from `./turn.js`. Add `turnConfig: []` and `turnSource: null` to the
module `config`. In `configure`, when `turnConfig` is present, normalize it and clear the source;
when `turnSource` is present, keep it only if it is `file`, `endpoint` or `player` and the list is
non-empty. In `enter`, build:

```js
const roomConfig = { appId: APP_ID };
if (config.turnConfig.length) roomConfig.turnConfig = config.turnConfig;
const roomObj = joinRoom(roomConfig, ...);
```

In `status()`, return `turnConfigured: config.turnConfig.length > 0`,
`turnServers: config.turnConfig.length`, `turnSource: config.turnConfig.length ? config.turnSource : null`.

- [ ] **Step 4: Run the test to verify it passes**

Run: `python3 scripts/nettest_js.py turn-config`

Expected: `turn-config: PASS`.

- [ ] **Step 5: Run an existing transport regression**

Run: `python3 scripts/nettest_js.py basic`

Expected: `basic: PASS` (needs internet).

- [ ] **Step 6: Commit**

```bash
git add web/net.js web/test/net.html
git commit -m "web: pass optional TURN servers to Trystero

Assisted-by: DeepSeek V4.1 Flash Free (opencode/deepseek-v4.1-flash-free)"
```

---

### Task 5: Lobby panel and room-join wiring

**Files:**
- Modify: `web/index.html:41-57, 141-162, 194-214, 478-533, 539-550`
- Modify: `scripts/nettest_js.py` (add `turn-ui` scenario and `Page.reload`)
- Test: `scripts/nettest_js.py` scenario `turn-ui`

**Interfaces:**
- Consumes: `web/turn.js` functions and `XBNet.configure`.
- Produces:
  - Element ids: `turn-advanced`, `turn-urls`, `turn-user`, `turn-cred`, `turn-forget`,
    `turn-error`.
  - `sessionStorage['xb:turn']` populated/cleared by the panel.

- [ ] **Step 1: Write the failing UI test**

Add `Page.reload`:

```python
def reload(self):
    self.ws.call(self.next_id(), "Page.reload", {"ignoreCache": False})
```

Add the scenario:

```python
def run_turn_ui(base):
    page = Page(f"{base}/index.html",
                wait_for="!!document.getElementById('turn-advanced')")
    try:
        check(page.ev("document.getElementById('turn-cred').type") == "password",
              "credential field is not a password input")
        page.ev("sessionStorage.setItem('xb:turn', JSON.stringify({"
                "urls:['turn:relay.example.org:3478'],username:'u',credential:'p'})); true")
        page.reload()
        page.wait_js("document.getElementById('turn-urls').value === "
                     "'turn:relay.example.org:3478'", 10, "stored override")
        check(page.ev("document.getElementById('turn-advanced').open") is True,
              "stored override did not open the panel")
        page.ev("document.getElementById('turn-forget').click()")
        page.wait_js("document.getElementById('turn-urls').value === ''", 5, "forget")
        check(page.ev("sessionStorage.getItem('xb:turn')") is None,
              "Forget left the override in storage")
    finally:
        page.close()
```

Add `"turn-ui": run_turn_ui` to `SCENARIOS` and append `"turn-ui"` to the default list in
`main()`.

- [ ] **Step 2: Run the test to verify it fails**

Run: `python3 scripts/nettest_js.py turn-ui`

Expected: FAIL because `#turn-advanced` does not exist.

- [ ] **Step 3: Add the panel and styles**

Inside the Multiplayer card, after the Host/Join row, add a `<details id="turn-advanced">` with
the six ids above, a short help paragraph and a Forget button. Use `type="password"` for the
credential and `autocomplete="off"` on all fields. Add card-scoped CSS for the summary, hint and
error text; reuse the existing `.card input` and `.card .row button` rules.

- [ ] **Step 4: Wire storage, loading and room join**

At page load, import `./turn.js` once, read `readPlayerOverride(sessionStorage)`, fill the fields
and open the panel when a stored override exists. Start `loadTurnFile()` once in the background.

In `startNet`, after importing `net.js` and before `enter`:

- build `{ urls, username, credential }` from the fields;
- if any field is non-empty, call `parsePlayerOverride`; on error show `turn-error`, open the
  panel, reset `lobbyStarting` and return without entering the room; on success store it and use
  its `turnConfig`;
- if every field is empty, call `clearPlayerOverride`;
- await the background `loadTurnFile()` unless a valid player override is already in use;
- call `resolveTurnConfig({ file, playerOverride })`;
- call `XBNet.configure({ turnConfig: result.turnConfig, turnSource: result.source })`;
- then call `XBNet.enter(mode, room)`.

The Forget button clears the fields, the error and `sessionStorage`. Clear the error when the
player edits a field. Never log the credential.

- [ ] **Step 5: Run the test to verify it passes**

Run: `python3 scripts/nettest_js.py turn-ui`

Expected: `turn-ui: PASS`.

- [ ] **Step 6: Commit**

```bash
git add web/index.html scripts/nettest_js.py
git commit -m "web: add the advanced TURN lobby panel

Assisted-by: DeepSeek V4.1 Flash Free (opencode/deepseek-v4.1-flash-free)"
```

---

### Task 6: Examples, build copy and hosting guide

**Files:**
- Create: `web/turn.example.json`
- Create: `web/turn.example.endpoint.json`
- Create: `docs/hosting.md`
- Modify: `.gitignore`
- Modify: `scripts/build-web.sh`
- Modify: `README.md`, `PROGRESS.md`, `AGENTS.md`
- Test: `scripts/nettest_js.py turn-config turn-ui`, `git diff --check`

**Interfaces:**
- Consumes: the schema and panel from Tasks 1-5.
- Produces: deployable examples and the hoster runbook.

- [ ] **Step 1: Add the example files and ignore the real one**

`web/turn.example.json`:

```json
{
  "turnConfig": [
    {
      "urls": ["turn:turn.example.org:3478?transport=udp"],
      "username": "xblast",
      "credential": "replace-me"
    }
  ]
}
```

`web/turn.example.endpoint.json`:

```json
{
  "credentialsUrl": "https://turn.example.com/credentials"
}
```

Add `web/turn.json` to `.gitignore`. In `scripts/build-web.sh`, copy `web/turn.json` into
`web/dist/` when present.

- [ ] **Step 2: Write `docs/hosting.md`**

Cover four profiles: no TURN (the project's own deployment), self-hosted static TURN,
self-hosted public TURN with a credential endpoint, and player-supplied TURN. Include:

- the `turn.json` schema and both example files;
- coturn checklist: VPS, DNS, 3478/5349 UDP+TCP, relay range, TLS, `external-ip`, quota,
  private-range denials, static user or `use-auth-secret`;
- the REST credential formula (`username = expiry:id`,
  `credential = base64(HMAC-SHA1(secret, username))`) and the need for a TTL longer than a match;
- the worker/CORS/rate-limit responsibilities;
- the credential warning for static files;
- a verification step using `chrome://webrtc-internals` and `localCandidateType === "relay"`;
- the statement that TURN is a relay, not a game server, and that our own deployment stays
  Tier 0.

Add a short README hosting link and remove the “relay mode is not wired up yet” sentence.
Update `PROGRESS.md` and `AGENTS.md`: optional TURN decision, default Tier 0, player override,
hosting doc, test commands.

- [ ] **Step 3: Run the focused tests**

Run: `python3 scripts/nettest_js.py turn-config turn-ui`

Expected: both scenarios PASS.

- [ ] **Step 4: Run the regression suite**

Run: `python3 scripts/nettest_js.py`

Expected: `ALL PASS` (needs internet for the existing WebRTC scenarios).

Run: `python3 scripts/netplaytest.py --scenario match`

Expected: `netplay: PASS`.

- [ ] **Step 5: Check the diff**

Run: `git diff --check`

Expected: no output.

- [ ] **Step 6: Commit**

```bash
git add .gitignore scripts/build-web.sh web/turn.example.json \
  web/turn.example.endpoint.json docs/hosting.md README.md PROGRESS.md AGENTS.md
git commit -m "docs: document optional TURN and add examples

Assisted-by: DeepSeek V4.1 Flash Free (opencode/deepseek-v4.1-flash-free)"
```

---

## Self-Review

- [x] Every spec section maps to a task: static/endpoint/player config, validation, fallback,
  status, panel, examples, hosting profiles, tests.
- [x] Test steps name exact functions, ids and assertions; code steps give signatures and only
  the algorithms the tests do not determine.
- [x] Interfaces use one spelling throughout: `normalizeTurnConfig`, `parseTurnFile`,
  `loadTurnFile`, `fetchCredentials`, `resolveTurnConfig`, `parsePlayerOverride`,
  `readPlayerOverride`, `writePlayerOverride`, `clearPlayerOverride`, `turnConfigured`,
  `turnServers`, `turnSource`.
- [x] Review Focus items each have a test: malformed file/endpoint in Task 2, credential leakage
  in Task 4, URL rejection in Task 1, fallback/precedence in Task 2, player override handling in
  Tasks 3 and 5.
- [x] No new dependencies; default path stays TURN-free.
