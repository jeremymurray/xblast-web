# Six players — short design

Date: 2026-11-01
Status: approved 2026-11-01
Scope: M3 slice 1 — multiple guests, room capacity, multi-browser proof
Related: `docs/superpowers/specs/2026-10-31-m2-p2p-design.md`,
`docs/superpowers/specs/2026-10-31-reconnect-replace-design.md`

## 1. Intent

Let more than one guest play in the same room, and make the room's ceiling explicit. Today a
room is verified with exactly one guest. A scratch run (host + two guests) showed that the
engine and transport already carry three players through a real match, so this slice is
mostly proof plus one missing edge: what happens when the room is full.

## 2. What already works

- The engine has six player slots and a host wait menu that lists every connected client with
  their local players and teams (`engine/menu_network.c`, `CreateHostItems`).
- `web/net.js` allocates one synthetic fd and one channel pair per peer, so accepts, datagrams
  and disconnects are already per guest.
- `scripts/nettest_js.py` has a host + two-client `multi` transport scenario.
- A throwaway six-page-capable experiment drove host + 2 guests into a match: both guests
  connected while the host was still in setup, and control and action traffic flowed in all
  three directions. No engine or transport change was needed for three players.

## 3. The gap

The engine has five remote slots (`MAX_HOSTS - 1`, host is id 0). When a sixth guest's hello
arrives, the host queues it as pending; `accept()` hands it to the engine, which finds no free
serial and returns without consuming it. The pending entry never clears, nothing is sent to the
guest, and the guest sits in "Connecting…" until its 20 s connect timeout with a generic
message. The host also spins in `SelectSockets` while the listen fd stays readable.

## 4. Goals

1. The host accepts up to five guests (six players with the host) and rejects a sixth with a
   clear reason, fast.
2. A rejoining guest whose stable client id is already present is still replaced, not rejected,
   even when the room is full.
3. A three-browser scenario (host + 2 guests) is the default multi-player acceptance test and
   reaches a real match with control and action traffic for every player.
4. A six-browser scenario (host + 5 guests, plus a 7th page asserting the rejection) is
   available on demand, not part of the default run.
5. The lobby tells the host how full the room is.
6. No engine changes.

## 5. Non-goals

- Chat, per-round desync hash, TURN, host migration, mid-match resume.
- More than six players. Six is the engine's `MAX_PLAYER`; raising it is a separate build
  decision (`-DSMPF` makes it 16).
- Enforcing the six-player *match* cap in JS. The engine already refuses a Start with more than
  six selected players ("Too many players, kick some!") and the host can see each guest's picks
  in the wait menu.
- A browser-side team/player editor. The engine's wait menu owns that.

## 6. Approaches

**A. Host-side capacity in `web/net.js` (chosen).** The host counts distinct client ids that are
active or pending; a sixth *new* id gets a `CTL_REJECT` frame and its channels close. The cap is
a JS constant (`MAX_CLIENTS = 5`, six players including the host) because the room is joined
before the engine loads, so JS cannot ask the engine at that point. No engine change; testable in
the JS harness without six engines.

**B. Expose the capacity from the engine** (`XBWeb_MaxClients()` returning `MAX_HOSTS - 1`) and
feed it to `net.js`. No magic number, but the value is unavailable exactly when the lobby needs
it (pre-engine), so JS still needs a fallback constant, plus a C change and rebuild for one
number.

**C. Change nothing; shorten the timeout and word it "no slot at the host".** Cheapest, but a full
room looks like a network failure, and the host keeps the stale pending peer.

A is chosen: smallest surface, fixes the hang, and the JS harness proves it with lightweight
pages.

## 7. Behaviour

### Capacity and rejection

- `MAX_CLIENTS = 5` (`MAX_PLAYER - 1`, host included as a player) in `web/net.js`.
- On a valid client hello the host first runs the existing replace-by-client-id path, then
  counts client peers with a hello that are not closed and are still accepted or pending.
- If this client id is not among them and the count is already `MAX_CLIENTS`, the host sends
  `CTL_REJECT` with reason `1` (room full), marks the peer `rejected`, keeps it out of pending,
  and closes its channels after ~1 s so the frame can flush.
- A rejected peer's repeated hellos are ignored (no re-queue).
- The guest's `connectState(fd)` returns `-1` with
  `connectError = "The room is full (6 players)."` as soon as a reject arrives, and closes its
  side.
- If the reject frame is lost the guest falls back to today's connect timeout; the message is
  still bounded by the timeout, not a hang.

### Protocol

`HELLO_VERSION` stays 2; add `CTL_REJECT = 6` with frame `[6, reason]`. Both pages load the same
build, as the reconnect slice already requires, so no version bump is needed for a new ctl frame.

### Lobby status

- `XBNet.status()` gains `maxClients`.
- The host netbar reads `n of 5 guests connected` and `room full` at the cap; the page does not
  hardcode the number.

## 8. Tests and harness

- **Harness fix (needed first).** `netplaytest.py`'s `dismiss_intro` uses fixed sleeps: sleep
  3 s, press space, sleep 2 s. Under the load of three engines the space lands during the intro
  animation, only skips it, and the intro's own 10 s key wait then swallows every later input.
  The page looks frozen although it is healthy. Replace it with a harmless click on an empty
  menu area (engine coords ~480, 650), repeated a few times: it dismisses the intro's wait and
  does nothing in a menu.
- **`nettest_js.py` `full` scenario:** host + five clients connect and are accepted; a sixth
  client with a new id gets the reject reason and `connectState === -1`; a new page reusing an
  existing client id is still accepted (replacement while full).
- **`netplaytest.py --scenario guests`** (default multi-player run, three pages): both guests
  connect while the host is in setup; host reaches two peers; the match starts; all three pages
  show control and action traffic; no overlay.
- **`netplaytest.py --scenario six`** (opt-in, heavy): six pages reach a match with six players;
  a seventh page joining the same room is refused with "room is full" and the host still shows
  five guests.
- **Regression:** existing `nettest_js.py` basic/wrong-room/multi/replace, existing
  `netplaytest.py --scenario match|refresh|midmatch`, `scripts/playtest.py`.

## 9. Files

- `web/net.js`: `MAX_CLIENTS`, `CTL_REJECT`, host capacity check, guest reject handling,
  `status().maxClients`.
- `web/index.html`: netbar capacity wording.
- `web/test/net.html`: nothing expected; add only if the `full` scenario needs a helper.
- `scripts/nettest_js.py`: `full` scenario.
- `scripts/netplaytest.py`: click-based intro dismissal, `guests` and `six` scenarios, default
  scenario becomes `guests`.
- `PROGRESS.md`, `AGENTS.md`: multi-guest status, room-full behaviour, test commands.

## 10. Risks

- The host can briefly hold a rejected peer in its map until the delayed close; `activePeers`
  excludes it, so counts stay correct.
- Replacement racing the capacity check: replacement runs first and closes the old peer, so the
  count does not include it.
- Six engine pages on one machine is heavy (each preloads ~15 MB of data); the `six` scenario is
  opt-in and may need longer waits than the three-page run.
- The 1 s flush delay before closing a rejected peer is a heuristic; a lost frame degrades to the
  existing timeout.

## 11. Process

Implement inline with TDD per task, one commit per logical change, every commit carrying
`Assisted-by: DeepSeek V4.1 Flash Free (opencode/deepseek-v4.1-flash-free)`. Work on a branch;
merge to `main` when green. Update `PROGRESS.md` and `AGENTS.md` as the slice lands. No release
tag: M3 is not complete.

## 12. Left to the builder

- Exact place in `handleHello` for the capacity check and the reject bookkeeping.
- Whether the delayed close is a timer on the peer or a single `setTimeout` guarded by
  `session !== s`.
- Exact netbar wording and whether the guest also shows the host's capacity.
- Wait/retry timings for the three- and six-page scenarios, and whether the 7th page in `six`
  needs its own reduced-intro path.
