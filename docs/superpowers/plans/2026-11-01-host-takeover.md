# Host Takeover, Backgrounding Warning, Readable Room Codes — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** When the host leaves before a match, let a guest claim the room, reload as host, and bring the other guests back automatically; warn about a background host tab; make room codes short and readable.

**Architecture:** `web/net.js` gains a client-to-client claim/visibility protocol on the existing `xb.ctl` channels and exposes it through `XBNet.status()`/`XBNet.claimHost()`. `web/index.html` owns the takeover overlay, auto-rejoin flags and room-code generator. Two small `#ifdef __EMSCRIPTEN__` engine hooks let the page flush config before reloading and auto-connect a rejoining guest.

**Tech Stack:** Plain ES modules, Emscripten/C engine hooks, Python CDP harness (`scripts/nettest_js.py`, `scripts/netplaytest.py`).

**Spec:** `docs/superpowers/specs/2026-11-01-host-takeover-design.md`

## Global Constraints

- Branch `feat/host-takeover`; merge to `main` with `git merge --no-ff`.
- TDD: write the failing test, run it, implement, run it, commit.
- Every commit ends with:
  `Assisted-by: DeepSeek V4.1 Flash Free (opencode/deepseek-v4.1-flash-free)`
- Keep `HELLO_VERSION = 2`; new frames are `CTL_CLAIM = 7`, `CTL_HOST_LEAVING = 8`, and a third visibility byte on `CTL_STATUS = 5`.
- Room codes: `adjective-noun-NNN`, NNN 100–999; 64 adjectives exactly 5 letters; 64 animal nouns 3–5 letters; 3,686,400 combinations.
- Mid-match migration is **not planned**; the takeover flow starts a new match.
- No new libraries, backend, relays, TURN changes, or `socket.h`/game-loop changes.
- Tests that need WebRTC also need internet + `--disable-features=WebRtcHideLocalIpsWithMdns` (the harness already sets it).

## Review Focus

- A late second claim after a winner has reloaded: two hosts must resolve deterministically, not split the room.
- A winner that reaches `setup` but never `listening`: guests must not wait forever with no recovery.
- Auto-rejoin with no flushed local player: the guest must land in the join menu, not half-connected.
- The original host returning (Re-host) and a step-down host: stored intent must be client mode, never a re-host loop.
- A backgrounded host: it must warn/status, but must never be treated as gone or evicted.

---

### Task 1: Readable room codes

**Files:**
- Modify: `web/index.html` (room-code lists, `randInt`, `makeCode`, input placeholder)
- Modify: `scripts/nettest_js.py` (add `import re`, new `run_roomcode`, `SCENARIOS`, default list)

**Interfaces:**
- Produces: `makeCode(): string`, `normalizeRoom(value: string): string`, top-level `ADJECTIVES: string[]`, `ANIMALS: string[]` in the lobby page.

- [ ] **Step 1: Write the failing test**

Add `import re` to the imports at the top of `scripts/nettest_js.py` (it is not currently
imported), then add `run_roomcode(base)`:

```python
def run_roomcode(base):
    page = open_lobby(base)
    try:
        page.wait_js("typeof makeCode === 'function'", 10, "room-code generator")
        codes = page.ev("Array.from({length: 200}, () => makeCode())")
        for code in codes:
            check(re.fullmatch(r"[a-z]{5}-[a-z]{3,5}-[1-9][0-9]{2}", code) is not None,
                  f"bad room code {code!r}")
            adj, noun, num = code.split("-")
            check(100 <= int(num) <= 999, f"bad number in {code!r}")
            check(page.ev(f"ADJECTIVES.includes({json.dumps(adj)})"), f"unknown adjective {adj!r}")
            check(page.ev(f"ANIMALS.includes({json.dumps(noun)})"), f"unknown animal {noun!r}")
        check(page.ev("normalizeRoom(' Quiet Otter 482 ')") == "quiet-otter-482",
              "normalizeRoom did not normalize spaces/case")
    finally:
        page.close()
```

Register `"roomcode": run_roomcode` in `SCENARIOS` and add `"roomcode"` to the default list.

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 scripts/nettest_js.py roomcode`
Expected: FAIL — `ADJECTIVES`/`ANIMALS` undefined or `makeCode()` still returns the old 3-word format.

- [ ] **Step 3: Implement the generator**

In `web/index.html`, replace `WORDS` with the spec's exact 64-item `ADJECTIVES` (all 5 letters) and 64-item `ANIMALS` (3–5 letters). Replace `randInt` with rejection sampling:

```js
function randInt(n) {
  const limit = Math.floor(0x100000000 / n) * n;
  const buf = new Uint32Array(1);
  do { crypto.getRandomValues(buf); } while (buf[0] >= limit);
  return buf[0] % n;
}
function makeCode() {
  return `${ADJECTIVES[randInt(ADJECTIVES.length)]}-` +
         `${ANIMALS[randInt(ANIMALS.length)]}-${100 + randInt(900)}`;
}
```

Set the room input `placeholder="quiet-otter-482"`. Keep `normalizeRoom` unchanged.

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 scripts/nettest_js.py roomcode`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add web/index.html scripts/nettest_js.py
git commit -m "web: use adjective-animal-number room codes" -m "Assisted-by: DeepSeek V4.1 Flash Free (opencode/deepseek-v4.1-flash-free)"
```

---

### Task 2: Host visibility status

**Files:**
- Modify: `web/net.js`, `web/test/net.html`, `scripts/nettest_js.py`

**Interfaces:**
- Produces: `XBNet.status().hostVisible: boolean`, `XBNet.__setHostVisible(visible: boolean): void`
- Wire: `CTL_STATUS = [5, stage, visible]` (`visible` 1/0).

- [ ] **Step 1: Write the failing test**

Add `run_visibility(base)` to `scripts/nettest_js.py`:

```python
def run_visibility(base):
    room = unique_room("xbvis")
    host = Page(f"{base}/test/net.html?role=host&room={room}&scenario=basic")
    client = Page(f"{base}/test/net.html?role=client&room={room}&scenario=basic")
    late = None
    try:
        require_net(host, "host"); require_net(client, "client")
        client.wait_js(peer_ready_expr(1), 60, "client peer")
        check(host.ev("XBNet.status().hostVisible") is True, "host did not start visible")
        host.ev("XBNet.__setHostVisible(false)")
        client.wait_js("XBNet.status().hostVisible === false", 10, "client saw hidden host")
        check(client.ev("XBNet.status().hostLost") is False,
              "a hidden host was treated as gone")
        late = Page(f"{base}/test/net.html?role=client&room={room}&scenario=basic")
        require_net(late, "late")
        late.wait_js(peer_ready_expr(1), 60, "late client peer")
        late.wait_js("XBNet.status().hostVisible === false", 10, "late client saw hidden host")
        host.ev("XBNet.__setHostVisible(true)")
        client.wait_js("XBNet.status().hostVisible === true", 10, "client saw visible host")
    finally:
        for page in [host, client, late]:
            if page is not None:
                page.close()
```

Register it in `SCENARIOS` and the default list.

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 scripts/nettest_js.py visibility`
Expected: FAIL — `hostVisible` undefined / `__setHostVisible` is not a function.

- [ ] **Step 3: Implement the status byte and hook**

In `web/net.js`:

- Add `hostVisible: true` to `newSession()`.
- `sendStatus(s)` sends `new Uint8Array([CTL_STATUS, s.hostStage, s.hostVisible ? 1 : 0])`.
- In `handleCtlMessage` `CTL_STATUS`, set `peer.hostVisible = bytes.length >= 3 ? bytes[2] === 1 : true`.
- After `sendHello(s, peer)` for a new client hello, call `sendStatus(s)` so a late joiner learns the current visibility.
- Add a module-level `document.addEventListener('visibilitychange', ...)` that, when `session?.role === 'host'`, sets `session.hostVisible = document.visibilityState !== 'hidden'` and calls `sendStatus(session)`.
- `status()` returns `hostVisible`: host's own value, or the host peer's value for a client.
- Add `function setHostVisible(value) { ... }` and expose it as `XBNet.__setHostVisible`.

Add `setHostVisible(v) { return this.requireNet().__setHostVisible(v); }` to `web/test/net.html`'s `T` object if tests use the wrapper; direct `XBNet.__setHostVisible` is fine.

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 scripts/nettest_js.py visibility`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add web/net.js web/test/net.html scripts/nettest_js.py
git commit -m "web: broadcast host visibility" -m "Assisted-by: DeepSeek V4.1 Flash Free (opencode/deepseek-v4.1-flash-free)"
```

---

### Task 3: Host leaving and host-lost status

**Files:**
- Modify: `web/net.js`, `scripts/nettest_js.py`

**Interfaces:**
- Produces: `status().hostLost: boolean`, `status().hostLostStage: number`, `status().newHostId: string | null`
- Wire: `CTL_HOST_LEAVING = [8, stage]`; host sends it from `leave()`.

- [ ] **Step 1: Write the failing test**

Add `run_hostleave(base)`:

```python
def run_hostleave(base):
    room = unique_room("xbleave")
    host = Page(f"{base}/test/net.html?role=host&room={room}&scenario=basic")
    client = Page(f"{base}/test/net.html?role=client&room={room}&scenario=basic")
    try:
        require_net(host, "host"); require_net(client, "client")
        client.wait_js(peer_ready_expr(1), 60, "client peer")
        check(host.ev("__test.open(101, 'stream')") is True, "host open failed")
        check(host.ev("__test.listen(101)") is True, "host listen failed")
        check(client.ev("__test.open(201, 'stream')") is True, "client open failed")
        client.ev("__test.connect(201)")
        wait_connect(client, 201)
        wait_accept(host, 101, 102)
        host.ev("XBNet.leave()")
        client.wait_js("XBNet.status().hostLost === true", 10, "client hostLost")
        check(client.ev("XBNet.status().hostLostStage") == 1, "wrong lost stage")
        check(client.ev("XBNet.status().newHostId") is None, "unexpected new host")
        check(client.ev("XBNet.status().state") == "joined", "client left the room")
        finish_pages([("host", host), ("client", client)], True)
    finally:
        host.close(); client.close()
```

Register it in `SCENARIOS` and the default list.

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 scripts/nettest_js.py hostleave`
Expected: FAIL — `hostLost` undefined.

- [ ] **Step 3: Implement host-leaving and detection**

In `web/net.js`:

- Add `hostLost`, `hostLostStage`, `newHostId` to `newSession()`.
- Add `sendHostLeaving(s)` that sends `[CTL_HOST_LEAVING, s.hostStage]` to active clients. Call it at the start of `leave()` when `s.role === 'host'`, before closing peers.
- In `handleCtlMessage`, handle `CTL_HOST_LEAVING` when `peer.remoteRole === ROLE_HOST`: set `hostLost=true`, `hostLostStage=bytes[1]`, `newHostId=null`.
- In `handlePeerLeave` and the host peer's `ctl.onclose`, if `s.role === 'client'` and the peer was the host and no other host peer is present, set the same fields.
- In `handleHello` for a valid host hello, set `newHostId = peer.id` and `hostLost = false`.
- Add the three fields to `status()`.

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 scripts/nettest_js.py hostleave`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add web/net.js scripts/nettest_js.py
git commit -m "web: detect the host leaving a room" -m "Assisted-by: DeepSeek V4.1 Flash Free (opencode/deepseek-v4.1-flash-free)"
```

---

### Task 4: Claim protocol

**Files:**
- Modify: `web/net.js`, `web/test/net.html`, `scripts/nettest_js.py`

**Interfaces:**
- Produces: `XBNet.claimHost(): boolean`, `XBNet.cancelClaim(): boolean`,
  `XBNet.__setTakeoverTimings({claimWindowMs, claimSettleMs, hostReadyTimeoutMs}): void`
- Produces: `status().claim = {state: 'idle'|'want'|'won'|'failed', winner: string|null, self: boolean}`,
  `status().takeover: null|'host'|'join'`, `status().hostWaitFailed: boolean`
- Wire: `CTL_CLAIM = [7, state, 16, ...idBytes]`, state 1 want / 2 won / 3 cancel.

- [ ] **Step 1: Write the failing test**

Add `run_claim(base)` with three rooms:

```python
# Case A: one claimant wins, the other sees the winner.
host.ev("XBNet.leave()")
a.wait_js("XBNet.status().hostLost === true", 10, "A hostLost")
b.wait_js("XBNet.status().hostLost === true", 10, "B hostLost")
a.ev("XBNet.claimHost()")
a.wait_js("XBNet.status().takeover === 'host'", 5, "A won")
b.wait_js("XBNet.status().takeover === 'join'", 5, "B saw A win")
check(b.ev("XBNet.status().claim.winner") == a_id, "B has the wrong winner")

# Case B: simultaneous claims; the lower client id wins.
# Use fixed clientId query params and __setTakeoverTimings({claimWindowMs: 1000});
# call claimHost() on both pages in quick succession.
# Assert exactly one status().takeover === 'host' and the winner is the lower id.

# Case C: no host reaches listening; hostReadyTimeoutMs = 300.
# Call __setTakeoverTimings on both clients before claiming.
# A wins, then both see status().hostWaitFailed === true and status().claim.state === 'failed'.
```

Register it in `SCENARIOS` and the default list.

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 scripts/nettest_js.py claim`
Expected: FAIL — `claimHost` is not a function.

- [ ] **Step 3: Implement the claim state machine**

In `web/net.js`:

- Add constants `CTL_CLAIM=7`, `CLAIM_WINDOW_MS=500`, `CLAIM_SETTLE_MS=500`,
  `HOST_READY_TIMEOUT_MS=30000`, and a `takeoverTiming` config object.
- Add `claim`, `takeover`, `hostWaitFailed`, `claimTimer`, `hostReadyTimer` to the session.
- `claimFrame(state, clientId)` builds the 4+16 byte frame; `broadcastCtl(s, bytes)` sends to every peer with an open `ctl`, including same-role peers marked `invalid` for engine traffic. Handle `CTL_CLAIM` from the frame's own client id, not from `peer.remoteRole`.
- `claimHost()`: allowed only for client role, `hostLost` or `hostWaitFailed`, no `newHostId`, no `claim.winner`; broadcast want, start the window timer, return true.
- On window expiry: winner = lowest client id in the claim map (including self); if self, broadcast won, set `takeover='host'`, start a 500 ms settle timer, then set `takeover='host'` for the page; otherwise set `takeover='join'`.
- On `CTL_CLAIM` `won`: accept the lowest id; if a lower late `want` arrives before the settle ends, abort and let it win. On `cancel`, drop the entry.
- After a winner is set, start `HOST_READY_TIMEOUT_MS`; clear it when `newHostId` reaches stage `listening`. If it expires first, set `hostWaitFailed=true`, `claim.state='failed'`, `takeover=null`.
- `cancelClaim()`: broadcast cancel, clear timers/claim, return true.
- `__setTakeoverTimings(opts)` updates the config for tests.
- Add the status fields.

Add `claimHost`, `cancelClaim`, `setTakeoverTimings` wrappers to `web/test/net.html`.

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 scripts/nettest_js.py claim`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add web/net.js web/test/net.html scripts/nettest_js.py
git commit -m "web: add host takeover claims" -m "Assisted-by: DeepSeek V4.1 Flash Free (opencode/deepseek-v4.1-flash-free)"
```

---

### Task 5: Two-host collision step-down

**Files:**
- Modify: `web/net.js`, `scripts/nettest_js.py`

**Interfaces:**
- Produces: `status().stepDown: boolean`, `status().steppedDownBy: string | null`
- Rule: compare `(clientId, selfId)` lexicographically; the higher host steps down.

- [ ] **Step 1: Write the failing test**

Add `run_collision(base)`:

```python
# Two host pages in the same room with fixed, distinct client ids.
# The lower client id must keep hosting; the higher must report stepDown.
host_a = Page(f"{base}/test/net.html?role=host&room={room}&scenario=basic&clientId={low_id}")
host_b = Page(f"{base}/test/net.html?role=host&room={room}&scenario=basic&clientId={high_id}")
# Wait for both to see each other's same-role hello.
host_a.wait_js("XBNet.status().stepDown === false", 60, "low host stays")
host_b.wait_js("XBNet.status().stepDown === true", 60, "high host steps down")
check(host_b.ev("XBNet.status().steppedDownBy") == low_id, "wrong steppedDownBy")
```

Register it in `SCENARIOS` and the default list.

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 scripts/nettest_js.py collision`
Expected: FAIL — `stepDown` undefined; the higher host stays a host.

- [ ] **Step 3: Implement the collision branch**

In `handleHello`, before the generic same-role invalid return, handle `s.role === 'host' && remoteRole === ROLE_HOST`:

- Read the remote client id from the hello.
- Compare `(remoteId, peer.id)` with `(s.clientId, selfId)`.
- If remote wins: `peer.invalid = true`, set `s.stepDown = true`, `s.steppedDownBy = remoteId`, set `s.hostStage = STAGE_IDLE`, send `CTL_HOST_LEAVING` to its clients, then close peer channels; do not leave the room yet (the page owns that).
- If self wins: mark the remote peer invalid and ignore it.
- Add `stepDown`/`steppedDownBy` to `status()`.

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 scripts/nettest_js.py collision`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add web/net.js scripts/nettest_js.py
git commit -m "web: resolve two hosts deterministically" -m "Assisted-by: DeepSeek V4.1 Flash Free (opencode/deepseek-v4.1-flash-free)"
```

---

### Task 6: Config flush and auto-connect engine hooks

**Files:**
- Modify: `web/net_web.c`, `web/net_web.h`, `engine/menu_game.c`, `scripts/build-web.sh`
- Modify: `web/index.html` (takeover flag reader, `startNet` options)
- Modify: `scripts/netplaytest.py` (new `autojoin` scenario)

**Interfaces:**
- Produces: `XBWeb_FlushConfig(void)` exported as `Module._XBWeb_FlushConfig`;
  `XBWeb_AutoJoin(void): int`, `XBWeb_ClearAutoJoin(void)`;
  `xbConfig.autoJoin: boolean`.
- Produces page flag `xb:takeover = {mode:'host'|'client', room, autoJoin?:true}`.

- [ ] **Step 1: Write the failing test**

Add `run_autojoin(base, outdir)` to `scripts/netplaytest.py`:

1. Host + guest pages; host `start_lobby_page(host, "host", room)`; guest joins; wait engines; dismiss intros.
2. Guest chooses a player and connects to the host in setup. Assert `__xbnet.connectState(1000) === 1`.
3. On the guest page: `Module._XBWeb_FlushConfig(); saveConfig();`
4. Set `sessionStorage.xb:takeover = JSON.stringify({mode:'client', room, autoJoin:true})`; `location.reload()`.
5. Wait for `__xbReady` and `__xbnet.status().role === 'client'`; assert
   `__xbnet.connectState(1000) === 1` within 30 s **without any click**.
6. Negative case: clear `localStorage.xblast:config:v2`, set the same flag, reload; assert
   `__xbnet.connectState(1000) !== 1` after a few seconds (the join menu is shown, not an auto-connect).

Register `autojoin` in the `netplaytest.py` scenario dispatch and usage.

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 scripts/netplaytest.py --scenario autojoin`
Expected: FAIL — `Module._XBWeb_FlushConfig` missing, `xb:takeover` ignored, guest stays in the join menu.

- [ ] **Step 3: Implement the engine hooks and flag reader**

`web/net_web.c`:

```c
#include "cfg_main.h"   // if xblast.h does not already provide SaveConfig

EMSCRIPTEN_KEEPALIVE void
XBWeb_FlushConfig (void)
{
    SaveConfig ();
}

EM_JS(int, xb_web_auto_join, (void), {
    const config = globalThis.xbConfig;
    return config && config.autoJoin ? 1 : 0;
});

int  XBWeb_AutoJoin (void) { return xb_web_auto_join (); }
void XBWeb_ClearAutoJoin (void) { globalThis.xbConfig.autoJoin = false; }
```

Use an `EM_JS` for clearing too, or a small JS function; keep the prototype in `web/net_web.h` under `#ifdef __EMSCRIPTEN__`.

`engine/menu_game.c` in `CreateJoinNetGameMenu`, before `return XBFalse`:

```c
#ifdef __EMSCRIPTEN__
if (XBWeb_AutoJoin ()) {
    int i;
    XBBool hasPlayer = XBFalse;
    for (i = 0; i < NUM_LOCAL_PLAYER; i++) {
        if (ATOM_INVALID != _gamePlayers[i]) { hasPlayer = XBTrue; break; }
    }
    XBWeb_ClearAutoJoin ();
    if (hasPlayer) {
        return ButtonStartClient (par);
    }
}
#endif
```

`scripts/build-web.sh`: add `-sEXPORTED_FUNCTIONS=['_main','_XBWeb_FlushConfig']` to `LDFLAGS`.

`web/index.html`:

- Add `TAKEOVER_KEY = 'xb:takeover'`, `readTakeover()`, `clearTakeover()`,
  `flushConfig()` (calls `Module._XBWeb_FlushConfig()` if present, then `saveConfig()`).
- Change `startNet(mode, options)` to set
  `globalThis.xbConfig = { mode, room, autoJoin: Boolean(options && options.autoJoin) }`.
- At the bottom, before the existing last-room banner:
  read `xb:takeover`; if present, clear it, set `roomEl.value`, and call
  `startNet(flag.mode, {autoJoin: flag.autoJoin})`; otherwise keep the current
  `readLastRoom()`/`makeCode()` behavior.

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 scripts/netplaytest.py --scenario autojoin`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add web/net_web.c web/net_web.h engine/menu_game.c scripts/build-web.sh web/index.html scripts/netplaytest.py
git commit -m "web: auto-join a rejoining guest after flushing config" -m "Assisted-by: DeepSeek V4.1 Flash Free (opencode/deepseek-v4.1-flash-free)"
```

---

### Task 7: Takeover overlay and auto-rejoin

**Files:**
- Modify: `web/index.html`
- Modify: `scripts/netplaytest.py` (new `takeover` scenario + dispatch)

**Interfaces:**
- Consumes: `status().hostLost`, `.hostLostStage`, `.newHostId`, `.hostVisible`,
  `.claim`, `.takeover`, `.hostWaitFailed`, `.stepDown`;
  `claimHost()`, `cancelClaim()`; `xb:takeover`; `flushConfig()`.
- Produces DOM: `#host-gone` (`.screen`), `#host-gone-title`, `#host-gone-text`,
  `#host-gone-status`, `#takeover`, `#host-gone-leave`.

- [ ] **Step 1: Write the failing test**

Add `run_takeover(base, outdir)` to `scripts/netplaytest.py`:

1. Host + guests A/B in a room; wait for both guests connected in the host setup.
   Set `XBNet.__setTakeoverTimings({claimWindowMs: 1000, claimSettleMs: 500,
   hostReadyTimeoutMs: 90000})` on both guests so the heavy test is not racing the product
   timeout.
2. Host page is killed (`host.close()`); guests wait for `#host-gone.show`.
3. Assert the overlay text includes "host left" and both guests offer **Take over**.
4. A clicks `#takeover`; wait for A's page to reload and `XBNet.status().role === 'host'`;
   assert A's room is the same.
5. B auto-reloads; wait for `__xbReady` and `__xbnet.connectState(1000) === 1`
   **without clicking Connect**.
6. A dismisses the intro, chooses a player, clicks Continue, then Start; both pages
   reach a match and exchange ctl/act traffic.
7. While waiting before the kill, host calls `XBNet.__setHostVisible(false)`; B waits for
   `#net-state` text containing "background"; host sets true and B clears. This pins the
   guest warning UI.

Register `takeover` in the scenario dispatch and usage.

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 scripts/netplaytest.py --scenario takeover`
Expected: FAIL — no `#host-gone` overlay; the guests stay at the engine main menu.

- [ ] **Step 3: Implement the page overlay and orchestration**

In `web/index.html`:

- Add the `#host-gone` markup and CSS (`z-index: 35`), with title/text/status,
  `#takeover`, `#host-gone-leave`.
- Add `updateHostGone(status)` called from `updateNetbar()`:
  - `status.stepDown`: show "Another player is hosting", action says "Rejoin as guest".
  - `status.hostLost`: show the prompt; action says "Take over" (`claimHost()`), or
    "Take over instead" when `status.hostWaitFailed`.
  - `status.newHostId` and `status.hostStage < 1`: show "X is taking over / waiting for the room".
  - `status.newHostId` and `status.hostStage >= 1` and (`status.takeover === 'join'` or
    a host loss was observed): show "Rejoining room X…" and schedule
    `flushAndReload({mode:'client', room, autoJoin:true})` after 2 s; **Leave** cancels.
  - `status.takeover === 'host'`: show "Taking over room X…" and schedule
    `flushAndReload({mode:'host', room})`.
- `flushAndReload(flag)`: call `flushConfig()`, store `xb:takeover`, `location.reload()`.
- `#host-gone-leave`: clear takeover/last-room, call `XBNet.leave()`, reload to the lobby.
- On `stepDown`, the action rewrites the stored intent to client mode and calls
  `flushAndReload({mode:'client', room, autoJoin:true})`.
- Add the host hint under the Multiplayer card and the title/notice on
  `visibilitychange` while hosting.
- Guest netbar: if `status.hostVisible === false`, show the warn state
  "host tab is in the background — game may pause" and clear when true.

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 scripts/netplaytest.py --scenario takeover`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add web/index.html scripts/netplaytest.py
git commit -m "web: add the host takeover overlay and auto-rejoin" -m "Assisted-by: DeepSeek V4.1 Flash Free (opencode/deepseek-v4.1-flash-free)"
```

---

### Task 8: Original host returns (Re-host)

**Files:**
- Modify: `scripts/netplaytest.py` (new `hostback` scenario + dispatch)
- Modify: `web/index.html` only if the scenario exposes a gap.

**Interfaces:**
- Consumes the same new-host auto-rejoin path as Task 7.

- [ ] **Step 1: Write the test**

Add `run_hostback(base, outdir)`:

1. Host + guest; guest connects in the host setup. Set the guest's
   `hostReadyTimeoutMs` to 90000 through `__setTakeoverTimings` for the test.
2. Host page reloads (`location.reload()`); wait for the lobby; click `#rejoin` (Re-host).
3. Guest waits for `#host-gone` / "Rejoining" and then auto-connects:
   `__xbnet.connectState(1000) === 1` without clicking.
4. Host chooses a player, Continue; host sees one guest; start a match and assert traffic.

Register `hostback` in the scenario dispatch and usage.

- [ ] **Step 2: Run test to verify it fails or exposes a gap**

Run: `python3 scripts/netplaytest.py --scenario hostback`
Expected before the fix: the guest stays at the engine main menu or the overlay never clears.

- [ ] **Step 3: Fix the gap**

The generic new-host path from Task 7 should handle this. If it does not, make the
auto-rejoin condition independent of `takeover === 'join'` and keyed on a new host
hello after an observed host loss. Do not auto-rejoin a guest that never saw a host.

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 scripts/netplaytest.py --scenario hostback`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/netplaytest.py web/index.html
git commit -m "web: auto-rejoin guests when the host re-hosts" -m "Assisted-by: DeepSeek V4.1 Flash Free (opencode/deepseek-v4.1-flash-free)"
```

---

### Task 9: Host leaves mid-match

**Files:**
- Modify: `scripts/netplaytest.py` (new `hostgone` scenario + dispatch)
- Modify: `web/index.html` only if the overlay wording is wrong.

**Interfaces:**
- Consumes `hostLostStage === 2` to choose "the match ended" wording.

- [ ] **Step 1: Write the test**

Add `run_hostgone(base, outdir)`:

1. Host + guests A/B; start a match; assert action traffic. Set the guests'
   `hostReadyTimeoutMs` to 90000 through `__setTakeoverTimings`.
2. Kill the host.
3. Guests wait for `#host-gone.show`; assert the text contains "match ended".
4. A clicks `#takeover`; B auto-rejoins; A starts a **new** match.
5. Assert the new match starts from the level intro and both pages exchange ctl/act traffic.
   Do not assert any resumed game time or score.

Register `hostgone` in the scenario dispatch and usage.

- [ ] **Step 2: Run test to verify it fails or exposes a gap**

Run: `python3 scripts/netplaytest.py --scenario hostgone`
Expected before the fix: the overlay says "host left" but not "match ended", or no takeover.

- [ ] **Step 3: Fix the wording/flow**

Use `hostLostStage === 2` for the "the match ended" text. Ensure the takeover path
starts a fresh match and does not try to resume or transfer state.

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 scripts/netplaytest.py --scenario hostgone`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/netplaytest.py web/index.html
git commit -m "web: handle a host leaving mid-match" -m "Assisted-by: DeepSeek V4.1 Flash Free (opencode/deepseek-v4.1-flash-free)"
```

---

### Task 10: Docs, progress, and full regression

**Files:**
- Modify: `PROGRESS.md`, `AGENTS.md`
- No code changes unless regression exposes a bug.

- [ ] **Step 1: Update the project docs**

`PROGRESS.md`: add the host-takeover/backgrounding/room-code slice, the new test
scenarios and commands, and move mid-match migration to **not planned** with the
engine-cost rationale. Update the header date/status.

`AGENTS.md`: add durable decisions — pre-match takeover only, claim window/tie-break,
auto-rejoin/auto-connect with config flush, adjective-animal-number room codes,
mid-match migration not planned. Keep the file short; rewrite rather than append.

- [ ] **Step 2: Run the full JS transport suite**

Run: `python3 scripts/nettest_js.py`
Expected: `ALL PASS` (basic, wrong-room, multi, replace, full, turn-config, turn-ui,
roomcode, visibility, hostleave, claim, collision).

- [ ] **Step 3: Run the netplay acceptance suite**

Run each (internet + public Nostr relays required):
- `python3 scripts/netplaytest.py --scenario takeover`
- `python3 scripts/netplaytest.py --scenario hostback`
- `python3 scripts/netplaytest.py --scenario hostgone`
- `python3 scripts/netplaytest.py --scenario guests`
- `python3 scripts/netplaytest.py --scenario match`
- `python3 scripts/netplaytest.py --scenario refresh`
- `python3 scripts/netplaytest.py --scenario midmatch`

Expected: PASS for each. `six` is optional/heavy; run it once if time allows.

- [ ] **Step 4: Run the solo regression**

Run: `python3 scripts/playtest.py`
Expected: PASS (solo still starts and plays).

- [ ] **Step 5: Commit**

```bash
git add PROGRESS.md AGENTS.md
git commit -m "docs: record host takeover and room-code decisions" -m "Assisted-by: DeepSeek V4.1 Flash Free (opencode/deepseek-v4.1-flash-free)"
```

- [ ] **Step 6: Merge**

After the full suite is green and the human partner has reviewed the branch:

```bash
git checkout main
git merge --no-ff feat/host-takeover
```

Do not create a release tag unless the human partner asks; M3 completion and the
version bump are a separate decision.
