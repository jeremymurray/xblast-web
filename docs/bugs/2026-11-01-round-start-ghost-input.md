# Round-start ghost input

**Status:** draft / investigating
**Reported:** 2026-11-01
**Tree:** `fix/round-start-ghost-input` @ 28c23af (`main`, after the six-player merge).
The six-player slice changed docs, tests, `web/index.html` and `web/net.js`; the engine
is unchanged, so the engine line numbers below hold.
**Symptom:** in some matches/rounds, at the start of the round the player moves and
drops a bomb even though the player gave no such input. Not tied to a long key hold;
no "Bot Deactivated" message observed. It also happens on a new round after playing
the previous one, so the player was not away for a whole round.

## Why this file exists

The engine has several independent paths that can inject an action at `gameTime == 1`
or move/drop a bomb without a fresh key press. They look identical on screen. This file
records each candidate, the evidence for and against it, and the experiment that
distinguishes it, so we do not fix the wrong layer.

## Candidates

| # | Candidate | Needs input? | Timescale | Confidence | Distinguishing sign |
|---|---|---|---|---|---|
| C1 | Level starts player with `initVirus=bomb`/`teleport` | no | per level | medium-low | repeats all level; only on certain level names |
| C2 | Game key event leaks out of the level-intro sync queue | one tap in sync window | ~1 frame | medium | only right after "Waiting for others …" |
| C3 | Browser key auto-repeat treated as new keydown | held key | continuous | low for this report, real defect | holding bomb key spams bombs |
| C4 | `setup.bot` starts local players as bots, silently | no | every match | low (no message seen) | bot keeps playing; "Bot Deactivated" on first key |
| C5 | Silent away→bot promotion after an idle level | no | next level onward | ruled out by report | "Bot Deactivated" on first key; whole match |

The report narrows it: no bot message, played the previous round, no long hold. That
leaves C1 and C2. Note that the "moved **and** bombed" signature is one frame of
`dir + bomb`, which is what a leaked action/key pair looks like; a single virus does
only one of those, so C1 explains the bomb but not the move unless the player was
already pressing a direction.

---

## C1 — level starts the player with a virus

### Mechanism

`ConfigLevelPlayers` sets the level's initial virus as **both** current and baseline
health:

- `engine/player.c:495-497`
  ```c
  ps->illness = initHealth;
  ps->health  = initHealth;
  ps->illtime = 0;
  ```
- `initHealth` comes from the level's `[player] initVirus` (`player.c:172-185`,
  `player.c:318-333`); an absent entry means `Healthy`.
- Because `illness == health`, `DoWalk`'s heal check (`player.c:1591-1596`) never
  clears it: the virus lasts the whole level.

### Why it looks like a bug

The status bar only shows the sick face when `illness != health`
(`engine/status.c:519`). An initial virus therefore has **no visual indicator** — the
player looks healthy while the engine acts for them.

Behaviour that matches the report:

- `initVirus=bomb` — `DoWalk` drops a bomb automatically at block boundaries:
  `player.c:1601-1608`. Players start block-aligned, so this fires within the first
  frames.
- `initVirus=teleport` — random `TeleportPlayer` every 1-in-32 frames:
  `player.c:1404`.
- `initVirus=reverse`/`reverse2` — controls inverted for the level, so a normal
  direction press moves the "wrong" way (`game.c:414-450`, `player.c:1017+`).

Bundled Debian levels (`data/level/*.xal`), counts by `initVirus`:
healthy 189, **run 162**, **reverse 17**, **bomb 16**, slow 13, **teleport 10**,
malfunction 10, mini 8, invisible 5, reverse2 4, empty 3.

The 16 `bomb` levels mostly start with `bombs >= 1` (one has `bombs=0`), and a bomb
gives the player their bomb count back when it explodes (`bomb.c:772`), so a bomb-virus
player keeps dropping bombs rather than dropping one.

### Prediction

If C1: the ghost only happens on a handful of level names, and the behaviour continues
for the whole level (bombs keep appearing, or the player keeps teleporting), not just
the first second. If it is only one bomb at the very start, C1 is less likely.

### Confirmation

1. Note the level name on the intro screen when it happens.
2. Check `initVirus` in `data/level/<name>.xal`.
3. Or read it at runtime: `player_stat[0].illness` at level start (debug build, see
   Diagnostics).

### Fix (only if we decide the invisibility is the defect)

- Show the sick face when `illness == health != Healthy` in `UpdateStatusBar`
  (`status.c:517-530`).
- Optional: log `initVirus` on the intro screen or in debug output.

### Risk

Low. Display-only. Does not change gameplay. Keep the upstream behaviour.

---

## C2 — game key event leaks out of the level-intro sync

### Mechanism

`GUI_WaitEvent` queues the frame timer **before** polling SDL, then returns the first
queued event:

- `engine/sdl_event.c:662-685`
  ```c
  while (XBE_NONE == (ecode = NextEvent (data))) {
      timeout = HandleTimeout (XBFalse);   /* may QueueEventVoid (XBE_TIMER) */
      SelectSockets (timeout);
      while (SDL_PollEvent (&event)) HandleSDLEvent (&event);  /* may queue XBE_KEYB_* */
  }
  ```
- `HandleTimeout` queues `XBE_TIMER` at `sdl_event.c:617`.

The level-intro sync waits run in `KB_XBLAST` (so they can catch Escape):

- host: `WaitForClientEvent` — `game_server.c:175-262`, mode set at `:191`
- guest: `WaitForServerEvent` — `game_client.c:103-186`, mode set at `:116`

They drop key events they *dequeue* (`default: Chat_Event(...)`), but if a keydown is
polled in the same `GUI_WaitEvent` iteration as the timer that ends the wait, it is
queued *after* the timer, survives the early return, and is consumed by the first
`GameEventLoop` of the round:

- `game.c:225-319` maps `XBGK_GO_*` to `d_soll` (walking persists, `game.c:411-452`)
  and `XBGK_BOMB` to `DropBomb` (`game.c:377-380`).

The window is short: the timer is queued at the top of the iteration, `SelectSockets`
sleeps about 1 ms when the timer has expired, and the SDL poll runs after that. A
keydown must land in that tail (or already be pending) for the leak. That is why it
looks intermittent.

### Prediction

If C2: it only happens right after "Waiting for others …", and one tap is enough (no
hold). A double-tap through scoreboard + intro, or an impatient press on the wait
screen, is the natural trigger.

### Confirmation

Instrument `GameEvent` to log `(gameTime, code, data.value)` for `gameTime <= 5`, and
log every `XBE_KEYB_*` left in the queue when `GUI_SetKeyboardMode(KB_XBLAST)` is
entered. One match tells us whether a key event existed before frame 1.

### Fix

1. Add `GUI_DiscardInputEvents()` (drain `XBE_KEYB_1/2`, `XBE_JOYST_1/2`, `XBE_MENU`,
   `XBE_XBLAST` from the ring in `engine/event.c`) and call it immediately after
   `GUI_SetKeyboardMode(KB_XBLAST)` in:
   - `game_local.c:76`
   - `game_server.c:406`
   - `game_client.c:295`
2. Optionally also drain before returning from `WaitForClientEvent` /
   `WaitForServerEvent` when the waited-for event is found.
3. This is a general correctness fix, not `__EMSCRIPTEN__`-only. If we want to be
   conservative, guard the calls with `#ifdef __EMSCRIPTEN__` and a
   `/* web port: ... */` comment, per `AGENTS.md`.

### Risk

Low. Discarding queued input at the start of a level only removes input that was
captured before the level began. It cannot drop legitimate first-frame input because
the flush happens before the loop starts.

### Test

Headless CDP (`scripts/playtest.py` / `netplaytest.py` pattern): inject a keydown in
the sync window with `Input.dispatchKeyEvent`, then assert the debug log contains no
`XBGK_BOMB`/`XBGK_GO_*` at `gameTime <= 2`. See Diagnostics for the debug hook.

---

## C3 — browser auto-repeat treated as new key presses

### Mechanism

`HandleSDLEvent` ignores `SDL_KeyboardEvent.repeat`:

- `engine/sdl_event.c:505-538` handles every `SDL_KEYDOWN` identically.

SDL2 marks repeats: `SDL_SendKeyboardKeyInternal` sets `repeat = SDL_TRUE` when the key
is already down, and emscripten's DOM handler forwards every `keydown` (including
browser repeats). Upstream's SDL 1.2 build never called `SDL_EnableKeyRepeat`, so this
is new in the web port.

Consequence beyond this report: holding the bomb key drops a bomb on every repeat (one
per keydown), so "hold to bomb spam" is possible.

### Prediction

If C3 were the reported bug, the player would need to hold a key across the mode
switch (menu → level). The report says long holds were not a factor, so C3 is probably
not this symptom — but it is a real defect worth fixing.

### Fix

Ignore `event->key.repeat` for `SDL_KEYDOWN` in `HandleSDLEvent`. Movement does not
need repeats: `ps->d_soll` persists until a stop key or key release
(`game.c:411-452`), so filtering repeats does not break walking.

### Test

Hold Space across the intro; assert exactly one bomb. Without the fix, multiple bombs.

---

## C4 — `setup.bot` starts local players as bots, silently

### Mechanism

`InitPlayers` copies the config flag with no message:

- `engine/player.c:876` `ps->bot = cfgGame->setup.bot;`

The flag is the "Bot:" row in the game setup (`menu_game.c:569`) and join menu
(`menu_game.c:741`), persisted on Continue (`menu_game.c:320`) into the engine config,
which the web wrapper mirrors to `localStorage['xblast:config:v2']`
(`web/index.html:217-262`).

`Player_BotAction` then drives the player from frame 1:
`player.c:2696-2705` → `bot.c:1420`.

### Prediction

If C4: every match, not "some"; and the first key press prints "Bot Deactivated"
(`player.c:2710-2725`). The report says no such message, so C4 is unlikely — but check
the row once, and check `bot=true` in `config/local.cfg`/`server.cfg`/`client.cfg`
inside the saved config.

### Fix (if we want it)

- Print "Bot Activated" when a match starts with `setup.bot` on.
- Or make the setup row more explicit / require confirmation.
- Do not remove the feature; upstream intends it.

### Test

Start with `bot=true`; assert the status message appears at level start.

---

## C5 — silent away→bot promotion

### Mechanism

At the end of every level:

- `engine/player.c:2662-2676`
  ```c
  if (ps->away) ps->bot = XBTrue;   /* no SetMessage */
  else          ps->away = XBTrue;
  ```
- called from `game_server.c:454` and `game_client.c:368`; solo has its own copy in
  `game_local.c:144-160`.
- `ps->away` starts `XBTrue` (`player.c:890`) and is cleared by any game key
  (`Player_ActivateBot(ps, XBFalse)`, called from `game.c:250-313`).
- `ps->bot` is **not** reset per level — only at match start (`player.c:876`) — so one
  idle level makes the player a bot for the rest of the match.

### Prediction

If C5: the first key press after the ghost prints "Bot Deactivated", and the player
was idle for a whole level beforehand. The report rules this out (no message, played
the previous round). Keep it as a real UX defect to fix separately.

### Fix

- Print "Bot Activated" on the promotion.
- Decide whether one idle level should persist for the match; a per-level reset to
  `setup.bot`, or requiring two idle levels, would keep the "away players keep the
  game moving" intent without the surprise.

### Test

Idle one level, assert the next level shows the message and a way to see the state.

---

## Ruled out (with evidence)

- **Stale network actions replayed at round start.** `Dgram_Reset` sets `expect = 1`
  (`com_dgram.c:406-427`); `HandleFrames` ignores any frame whose game time is not
  `expect` (`com_dgram.c:140-202`); the client ring is cleared at level start
  (`client.c:831-848`) and the server store at `server.c:1020-1038`.
- **Stale walking direction across rounds.** `ConfigLevelPlayers` resets
  `d_ist`/`d_soll` to `GoStop` (`player.c:531-532`).
- **`PlayerAction.bot` activating a bot.** The field is only ever set false
  (`game.c:194`) and `PlayerActionFromByte` never sets it; `game.c:391` is dead.
- **Wrong player index in the network action path.** The store is indexed by global
  player and copied per player (`server.c:769-813`, `game_server.c:283-342`); no
  off-by-one found.
- **Random-seed desync at round start.** The server reseeds and sends the seed before
  level activation (`game_server.c:528-531`), and the client applies it
  (`client.c:635-640`).

## Diagnostics (one debug build settles C1/C2/C4/C5)

Build with the debug switches (they are commented in `engine/debug.h:26-43`, but `-D`
works):

```sh
CFLAGS+=" -DDEBUG_GAME -DDEBUG_DGRAM -DDEBUG_ACTION"
```

Log points to add temporarily (all removable before merge):

1. `LocalRunLevel` / `ServerRunLevel` / `ClientRunLevel`, first frame:
   `level=<name> illness=%d health=%d bot=%d away=%d d_soll=%d bombs=%d`
2. `ConfigLevelPlayers`: `initVirus=%s -> illness=%d`
3. `GameEvent`, `gameTime <= 5`: `gt=%d code=%d value=%d`
4. `GUI_SetKeyboardMode(KB_XBLAST)`: queue depth + whether any `XBE_KEYB_*` is queued
5. `HandleSDLEvent` `SDL_KEYDOWN`: `sym=%d repeat=%d mode=%d`
6. `Player_CheckLocalAway`: `away=%d bot=%d -> ...`

Run the existing harnesses plus one manual match, and note the level name when the
ghost happens. Expected outcome:

- `initVirus=bomb|teleport` on the level → C1.
- a queued `XBE_KEYB_*` before frame 1 → C2.
- `bot=1` at level start with no message → C4/C5.

## Work plan (independent of the six-player slice)

Branch per fix, small commits, one logical change each, `Assisted-by:` trailer:

1. `fix/input-queue-flush` — C2 + C3 (flush + repeat filter). Highest value, lowest
   risk. Add the CDP regression test.
2. `fix/bot-visibility` — C4 + C5 messages and the per-level reset decision.
3. `fix/virus-face` — C1 status-bar indicator, if we decide the invisibility is the
   defect.

This worktree (`../xblast-web-bugs`) is on `fix/round-start-ghost-input`, based on
`main`, so it can merge independently of `feat/six-players`. Do not touch
`web/net.js` or `scripts/nettest_js.py` from here while the six-player work is in
flight.

## Open questions

1. Solo, host, guest, or all three?
2. Does the player keep bombing/moving for the rest of the level, or once only?
3. Does the intro show a specific level name when it happens?
4. Is the setup "Bot:" row `no`?
5. Does it happen in round 1 of a match, or only after the first round?

## Handoff prompt

> Investigate round-start ghost input. Read
> `docs/bugs/2026-11-01-round-start-ghost-input.md` in the `../xblast-web-bugs`
> worktree. Build a debug variant with `-DDEBUG_GAME -DDEBUG_DGRAM -DDEBUG_ACTION`,
> add the six temporary log points, and run one match with `scripts/netplaytest.py`
> plus a manual solo match. Identify whether the level's `initVirus`, a leaked
> `XBE_KEYB_*` event, or `ps->bot` is responsible. Do not modify `web/net.js`. Report
> findings before fixing.
