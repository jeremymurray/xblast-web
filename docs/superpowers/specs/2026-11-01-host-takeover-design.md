# Host takeover, backgrounding warning, readable room codes — design

Date: 2026-11-01
Status: approved 2026-11-01
Scope: M3 slice — pre-match host takeover with auto-rejoin, host-backgrounding warning,
readable room codes
Related: `docs/superpowers/specs/2026-10-31-reconnect-replace-design.md`,
`docs/superpowers/specs/2026-11-01-six-players-design.md`

## 1. Intent

When the host leaves a room before a match, the room should not die. Every remaining guest is
offered the host role; one claims it, takes over the same room, and the others rejoin with as
little friction as possible. The room code stays the same.

The same flow runs after a host leaves mid-match, but it starts a **new** match: mid-match
migration is not planned (see Non-goals).

Two smaller changes ride along: room codes become easier to say out loud, and players are
warned that a background host tab can stall the game.

## 2. Decisions

- **Pre-match takeover only.** The match ends when the host leaves. The takeover flow can start
  a new match in the same room.
- **Open prompt to every guest**, not a host-nominated successor. A 500 ms claim window and a
  deterministic client-id tie-break decide simultaneous claims; a bare first-click race is not
  used. A `won` claim blocks later claims. This is best-effort exactly-one; the two-host
  collision safety net resolves a rare duplicate caused by late or partitioned claims.
- **Remaining guests auto-rejoin** once a new host is listening. Auto-rejoin means
  auto-connect, not just reopening the join menu: a small web-only engine intent skips the menu
  when the guest already has a local player configured. A 2 s notice with **Leave** precedes
  the reload. This applies to any new host after a host loss (a takeover winner or the original
  host returning), not only to the takeover losers.
- **Flush the current config before the reload.** The guest's player selection and game setup
  live in the engine's in-memory config until `DoMenu` returns, so a plain reload would lose
  them. The page calls a small exported engine flush and mirrors the filesystem before
  reloading; if that is unavailable, auto-connect falls back to the join menu.
- **Room code:** `adjective-noun-NNN`, NNN from 100–999, from a curated safe allowlist of 64
  five-letter adjectives and 64 animal nouns of at most five letters (3,686,400 combinations).
- **Backgrounding:** warn the host and broadcast host visibility to guests. Do not try to
  defeat browser timer throttling.
- **Mid-match migration: not planned.** Record it as such rather than a todo. The engine work
  (client→server role switch, host-id/player remapping, level progression, desync risk) is
  disproportionate for the benefit.

## 3. Current behaviour

- The lobby joins the page-owned room before the engine loads; the engine's web intent opens
  either the host setup menu or the guest join menu.
- A guest's stream to the host EOFs when the host leaves; `Client_StreamEvent` queues
  `XBNW_Disconnected` and the engine drops to the main menu.
- The guest remains in the room with zero active peers. Today the only route back is **Leave**
  or **Multiplayer Lobby** (a page reload and manual lobby flow).
- `web/net.js` creates two channels per room peer, but a client deliberately marks another
  client's hello `invalid`; clients do not coordinate with each other.
- Host stages are `setup`/`listening`/`match`/`idle`; `CTL_STATUS` already carries the stage.
- Room codes are three words plus two digits from a 24-word list (~1.24 M combinations).
- The known host-backgrounding stall is documented but not surfaced in the UI.

## 4. Goals

1. A guest can claim the host role after the host leaves; one wins in the normal case, and a
   rare duplicate is resolved deterministically by the two-host collision net.
2. The winner returns to the same room as host with one click and a reload.
3. The other guests return to the room as clients with no manual lobby work once a new host
   (the takeover winner or the original host returning) is listening.
4. The room code is unchanged by the handoff.
5. A host leaving mid-match produces a clear "the match ended" state, not a silent freeze.
6. Guests see when the host tab is backgrounded; the host is reminded to keep it visible.
7. Generated room codes are easy to spell and say, and are drawn from a safe, checked-in list.
8. No mid-match state transfer, no snapshot/replay, no client→server engine role switch.

## 5. Non-goals

- **Mid-match migration / match continuity.** Not planned. A host leaving ends the match; the
  takeover flow starts a new one.
- Mid-match resume/replay for a guest (already deferred).
- Host nomination UI, room passwords, or stronger access control.
- TURN changes, new relays, or a backend.
- Defeating timer throttling with a worker, silent audio, or wake locks.
- A room-code registry or collision check against active rooms.

## 6. Approaches considered

### Takeover

**A. Bare first-click reload.** Every guest who clicks reloads as host. Simple, but two quick
clicks create two hosts and the room can split. Rejected.

**B. Claim window + deterministic tie-break (chosen).** Each claimant broadcasts a claim and
waits 500 ms. The lowest stable client id wins; the winner broadcasts that it won and reloads.
Losers see who won. A two-host collision safety net covers a missed claim or a partition.

**C. Host nominates a successor.** Orderly when the host clicks Leave, but useless on a crash
and more UI. Not chosen for this slice; can be added later on top of B.

### Auto-rejoin

**A. Manual Rejoin.** The guest clicks a banner and then navigates the join menu. Safe but not
"lowest friction". Not chosen.

**B. Auto-open the join menu.** Reload with client intent; the guest still selects players and
clicks Connect. Half the friction. Not chosen.

**C. Auto-connect (chosen).** Reload with client intent and an `autoJoin` engine intent; if the
guest already has a local player configured, the engine invokes the existing
`ButtonStartClient` path immediately. If not, it clears the intent and shows the join menu.
A 2 s notice with **Leave** precedes the reload.

### Room codes

**A. Keep three words + two digits.** ~1.24 M combinations, four spoken tokens, easy to
mishear. Not chosen.

**B. Adjective-noun-NNN (chosen).** Three spoken tokens, 3.69 M combinations from a safe
allowlist. The number is 100–999, no leading zeros.

### Backgrounding

**A. Warn + broadcast visibility (chosen).** Cheap, honest, and helps guests distinguish a
frozen host from a gone host.

**B. Worker/keepalive mitigation.** A worker or silent audio may reduce throttling but does not
guarantee it, adds moving parts, and can surprise users. Not chosen.

## 7. Protocol

`HELLO_VERSION` stays 2. Both pages must load the same build, as before. New control frames:

```
CTL_CLAIM        = 7: [7, state, idLen, ...idBytes]
CTL_HOST_LEAVING = 8: [8, stage]
CTL_STATUS       = 5: [5, stage, visible]      (third byte added)
```

- Claim `state`: `1` want, `2` won, `3` cancel. `idLen` is 16 and `idBytes` is the claimant's
  stable client id.
- `CTL_HOST_LEAVING` is sent by a host to every active client immediately before `leave()` or a
  host reload. It carries the host's last stage so guests can say "the match ended" when the
  stage was `match`.
- `CTL_STATUS` gains a visibility byte (`1` visible, `0` hidden). Older handlers read only the
  stage byte and ignore the extra byte. The host sends status on stage changes, on visibility
  changes, and once to each peer after a valid hello.
- Claims are broadcast to every peer with an open ctl channel, including same-role client peers
  that are `invalid` for engine traffic. `handleCtlMessage` handles claim frames before the
  engine-traffic validity checks. No engine bytes are accepted from a same-role peer.
- A `won` claim blocks later claims. A `want` that arrives after a `won` is ignored; the sender
  should already have the `won` on the reliable ordered channel.
- A stale build ignores the new frames. The two-host collision safety net covers the case where
  a stale tab still tries to host.

## 8. Host loss and takeover flow

### Detection

- A client sets `hostLost = true` when it receives `CTL_HOST_LEAVING`, or when its host peer
  closes/leaves (`ctl.onclose`, `handlePeerLeave`). It records `hostLostStage` from the last
  status/hello.
- The engine will already be dropping to the main menu; no engine change is needed for this.
- When a new host hello appears, `hostLost` becomes false and `newHostId` is set. The page keeps
  the overlay but switches from "take over" to "waiting for the room".

### Client state machine

```
hostLost      no host peer; the takeover prompt is open
claiming      own `want` sent; waiting for the 500 ms window
winner        self won, `won` sent, settling before reload
waiting       another client won, or a new host hello at stage setup
rejoining     new host at stage listening; 2 s notice, then reload
failed        no listening host before the timeout; prompt reopens
```

- `claimHost()` is allowed only in `hostLost` or `failed`, and never while `claim.winner` is
  set or a new host is present.
- After a `won` or a new host hello at stage `setup`, the timeout is
  `HOST_READY_TIMEOUT_MS = 30_000` for the host to reach stage `listening`. If it expires,
  clear the claim/winner, return to `failed`, and reopen the prompt. A new claim can then
  start; the two-host collision net resolves it if the old winner later listens.
- Losers show "X is taking over… / waiting for the room" with **Leave** for the whole wait.
  They do not reload until stage `listening`.
- If a loser reloads and the host disappears before its connect lands, the normal connect
  error/join-menu flow applies; the page shows a "Could not rejoin room X" notice with
  **Leave** and clears the takeover flag.

### Claim

- On a claim the client broadcasts `want`, records the start time, and waits 500 ms
  (`CLAIM_WINDOW_MS`).
- Incoming `want` claims are collected. The winner is the lexicographically lowest client id
  among all claims seen. The tie-break only matters for near-simultaneous clicks; the first
  click normally wins.
- A `won` blocks later claims. If a lower-id `want` arrives before the winner reloads, the
  winner aborts and the lower id takes over; if the winner has already reloaded, the collision
  net is the fallback. This is why the guarantee is "one winner in the normal case", not a
  distributed lock.
- If self wins, broadcast `won`, wait 500 ms (`CLAIM_SETTLE_MS`) for the reliable ctl frame and
  any in-flight `want` to arrive, then set `takeover = 'host'` for the page. If another client
  wins, set `takeover = 'join'`, store the winner id, and move to `waiting`.
- `XBNet.cancelClaim()` broadcasts `cancel` and reopens the prompt. A claim can be cancelled
  before it is won.
- `status()` gains `hostLost`, `hostLostStage`, `hostVisible`, `claim`
  (`{state, winner, self}`), and `takeover` (`null`/`host`/`join`).

### Two-host collision safety net

If a host receives a valid host hello from another peer (both think they are host), compare
`(clientId, selfId)`; the lower pair keeps hosting. The higher page calls `leave()`, rewrites
the stored room intent to **client** mode, shows "Another player is hosting this room", and
offers **Rejoin as guest**. This also covers a duplicated tab that shares a client id. A naive
Re-host would re-collide, so the stored intent must be client. Its guests see a host loss with
the survivor already present and use the normal new-host auto-rejoin path.

### Page-level overlay

- A full-screen panel above the canvas, using the existing `.screen` style.
- Host left, match ended (if the last stage was `match`) or host left (otherwise).
- Buttons: **Take over** and **Leave**; a status line for claims ("<name> is taking over…").
- The winner's page shows "Taking over room X…" briefly before reloading.
- The losers' page shows "X is taking over… / waiting for the room" while the new host is in
  setup, then "Rejoining room X…" for 2 s with **Leave**, then reloads.

## 9. Auto-rejoin

### Config flush before any takeover reload

The guest's player selection and game setup are in the engine's in-memory config until
`DoMenu` returns. Before reloading (winner, loser, or original host returning), the page:

1. calls `Module._XBWeb_FlushConfig()` (a small exported wrapper around `SaveConfig()`);
2. calls the page's existing `saveConfig()` to mirror the Emscripten filesystem to
   `localStorage`;
3. then sets `xb:takeover` and reloads.

If the flush call is unavailable or fails, the reload still happens; the guest falls back to
the normal join menu. The wrapper is the only engine-side addition for config persistence.

### Winner

- Store `xb:takeover = {mode:'host', room}` in `sessionStorage`, then reload.
- On load, the page prefills the room, auto-calls the existing `startNet('host')`, and clears
  the flag. The engine opens the normal host setup menu. The host configures the game and
  clicks **Continue** to listen; this moves the host to stage `listening`.
- If `sessionStorage` is unavailable, the page shows the normal lobby with the room prefilled
  and a **Re-host** banner instead.

### New host, including the original host returning

- A new host hello after a host loss is treated the same whether it is the takeover winner or
  the original host returning via **Re-host**. The guest waits for stage `listening`; it does
  not reload while the host is still in `setup`.
- Show "Rejoining room X…" for 2 s with **Leave**. If **Leave** is clicked, clear the takeover
  flag, leave the room, and reload to the lobby.
- Store `xb:takeover = {mode:'client', room, autoJoin:true}` and reload.
- On load, the page prefills the room, auto-calls `startNet('client')`, and clears the flag.
  `xbConfig.autoJoin = true` tells the engine to skip the join menu when a local player is
  already configured.
- If no local player is configured, the engine clears `autoJoin` and shows the normal join
  menu; the guest can pick players and click Connect. This is the fallback, not the common case.
- If the new host disappears before/while joining, the normal connect error/join-menu flow
  applies; the page shows a "Could not rejoin room X" notice with **Leave** and clears the
  takeover flag. The lobby's Rejoin banner remains available after that.

This also upgrades the 0.3.1 host-refresh behaviour: a host that refreshes and clicks
**Re-host** now brings the guests back automatically, instead of leaving them at the engine main
menu. That is a deliberate, low-friction change and reuses the same path.

### Engine auto-connect intent

A small `#ifdef __EMSCRIPTEN__` hook in the join flow:

- `xbConfig.autoJoin` is read by the web intent path.
- After `CreateJoinNetGameMenu` is built, if `autoJoin` is set and a local player is already
  selected, invoke the existing `ButtonStartClient` path (or queue it as a one-shot menu
  action). Clear the intent either way.
- If no local player is selected, clear the intent and leave the normal menu visible.
- No new network code; `ButtonStartClient` already calls `XBWeb_ClientConnect`.

The host side needs no new intent: `mode:'host'` already opens the host setup menu.

## 10. Host-backgrounding warning

- `net.js` tracks `document.visibilityState` for the host session. On change, it updates
  `hostVisible`, sends `CTL_STATUS`, and updates `status()`.
- The host page shows a static hint under the Multiplayer card: "Keep the host tab in the
  foreground; background tabs can pause the game."
- While hosting and hidden, set `document.title = 'XBlast TNT — host in background'`; on return,
  restore the title and show a short notice: "The host tab was in the background; the match may
  have paused."
- A guest with `status.hostVisible === false` shows a persistent warn state in the netbar:
  "host tab is in the background — game may pause". It clears when the host is visible again.
- A hidden host does **not** trigger host-lost, takeover, or migration. Only peer loss/EOF does.
- On a new peer hello, the host sends a status frame so the guest learns the current visibility.

## 11. Room codes

### Format

```
<adjective>-<noun>-<NNN>      NNN = 100..999, no leading zero
```

Examples: `quiet-otter-482`, `sunny-gecko-905`, `brave-tiger-317`.

### Generator

- `makeCode()` picks one adjective, one noun, and `100 + randInt(900)`.
- `randInt(n)` uses `crypto.getRandomValues` with rejection sampling, not `% n`, so the
  distribution is uniform.
- `normalizeRoom()` is unchanged: lowercase, non-alphanumerics to single hyphens, trim, max 32.
  Generated codes already match.
- The input placeholder becomes `quiet-otter-482`.
- Custom room codes remain accepted; the new format is only the generator's default.

### Safe allowlist

64 lowercase ASCII adjectives, **exactly five letters each**, and 64 **animal nouns of at most
five letters**. No hyphens, no homophones, no profanity/slurs/sexual/violent/drug/political/
religious terms, and no words that form an unfortunate pair. Curated in `web/index.html`; no
external word list or dependency.

Animal nouns are limited to animals so the noun is always a concrete, easy-to-say thing. The
noun list allows 3–5 letters rather than exactly five: that keeps the easiest short animals
(fox, owl, cat, dog, elk, yak) and still reaches 64 without obscure entries like quoll or
kiang.

Adjectives (all exactly five letters):

```
amber azure beige black brave brown clean clear coral crisp dusty eager early fancy fresh
funny fuzzy giant grand great green happy hazel ivory jolly large light lucky lunar maple
merry minty misty noble olive peach plain polar proud quick quiet rapid ready royal sandy
sharp shiny short silky small smart snowy solar solid spicy sunny super sweet swift white
windy witty young zesty
```

Animal nouns (3–5 letters):

```
ant ape bat bee cat cod cow dog eel elk emu fox hen owl pig ram rat yak bear bird boar
colt crab crow deer dove duck fawn fish frog goat hawk hare ibex kiwi lamb lark lion lynx
mole moth mule newt orca pike pony puma seal swan toad tuna wasp wolf worm wren otter bison
panda koala zebra tiger gecko moose eagle
```

Combinations: `64 × 64 × 900 = 3,686,400`. At 100 concurrent rooms the chance of any code
collision is about 0.13%; this is acceptable for a casual game with no registry. A collision
means two groups meet in the same room and the existing role/hello checks apply.

## 12. Tests

### JS transport (`scripts/nettest_js.py`)

- `takeover` scenario, host + two clients:
  - host leaves; both clients see `hostLost` and the last stage;
  - A claims; A wins; B sees the winner; A's `takeover` is `host`, B's is `join`;
  - simultaneous claims with fixed client ids: the lower id wins;
  - cancel reopens the prompt;
  - a new host hello clears `hostLost` and moves the client to `waiting`;
  - a host that never reaches `listening` times out and reopens the prompt;
  - two hosts in one room: the higher `(clientId, selfId)` steps down and its stored intent
    becomes client mode.
- `visibility` hook: host calls `__setHostVisible(false)`; client sees `hostVisible === false`;
  set true and it clears. Add the test hook next to the existing `__resendHello`.
- The claim/visibility tests need no engine pages and no WebRTC scenario beyond the existing
  two/three-page harness.

### End-to-end (`scripts/netplaytest.py`)

- `takeover` scenario (host + two guests, pre-match):
  - host page process is killed (or clicks Leave) before the match;
  - one guest claims and becomes host in the same room;
  - the other guest auto-rejoins without clicking Connect, using its flushed player config;
  - the new host sees two guests, starts a match, and ctl/act traffic flows.
- `hostback` scenario: the host refreshes and clicks **Re-host**; the guest auto-rejoins via the
  same new-host path. This proves the 0.3.1 host-refresh UX change.
- `hostgone` mid-match scenario:
  - start a match, kill the host;
  - guests see "the match ended" and are offered takeover;
  - takeover starts a new room/match; no resume is attempted.
- Room code check on the landing page:
  - evaluate `makeCode()` 200 times; assert
    `^[a-z]{5}-[a-z]{3,5}-[1-9][0-9]{2}$`;
  - assert the numeric range, that the adjective is in the adjective list, and that the noun
    is in the animal list;
  - `normalizeRoom(' Quiet Otter 482 ') === 'quiet-otter-482'`.
- Regression: existing `basic`, `wrong-room`, `multi`, `replace`, `full`, `turn-config`,
  `turn-ui`; `match`, `guests`, `six`, `refresh`, `midmatch`; `scripts/playtest.py`.

## 13. Files

- `web/net.js`: claim protocol, host-leaving frame, visibility status, takeover/claim status,
  test hook.
- `web/index.html`: takeover overlay, auto-rejoin notice and flags, room-code lists/generator,
  backgrounding hint/title, guest warn state.
- `engine/menu.c` / `engine/menu_game.c`: `autoJoin` intent in the web join path, guarded by
  `#ifdef __EMSCRIPTEN__`.
- `web/net_web.c` (or `web/sdl_web.c`) + `scripts/build-web.sh`: the exported
  `XBWeb_FlushConfig` wrapper that calls `SaveConfig()`.
- `scripts/nettest_js.py`: `takeover` and `visibility` checks.
- `scripts/netplaytest.py`: `takeover`, `hostgone`, room-code checks.
- `PROGRESS.md`, `AGENTS.md`: takeover behaviour, room-code format, mid-match migration marked
  not planned.
- No changes to `socket.h` or the game loop.

## 14. Risks and edges

- **Claim visibility:** a guest may miss another claim if its ctl channel to that peer is not
  ready, or click late enough that its `want` misses the winner's settle window. The two-host
  collision safety net and the 30 s host-ready retry cover it; the room can still split in a
  true partition. Document as a limitation.
- **Stale build:** a cached page ignores claims. It can still use the normal Rejoin banner; the
  collision safety net prevents two hosts from coexisting silently.
- **Auto-connect with no local player:** falls back to the normal join menu; the guest is in the
  room but not connected until they choose players. This is more likely if the config flush
  fails, so the flush is a first-class step, not a nicety.
- **Reload cost:** the engine assets are cached but a reload still takes seconds on a slow
  connection. The 2 s notice and **Leave** make it visible.
- **Session storage unavailable:** no auto-rejoin/takeover flags; the prompt and manual
  Rejoin/Re-host still work.
- **Host backgrounding detection is best-effort:** some browsers throttle without reporting
  `hidden`; the warning cannot cover every case. A backgrounded host is never evicted.
- **Room-code collisions:** random, no registry; low at this scale. Existing custom codes and
  old `xb:lastRoom` values keep working.
- **New host's setup:** the old host's game settings are not transferred. The new host configures
  a fresh match; guests wait in the client wait menu. The match outcome/scores are gone, as
  intended for pre-match-only migration.
- **The host leaving mid-match:** the engine's disconnect path ends the match. The overlay says
  so; it must not imply the match can be resumed.

## 15. Left to the builder

- Exact overlay wording/layout and the 2 s notice behaviour.
- Exact placement of the `autoJoin` one-shot in the menu loop, and how to check that a local
  player is configured.
- Exact `XBWeb_FlushConfig` placement and export flags; whether it is safe to call from the
  page while the engine is in a menu.
- Whether `CTL_STATUS`'s visibility byte is enough or a separate visibility frame is cleaner.
- Exact claim/retry timings (`500/500/30000` ms) under three and six pages.
- Word-list review for unfortunate pairs; keep the 64/64 size, exactly five letters for
  adjectives, and at most five letters for animal nouns.
- Test harness helpers for killing the host page and detecting the auto-rejoined client.
