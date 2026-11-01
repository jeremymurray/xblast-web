# Reconnect/replace Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Execute inline; use a subagent only if a problem genuinely needs independent eyes, and then on `opencode-go/deepseek-v4.1-flash`.

**Goal:** A guest who refreshes before the match starts rejoins the same room and the host replaces the stale client; a refresh during a match fails fast with a clear message.

**Architecture:** JS/HTML only. `web/net.js` bumps the ctl hello to v2, carries a stable per-tab client id, replaces a host-side peer with the same id, and emits host stage (`setup`/`listening`/`match`/`idle`) so a guest can fail early. `web/index.html` restores the last room from `sessionStorage` and offers Rejoin. No engine changes.

**Tech Stack:** Vanilla ES modules, WebRTC DataChannels, Trystero 0.26.0, existing Python CDP test harness.

**Spec:** `docs/superpowers/specs/2026-10-31-reconnect-replace-design.md`

## Global Constraints

- JS/HTML only in this slice: no changes under `engine/`.
- Hello protocol becomes v2; no backward compatibility with v1 is required because both pages load the same build.
- Stable client id: 16 random bytes, hex-encoded, stored in `sessionStorage` under `xb:clientId`; fall back to a per-page id if storage is unavailable.
- Last room/role: `sessionStorage` `xb:lastRoom` (JSON `{mode, room}`); clear on Leave and Solo.
- Host stages: `0 setup`, `1 listening`, `2 match`, `3 idle`.
- No auto-load after refresh: the lobby offers a Rejoin/Re-host button.
- Tests need internet (public Nostr relays) and the existing `--disable-features=WebRtcHideLocalIpsWithMdns` flag.
- Every commit ends with:
  `Assisted-by: DeepSeek V4.1 Flash Free (opencode/deepseek-v4.1-flash-free)`
- Do not merge or tag without the human's choice at the finish step.

## Review Focus

1. **Host replacement frees the old engine slot.** A refreshed guest's new peer must cause the old accepted stream to EOF and the new peer to be accepted; the host must not keep two active clients.
2. **Mid-match refresh fails fast.** Host stage 2/3 in the hello must make `connectState` return `-1` with a clear `connectError`, not a wait-screen hang.
3. **Host still in setup still works.** Stage 0 must remain connectable; the existing host/guest-before-Continue test must keep passing.
4. **Rejoin is explicit and clears cleanly.** A reload restores the room and a Rejoin button; Leave/Solo clear it, and a missing `sessionStorage` degrades gracefully.
5. **No two-client leak.** After a refresh, the host's `stats().peers` returns to 1 and the match starts with action traffic.

---

### Task 1: Transport v2, stable client id, host replacement, host stage

**Files:**
- Modify: `web/net.js`
- Modify: `web/test/net.html` (test-only `clientId` query parameter)
- Modify: `scripts/nettest_js.py` (new `replace` scenario)
- Test: `scripts/nettest_js.py`

**Interfaces:**
- Constants: `HELLO_VERSION = 2`, `CTL_STATUS = 5`, `STAGE_SETUP = 0`,
  `STAGE_LISTENING = 1`, `STAGE_MATCH = 2`, `STAGE_IDLE = 3`.
- Hello: `[1, 2, role, idLen, ...idBytes, stage]`; `idLen` 16; role 1 host / 2 client.
- Status: `[5, stage]`, host → peers on change.
- `XBNet.status()` gains `hostStage` and `clientId` (debug/test convenience).
- `web/test/net.html` reads `?clientId=` and writes it to `sessionStorage` before importing `../net.js`.

- [ ] **Step 1: Write the failing `replace` transport test**

Add a `replace` scenario to `scripts/nettest_js.py`:
- Open a host page and client A page in the same room with `clientId=replace-<unique>`.
- Host `open(101,'stream')`, `listen(101)`; A `open(201,'stream')`, `connect(201)`; host `accept(101,102)`; exchange one ctl byte.
- Open client A2 in the same room with the **same** `clientId`.
- A2 `open(301,'stream')`, `connect(301)`; host waits for `stats().peers === 1` and accepts a new fd `103`.
- Assert A's accepted fd `102` sees EOF; host `send(103, [7,7])` reaches A2; host `stats().peers === 1`.
- Assert host `status().hostStage === 1`.

Run `python3 scripts/nettest_js.py replace`.
Expected: FAIL (client ids not carried; host sees two clients / no replacement).

- [ ] **Step 2: Implement hello v2 and the stable id**

In `web/net.js`:
- Read/create the client id:
  ```js
  function clientId() {
    try {
      let id = sessionStorage.getItem('xb:clientId');
      if (!id || !/^[0-9a-f]{32}$/.test(id)) {
        const b = crypto.getRandomValues(new Uint8Array(16));
        id = Array.from(b, x => x.toString(16).padStart(2,'0')).join('');
        sessionStorage.setItem('xb:clientId', id);
      }
      return id;
    } catch (e) {
      /* private mode: per-page id */
      return Array.from(crypto.getRandomValues(new Uint8Array(16)),
        x => x.toString(16).padStart(2,'0')).join('');
    }
  }
  ```
- Store `s.clientId` at `newSession`.
- `sendHello` builds the v2 frame with the 16 id bytes and `s.hostStage` (client sends 0).
- `handleHello` parses v2; invalid version/length/role marks `peer.invalid`.
- Store `peer.clientId` (hex) and `peer.hostStage` (last byte).
- Add `STAGE_*` constants and `s.hostStage` (0 on `enter('host')`).
- `listen()` sets stage 1; `close(listenFd)` sets stage 2 if any accepted peer is open, else 3; `accept`/`closePeerChannels`/`handlePeerLeave` recompute.
- `sendStatus(s)` sends `[CTL_STATUS, s.hostStage]` to active peers; call after hello and on every stage change.
- `handleCtlMessage` type 5 updates `peer.hostStage` for a host peer (ignore from clients).
- `connectState`: if the host peer's `hostStage` is 2 → `-1`, `connectError = 'The host is already in a match.'`; 3 → `-1`, `connectError = 'The host is not accepting players.'`.

- [ ] **Step 3: Implement host replacement by client id**

In `handleHello`, on the host with a client hello:
- Find another peer with the same `clientId` and a different peer id.
- `closePeerChannels(old, true)`, `removePending(old)`, set `old.replacedBy = peer.id`.
- Keep the old peer object while fds reference it; `activePeers` excludes it.
- Then enqueue the new peer in `pending`.
- Recompute/send host stage.

- [ ] **Step 4: Run the transport suite**

Run `python3 scripts/nettest_js.py`.
Expected: `basic`, `wrong-room`, `multi`, and `replace` all PASS; the wrong-room timeout still proves the 500 ms path.

- [ ] **Step 5: Commit**

```bash
git add web/net.js web/test/net.html scripts/nettest_js.py
git commit -m "web: replace a refreshed client by stable id and report host stage" -m "Assisted-by: DeepSeek V4.1 Flash Free (opencode/deepseek-v4.1-flash-free)"
```

---

### Task 2: Lobby rejoin and the end-to-end refresh test

**Files:**
- Modify: `web/index.html`
- Modify: `scripts/netplaytest.py` (new `--scenario refresh`; keep `match` default)
- Test: `scripts/netplaytest.py`

**Interfaces:**
- Lobby IDs: `#rejoin` (banner button), `#rejoin-banner` (container), `#rejoin-room` (text).
- Storage keys: `xb:lastRoom` JSON `{mode:'host'|'client', room}`; `xb:clientId` from Task 1.
- `startNet(mode)` stores `xb:lastRoom`; `startSolo()` and `#leave` clear it.
- On load, read `xb:lastRoom`; prefill `#room`; show `#rejoin-banner` with `Rejoin room X` for client or `Re-host room X` for host; clicking calls `startNet(mode)`.
- `updateNetbar` shows `status().connectError` and host stage; no change to the M2 flow.

- [ ] **Step 1: Write the failing refresh scenario**

Add `--scenario refresh` to `scripts/netplaytest.py`:
- Host and guest join/connect as in the existing match test, with the host still in its wait menu.
- Reload the guest page (`Page.reload` / `location.reload()`), wait for `#rejoin-banner`.
- Click `#rejoin`, wait for the engine, dismiss the intro, choose a player, press Connect.
- Wait for the host to report `stats().peers === 1` (old client replaced) and the guest to be on the wait screen.
- Start the match; assert ctl/act traffic as in the existing test; screenshot both.

Run `python3 scripts/netplaytest.py --scenario refresh`.
Expected: FAIL (no rejoin banner; guest cannot rejoin; host keeps the stale client).

- [ ] **Step 2: Implement the lobby rejoin UI**

In `web/index.html`:
- Add the banner markup/CSS near the landing.
- `storeLastRoom(mode, room)` / `readLastRoom()` / `clearLastRoom()` with try/catch.
- Call `storeLastRoom` in `startNet`; `clearLastRoom` in `startSolo` and the Leave handler.
- On load, if a stored room exists, prefill `#room` and show the banner; the button calls `startNet(mode)`.
- In `updateNetbar`, show `status().connectError`/`lastError` and the host stage text; keep the guest Cancel behavior.
- If `sessionStorage` is unavailable, no banner; the rest works.

- [ ] **Step 3: Run refresh + default match**

Run:
```sh
python3 scripts/netplaytest.py --scenario refresh
python3 scripts/netplaytest.py
```
Expected: both PASS; the refresh run shows one active host client and a started match.

- [ ] **Step 4: Commit**

```bash
git add web/index.html scripts/netplaytest.py
git commit -m "web: offer rejoin after refresh and test client replacement" -m "Assisted-by: DeepSeek V4.1 Flash Free (opencode/deepseek-v4.1-flash-free)"
```

---

### Task 3: Mid-match failure, docs and full gate

**Files:**
- Modify: `scripts/netplaytest.py` (new `--scenario midmatch`)
- Modify: `PROGRESS.md`, `AGENTS.md`
- Test: `scripts/netplaytest.py`, `scripts/playtest.py`, `scripts/nettest_js.py`, `scripts/nettest_socket.py`

**Interfaces:**
- Mid-match scenario uses the same host/guest match setup, then reloads the guest after the level starts, clicks Rejoin, chooses a player and presses Connect.
- Assert `XBNet.status().connectError` contains `already in a match`; assert the guest does not reach a second match/playfield; the engine returns to the join menu.

- [ ] **Step 1: Write the failing mid-match scenario**

Add `--scenario midmatch` to `scripts/netplaytest.py`:
- Run the existing host/guest match until the playfield is reached.
- Reload the guest; wait for `#rejoin-banner`; click `#rejoin`; load engine; choose player; press Connect.
- Wait for `XBNet.status().connectError` to match `/already in a match/i` within 10 s.
- Assert the guest does not reach the playfield again; screenshot the guest error.

Run `python3 scripts/netplaytest.py --scenario midmatch`.
Expected: FAIL (guest hangs or lacks the error).

- [ ] **Step 2: Make the failure clear**

If Task 1's stage check is not already sufficient, fix the host stage transition at match start (`close(listenFd)` with accepted peers → stage 2) and the guest `connectState` error. The guest's engine should show `GUI_ErrorMessage("Could not join room ...")` and return to the join menu; the lobby toast shows the same reason.

- [ ] **Step 3: Update docs**

- `PROGRESS.md`: mark the reconnect/replace slice done; note mid-match resume remains a later item; add the new test commands.
- `AGENTS.md`: add the stable client id/replace/host-stage decision and the "no auto-load, Rejoin button" UX.
- Keep `0.3.0` as the release unless the human chooses a patch tag at finish.

- [ ] **Step 4: Run the full gate**

```sh
./scripts/build-web.sh
python3 scripts/playtest.py
python3 scripts/nettest_js.py
python3 scripts/nettest_socket.py
python3 scripts/netplaytest.py
python3 scripts/netplaytest.py --scenario refresh
python3 scripts/netplaytest.py --scenario midmatch
```
Expected: all PASS; the netplay tests need internet.

- [ ] **Step 5: Commit**

```bash
git add scripts/netplaytest.py PROGRESS.md AGENTS.md
git commit -m "web: fail fast on mid-match refresh and close out the slice" -m "Assisted-by: DeepSeek V4.1 Flash Free (opencode/deepseek-v4.1-flash-free)"
```

---

## Self-review notes

- **Spec coverage:** hello v2/client id, replacement, host stage/status, rejoin UI, mid-match failure, tests and docs are each assigned above.
- **Step scan:** each task has a failing test first, an implementation step, a verification command and a commit.
- **Type consistency:** `clientId`, `hostStage`, `STAGE_*`, `CTL_STATUS`, `xb:clientId`, `xb:lastRoom`, `#rejoin`, `#rejoin-banner` are used consistently across tasks.
- **Review Focus:** all five failure modes have a named assertion in Tasks 1–3.
- **Execution:** inline; no subagent dispatch unless a task reveals something that genuinely needs independent review, and then on DeepSeek 4.1 Flash.
