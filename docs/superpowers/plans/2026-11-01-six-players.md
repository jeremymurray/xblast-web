# Six Players Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Execute inline; use a subagent only if a problem genuinely needs independent eyes, and then on `opencode-go/deepseek-v4.1-flash`.

**Goal:** A room holds six players (host + five guests); a sixth guest is refused with "The room is full (6 players)." instead of hanging, and multi-guest play is proven end-to-end with three browsers by default and six on demand.

**Architecture:** `web/net.js` gains a host-side capacity check over distinct client ids and a `CTL_REJECT` control frame; the guest turns a reject into `connectError` and closes its channels so the engine leaves the wait screen. The engine and its six-player menus are unchanged. `scripts/netplaytest.py` gets a load-proof intro dismissal plus `guests` (3 pages, default) and `six` (6 pages + a light 7th page, opt-in) scenarios.

**Tech Stack:** Vanilla ES modules, WebRTC DataChannels, Trystero 0.26.0, existing Python CDP harness.

**Spec:** `docs/superpowers/specs/2026-11-01-six-players-design.md`

## Global Constraints

- No changes under `engine/`.
- `MAX_CLIENTS = 5` in `web/net.js` (six players including the host; this build has `MAX_PLAYER 6`, no `-DSMPF`).
- `HELLO_VERSION` stays 2; add `CTL_REJECT = 6` with frame `[6, reason]`; `REJECT_FULL = 1`.
- Guest message verbatim: `The room is full (6 players).`
- Replacement by stable client id runs before the capacity check and always wins.
- Capacity rejection only while the host stage is `setup` or `listening` (0/1); `match`/`idle` (2/3) rely on the hello's stage.
- Rejected peers are not active, not pending, and are never accepted; `isActivePeer` excludes them.
- `scripts/netplaytest.py` default scenario becomes `guests` (3 pages); `six` is opt-in.
- Tests need internet (public Nostr relays) and the existing `--disable-features=WebRtcHideLocalIpsWithMdns` flag.
- Every commit ends with:
  `Assisted-by: DeepSeek V4.1 Flash Free (opencode/deepseek-v4.1-flash-free)`
- Work on `feat/six-players`; no release tag (M3 is not complete). Do not merge without the human's choice at the finish step.

## Review Focus

1. **A join during a match, in a full room, reports the match.** With five guests accepted and the listen socket closed, a fresh guest must get `The host is already in a match.`, never "room full" and never a hang.
2. **Pending guests count toward the cap.** With five helloed guests, one still unaccepted, a sixth is rejected — capacity is computed from hellos, not from `accept()` calls.
3. **Freeing a slot flips the room back.** After an accepted guest leaves, the host's `status().full` is false and `stats().peers` drops to four.
4. **A rejected guest ends disconnected.** Its `stats().peers` is 0 and its host peer is closed, so the engine's stream EOFs instead of sitting in the wait screen; the host still counts five.
5. **The host netbar says the room is full.** With five guests connected, the host's `#net-state` contains `full`; with fewer it shows the count.

---

### Task 1: Room capacity, reject frame, guest message, lobby status

**Files:**
- Modify: `web/net.js` (constants near lines 28-43; `isActivePeer`; `handleHello`; `handleCtlMessage`; `connectState`; `status`)
- Modify: `web/index.html` (`updateNetbar`)
- Modify: `scripts/nettest_js.py` (new `full` scenario, dispatch entry)
- Test: `scripts/nettest_js.py full`

**Interfaces:**
- Consumes: existing `ctlSend`, `closePeerChannels`, `activePeers`, `isActivePeer`, `handleHello`, `handleCtlMessage`, `connectState`, `status`.
- Produces:
  - `const MAX_CLIENTS = 5; const CTL_REJECT = 6; const REJECT_FULL = 1;`
  - `clientCount(s, exceptPeer) -> number` (distinct active/pending client ids)
  - `rejectClient(s, peer)` — sends `[CTL_REJECT, REJECT_FULL]`, sets `peer.rejected = true`, removes it from pending
  - `status()` gains `maxClients: number` and `full: boolean` (host only: `full` true when five clients count)
  - `peer.rejected` boolean on peer records

- [ ] **Step 1: Write the failing `full` transport scenario**

Append to `scripts/nettest_js.py`, following `run_multi`'s shape (`require_net`, `wait_connect`, `wait_accept`, `wait_eof`, `finish_pages`, `unique_room`):

```python
def run_full(base):
    """Room capacity: five guests fit, a sixth is refused, a freed slot reopens it."""
    room = unique_room("xbfull")
    print(f"== full: room {room} ==", flush=True)
    host = Page(f"{base}/test/net.html?role=host&room={room}&scenario=full")
    guests = [Page(f"{base}/test/net.html?role=client&room={room}&scenario=full")
              for _ in range(5)]
    extra = None
    rejoiner = None
    late = None
    pages = [("host", host)] + [(f"guest-{i + 1}", g) for i, g in enumerate(guests)]
    try:
        for label, page in pages:
            require_net(page, label)
        host_id = host.ev("XBNet.status().selfId")
        guest_ids = [g.ev("XBNet.status().selfId") for g in guests]
        check(len({host_id, *guest_ids}) == 6, "page selfIds are not distinct")
        check(host.ev("XBNet.status().maxClients") == 5,
              "status().maxClients is not the five-guest cap")

        print("1. host listens, five guests connect", flush=True)
        check(host.ev("__test.open(101, 'stream')") is True, "host open(101) failed")
        check(host.ev("__test.listen(101)") is True, "host listen(101) did not return true")
        for i, guest in enumerate(guests):
            fd = 201 + i
            check(guest.ev(f"__test.open({fd}, 'stream')") is True,
                  f"guest {i + 1} open({fd}) failed")
            guest.ev(f"__test.connect({fd})")
            wait_connect(guest, fd)
        host.wait_js("XBNet.status().peers === 5", 30, "host sees five helloed guests")

        print("2. host accepts four; one stays pending", flush=True)
        accepted = {}
        for new_fd in (102, 103, 104, 105):
            accepted[wait_accept(host, 101, new_fd)] = new_fd
        check(len(accepted) == 4 and set(accepted) <= set(guest_ids),
              f"host accepted {sorted(accepted)!r}, expected four of {sorted(guest_ids)!r}")

        print("3. a sixth guest is refused while one is still pending", flush=True)
        extra = Page(f"{base}/test/net.html?role=client&room={room}&scenario=full")
        require_net(extra, "guest-6")
        extra.ev("__test.open(301, 'stream')")
        extra.ev("__test.connect(301)")
        extra.wait_js(
            "(() => { const s = XBNet.status(); return s.connectError === "
            "'The room is full (6 players).'; })()",
            30, "sixth guest got the room-full message")
        check(extra.ev("__test.connectState(301)") == -1,
              "sixth guest connect did not fail")
        check(extra.ev("XBNet.stats().peers") == 0,
              "rejected guest still counts a connected peer")
        check(host.ev("XBNet.status().peers") == 5,
              "host peer count changed after the reject")
        check(host.ev("XBNet.status().full") is True,
              "host does not report the room as full")

        print("4. the pending guest is accepted; the room stays full", flush=True)
        pending = set(guest_ids) - set(accepted)
        check(len(pending) == 1, f"expected one pending guest, got {sorted(pending)!r}")
        accepted[wait_accept(host, 101, 106)] = 106
        check(set(accepted) == set(guest_ids), "host did not accept every helloed guest")
        check(host.ev("XBNet.status().peers") == 5, "host peer count is not five")
        check(host.ev("XBNet.status().full") is True, "host stopped reporting full")

        print("5. a rejoin of an existing client id still replaces while full", flush=True)
        joiner_id = guests[1].ev("XBNet.status().clientId")
        rejoiner = Page(f"{base}/test/net.html?role=client&room={room}"
                        f"&scenario=full&clientId={joiner_id}")
        require_net(rejoiner, "rejoiner")
        rejoiner.ev("__test.open(401, 'stream')")
        rejoiner.ev("__test.connect(401)")
        wait_connect(rejoiner, 401)
        check(wait_accept(host, 101, 107) == rejoiner.ev("XBNet.status().selfId"),
              "host accepted the wrong peer for the rejoining client")
        wait_eof(guests[1], 202)
        host.wait_js("XBNet.status().peers === 5", 15, "host still has five guests")
        check(host.ev("XBNet.status().full") is True, "host stopped reporting full")

        print("6. a guest leaving frees the slot", flush=True)
        first = guest_ids[0]
        host.ev(f"__test.closeFd({accepted[first]})")
        wait_eof(guests[0], 201)
        host.wait_js("XBNet.status().full === false", 15, "host no longer full")
        check(host.ev("XBNet.stats().peers") == 4, "host peer count is not four after a leave")

        print("7. a match stage outranks the capacity message", flush=True)
        host.ev("__test.closeFd(101)")          # listen closes, accepted peers stay
        host.wait_js("XBNet.status().hostStage === 2", 15, "host stage match")
        late = Page(f"{base}/test/net.html?role=client&room={room}&scenario=full")
        require_net(late, "late")
        late.ev("__test.open(501, 'stream')")
        late.ev("__test.connect(501)")
        late.wait_js(
            "(() => { const s = XBNet.status(); return s.connectError === "
            "'The host is already in a match.'; })()",
            30, "late guest got the match message")
        check(late.ev("__test.connectState(501)") == -1, "late guest connect did not fail")
        check(host.ev("XBNet.status().peers") == 5,
              "host counted the late guest as a peer")

        finish_pages(pages + [("guest-6", extra), ("rejoiner", rejoiner),
                              ("late", late)], True)
        print("full: PASS", flush=True)
    except Exception as e:
        finish_pages_best_effort(pages + [("guest-6", extra), ("rejoiner", rejoiner),
                                          ("late", late)], e)
        dump_pages([p for p in pages + [("guest-6", extra), ("rejoiner", rejoiner),
                                        ("late", late)] if p[1] is not None])
        raise
    finally:
        for page in [host, *guests, extra, rejoiner, late]:
            if page is not None:
                page.close()
```

Register it: add `"full": run_full,` to `SCENARIOS` and `"full"` to the default list in `main()`.

- [ ] **Step 2: Run it and watch it fail**

Run: `python3 scripts/nettest_js.py full`
Expected: FAIL — `status().maxClients is not the five-guest cap` (the field does not exist yet).

- [ ] **Step 3: Implement capacity and the reject frame in `web/net.js`**

- Constants next to `CTL_STATUS`/`HELLO_VERSION`:
  ```js
  const CTL_REJECT = 6;
  const REJECT_FULL = 1;
  const MAX_CLIENTS = 5;   /* MAX_PLAYER - 1: five guests plus the host */
  ```
- `isActivePeer(peer)`: also require `!peer.rejected`.
- New helpers (place near `activePeers`):
  - `clientCount(s, exceptPeer)`: count peers where `isActivePeer(peer) && peer.remoteRole === ROLE_CLIENT && peer !== exceptPeer && (peer.accepted || s.pending.includes(peer.id))`.
  - `rejectClient(s, peer)`: `ctlSend(s, peer, new Uint8Array([CTL_REJECT, REJECT_FULL]))`; `peer.rejected = true`; `removePending(s, peer)`.
- `handleHello`, host + client branch: after `replaceClientPeer(s, peer, remoteClientId)`, pick one of three outcomes:
  - stage `match` or `idle`: mark `peer.rejected = true` and do **not** queue it (the hello's
    stage already tells the guest why; no reject frame);
  - stage `setup`/`listening` and `clientCount(s, peer) >= MAX_CLIENTS`: `rejectClient(s, peer)`;
  - otherwise queue it as today.
  Also return early at the top of `handleHello` for an already-rejected peer, and send the
  `firstValid` hello echo before any reject frame so the guest knows the stage first.
- `handleCtlMessage`: `case CTL_REJECT:` when `peer.remoteRole === ROLE_HOST` and `bytes[1] === REJECT_FULL` → set `peer.rejected = true`, `s.connectError = 'The room is full (6 players).'`, `s.lastError = s.connectError`, then `closePeerChannels(s, peer, true)` so the stream EOFs.
- `connectState(fd)`: after the peer is resolved, `if (peer.rejected) { s.connectError = 'The room is full (6 players).'; s.lastError = s.connectError; return -1; }`. This runs after the existing stage checks, so `MATCH`/`IDLE` keep precedence.
- `status()`: add `maxClients: MAX_CLIENTS` and `full: s && s.role === 'host' ? clientCount(s, null) >= MAX_CLIENTS : false`.

- [ ] **Step 4: Run the scenario again**

Run: `python3 scripts/nettest_js.py full`
Expected: `full: PASS`.

- [ ] **Step 5: Show the cap in the host netbar**

In `web/index.html` `updateNetbar`, replace the `peers > 0` branch for hosts:
```js
} else if (status.role === 'host' && status.full) {
  stateText = `room full — ${peers} of ${status.maxClients} guests`;
  dot = 'warn';
} else if (peers > 0) {
  stateText = status.role === 'host'
    ? `${peers} of ${status.maxClients} guests connected`
    : `${peers} peer${peers === 1 ? '' : 's'} connected`;
  dot = 'ok';
}
```

- [ ] **Step 6: Run the whole transport suite**

Run: `python3 scripts/nettest_js.py`
Expected: `ALL PASS` (basic, wrong-room, multi, replace, full).

- [ ] **Step 7: Commit**

```bash
git add web/net.js web/index.html scripts/nettest_js.py
git commit -m "web: cap the room at five guests and reject a sixth"
```

---

### Task 2: Load-proof intro dismissal and a three-browser acceptance run

**Files:**
- Modify: `scripts/netplaytest.py` (`dismiss_intro`, new `run_guests`, scenario dispatch)
- Test: `scripts/netplaytest.py --scenario guests`

**Interfaces:**
- Consumes: `Page`, `start_lobby_page`, `wait_engine`, `choose_first_player`, `shot`, `dump_page`, `ROOM`.
- Produces: `dismiss_intro(page)` that clicks instead of pressing a key; `run_guests(base, outdir)`; `scenario` default `"guests"` with `"guests"`/`"six"`/`"match"`/`"refresh"`/`"midmatch"` accepted.

- [ ] **Step 1: Add the `guests` scenario (still using the old dismissal)**

Write `run_guests(base, outdir)` modeled on `run()`:
- Three pages (`host`, `guest1`, `guest2`) join the same random room (`m2-guests-xxxxxx`).
- Wait for each lobby, `wait_engine`, `dismiss_intro` for all three.
- Each guest: `choose_first_player` then `key("return")`, then
  `wait_js("__xbnet && __xbnet.connectState(1000) === 1", 60, "<label> connected")`.
- Host: `choose_first_player`, record `ctlRx`, `key("return")`, then
  `wait_js("__xbnet.stats().peers === 2", 60, "host has two guests")` and
  `wait_js(f"__xbnet.stats().ctlRx >= {ctl_before + 100}", 30, "host got both configs")`.
- Start (`key("return")`), wait 3 s, `space` on all pages, 2.5 s, then `left`/`right`/`space`
  on all pages, 2.5 s.
- Assert per page: host `peers === 2`, each guest `peers === 1`, `actTx` delta ≥ 100, no
  `show` in the overlay class.
- Register `"guests": run_guests` and accept it in `main()`'s scenario check.

- [ ] **Step 2: Run it and watch it fail**

Run: `python3 scripts/netplaytest.py --scenario guests`
Expected: FAIL — `guest2 connected: timed out after 60s waiting for globalThis.__xbnet && __xbnet.connectState(1000) === 1`. Under three engines the intro's dismissal key lands during the animation and its own 10 s wait then swallows every later input.

- [ ] **Step 3: Replace the fixed-sleep dismissal**

```python
def dismiss_intro(page):
    # The intro animates for ~1.75 s, then waits up to 10 s for a key. With
    # several engines running, a dismissal key can land during the animation and
    # only skip it, so the intro's own wait eats the input meant for the menu.
    # A click on an empty menu area ends that wait and does nothing in a menu.
    time.sleep(2.5)
    for _ in range(4):
        page.click(480, 650)
        time.sleep(1.2)
```

`page.click(480, 650)` is engine-space (`send_click` maps from 960x736); that point is below
every menu item in the join, host-wait and start-game menus.

- [ ] **Step 4: Run it again**

Run: `python3 scripts/netplaytest.py --scenario guests`
Expected: `guests: PASS` with a match screenshot per page.

- [ ] **Step 5: Make `guests` the default scenario**

In `main()`, `scenario = "guests"`; the accepted set becomes
`("guests", "six", "match", "refresh", "midmatch")`; dispatch `guests` and keep the rest.

- [ ] **Step 6: Run the default and the two-player regression**

Run: `python3 scripts/netplaytest.py`
Expected: `guests: PASS`.

Run: `python3 scripts/netplaytest.py --scenario match`
Expected: `netplay: PASS` (the old two-page flow still works with the new dismissal).

- [ ] **Step 7: Commit**

```bash
git add scripts/netplaytest.py
git commit -m "test: drive three browsers and dismiss the intro without keys"
```

---

### Task 3: Six-browser acceptance run (opt-in)

**Files:**
- Modify: `scripts/netplaytest.py` (`run_six`, dispatch, copy `web/test/net.html` into `dist/test/`)
- Test: `python3 scripts/netplaytest.py --scenario six`

**Interfaces:**
- Consumes: `run_guests`'s flow, `Page`, `start_lobby_page`, `wait_engine`, `dismiss_intro`, `choose_first_player`; the transport's `status().full`, `connectError`, `stats().peers` via `web/test/net.html`.
- Produces: `run_six(base, outdir)`; `six` accepted by `main()`.

- [ ] **Step 1: Serve the lightweight transport page**

In `main()`, after `build-web.sh` runs, copy `web/test/net.html` to `web/dist/test/net.html`
(`os.makedirs(os.path.dirname(dst), exist_ok=True); shutil.copyfile(src, dst)`), the same way
`nettest_js.py` does. This gives the 7th page a net-only guest that needs no engine.

- [ ] **Step 2: Add the `six` scenario and run it before wiring the dispatch**

Write `run_six(base, outdir)`:
- Six engine pages (`host`, `guest1`…`guest5`) join one room (`m2-six-xxxxxx`), each guest
  connects while the host is still in setup, host `choose_first_player` then `key("return")`.
- Assert `host peers === 5`, every guest `peers === 1`, and the host's
  `document.getElementById('net-state').textContent` matches `/full/`.
- Open a 7th **light** page `f"{base}/test/net.html?role=client&room={room}&scenario=full"`
  (no engine), `require_net`-style waits (`__test.ready`, `XBNet`), then
  `__test.open(301, 'stream')`, `__test.connect(301)`, and wait for
  `connectError === 'The room is full (6 players).'`; assert `__test.connectState(301) == -1`
  and `XBNet.stats().peers === 0`, and that the host still reports `peers === 5`.
- Start the match on the host (`key("return")`), `space` on all six pages, move with
  `left`/`right`/`space`, then assert per page: host `peers === 5`, guests `peers === 1`,
  `actTx` delta ≥ 100, no `show` overlay. Screenshot every page.
- Register `"six": run_six`.

Run: `python3 scripts/netplaytest.py --scenario six`
Expected: FAIL — `unknown scenario: six` (not wired yet). This task is an acceptance gate for
behaviour already proven at the transport level in Task 1; its RED is the missing scenario.

- [ ] **Step 3: Wire the dispatch**

Add `"six"` to the accepted scenario set and `if scenario == "six": return run_six(base, outdir)`.

- [ ] **Step 4: Run the heavy scenario**

Run: `python3 scripts/netplaytest.py --scenario six`
Expected: `six: PASS`. If a page fails only on timing, raise that wait (engine load under six
pages is slower) rather than shortening the assertions. Expect several minutes.

- [ ] **Step 5: Commit**

```bash
git add scripts/netplaytest.py
git commit -m "test: add an opt-in six-browser room-capacity run"
```

---

### Task 4: Docs, known issues, and the full regression

**Files:**
- Modify: `PROGRESS.md` (M3 checklist/status, known issues, how to run, next tasks)
- Modify: `AGENTS.md` (decisions: capacity rule, `MAX_CLIENTS`, default vs opt-in runs)
- Test: the commands below

**Interfaces:**
- Consumes: everything above.
- Produces: no code.

- [ ] **Step 1: Update `PROGRESS.md`**

- M3 row: multi-guest slice done (six-player support, room-full rejection).
- "How to run" scripted checks: add `python3 scripts/netplaytest.py --scenario guests` (default)
  and `--scenario six` (heavy, opt-in), and `python3 scripts/nettest_js.py full`.
- Known issues: replace "Only two players … have been verified" with the verified levels
  (three end-to-end, six on demand) and add the room-full behaviour and the reload-to-retry
  limitation.
- Next tasks: mark item 1 (six players) done; leave chat, hash, TURN, migration, resume.

- [ ] **Step 2: Update `AGENTS.md`**

One line under Decisions: five guests + host = six players; the sixth client is rejected with
`CTL_REJECT`; three browsers by default, six opt-in; no engine change.

- [ ] **Step 3: Run the regression**

```sh
python3 scripts/nettest_js.py
python3 scripts/netplaytest.py --scenario guests
python3 scripts/netplaytest.py --scenario match
python3 scripts/netplaytest.py --scenario refresh
python3 scripts/playtest.py
```
Expected: `ALL PASS`, `guests: PASS`, `netplay: PASS`, `refresh: PASS`, solo playtest PASS.

- [ ] **Step 4: Commit**

```bash
git add PROGRESS.md AGENTS.md
git commit -m "docs: close out the multi-guest slice"
```

## Self-review notes

- Spec §7 (capacity, protocol, lobby status) → Task 1. §8 (tests and harness) → Tasks 1-3.
  §9 (files) → all tasks. §3 gap → Task 1. No task touches `engine/`.
- The 16-player `-DSMPF` build stays a roadmap note, not a task: the spec lists it as a
  non-goal.
- Interface names match across tasks: `MAX_CLIENTS`, `CTL_REJECT`, `status().full`,
  `status().maxClients`, `dismiss_intro`, `run_guests`, `run_six`.
