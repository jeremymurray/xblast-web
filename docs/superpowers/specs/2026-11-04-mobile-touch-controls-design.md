# Mobile touch controls

Date: 2026-11-04
Status: design, awaiting approval
Scope: play the existing game on a phone or tablet, solo or networked

## 1. Context

The page loads and renders on a phone, but the only input path is a keyboard.
`web/index.html` owns the lobby and the Emscripten module, and the engine still
reads SDL keyboard events in `engine/sdl_event.c`. Player 1's web defaults
(`engine/cfg_control.c`, `__EMSCRIPTEN__` branch) are arrows for movement,
BackSpace to stop, Return to bomb, Tab for the level's special, P to pause and
Escape to leave. The engine's own menus are keyboard-only too: arrows navigate,
Return/Space select, Escape aborts, Tab/BackSpace step (`menuKeyTable`).

The playfield is 480×368 (PIXW × PIXH+SCOREH) and the canvas scales to fit its
container. The landing panel can be taller than a short phone viewport, and
`body { overflow: hidden }` plus a centred fixed `.screen` means Host/Join can
be unreachable before the game even loads.

## 2. Intent

A phone or tablet user opens the page, taps Play, navigates the engine's menus,
and plays a real match with on-screen controls. Desktop keyboard play is
unchanged.

## 3. Goals

1. On-screen controls that cover every action needed to start and play a match:
   movement, stop, bomb, special, pause, level abort/cancel, and back/leave.
2. The controls drive the same engine input path as the keyboard, so menus,
   local play and netplay all work without engine game-logic changes.
3. A landscape layout with the pad on the left, the playfield in the middle and
   the action buttons on the right.
4. A portrait layout with the playfield pinned to the top and the controls
   across the bottom, Game Boy style.
5. The landing screen scrolls on short screens, so the lobby is usable.
6. Desktop remains exactly as it is: no new furniture without a touch device.
7. A repeatable headless check for the layout and the input plumbing.

## 4. Non-goals

- Remapping the touch buttons. They use the web defaults and do not follow a
  custom P1 binding set.
- Gestures, swipe movement, vibration or haptics.
- Forced orientation, orientation locking, or a fullscreen prompt.
- In-match menus or chat input on touch.
- Changing engine gameplay, netcode or key defaults.
- A native app wrapper or PWA install prompt.

## 5. Anti-goals

- A second game UI in HTML that duplicates engine menus.
- Controls that cover the playfield in landscape.
- A desktop user suddenly seeing phone controls because of a narrow window.
- Touches that scroll, zoom or pull-to-refresh the page.
- Stuck keys after a tab switch or a lost pointer.

## 6. Constraints

- Emscripten SDL2 2.32.10 only creates an SDL key event when the browser event
  has a recognised `code`, and it derives the SDL keysym from the legacy
  `keyCode` field (`SDL_emscriptenevents.c`). Synthetic `KeyboardEvent`s
  therefore depend on browser-specific legacy-field support.
- `SDL_PushEvent` runs the engine's event filter and then its normal
  `SDL_PollEvent` path, exactly like a hardware key.
- The canvas is 480×368 and is the only thing the engine draws.
- The web build already exports one C function to page JS
  (`_XBWeb_FlushConfig`), so the mechanism has precedent.
- Mobile browsers need a secure context for netplay; that is already a
  deployment constraint.
- The work must stay small, static-hosted and GPL-2.0-or-later compatible.

## 7. Approaches

### Input plumbing

**A. C bridge that pushes SDL key events (recommended).** Add a small
`XBWeb_SendKey(action, down)` to `web/sdl_web.c`, export it, and let JS call it
on press/release. It builds an `SDL_KEYDOWN`/`SDL_KEYUP` with the SDL keysym for
the web default binding and calls `SDL_PushEvent`. This enters the engine at
exactly the same place as a real key, works in menus and matches, needs no
per-browser event simulation, and is testable from the page. Cost: one C
function, one build export, and a wasm rebuild.

**B. Synthetic `KeyboardEvent` from JS.** Dispatch a keydown/keyup on `window`
with `key`, `code`, `keyCode` and `which`. No wasm rebuild, but SDL only forwards
it when `code` and the legacy `keyCode` both land correctly; support is uneven
across browsers and breaks silently. Rejected.

**C. Inject engine action events directly.** Push `XBGK_*` values into the
engine's event queue for gameplay, and use key events only for menus. This
would survive a remapped P1 config, but it duplicates the engine's action
mapping, leaves the key-up/stop semantics to reimplement, and still needs the
key bridge for menus. Rejected for this cut.

Chosen: **A**. The C bridge is smaller and it exercises the engine's real input
path. The default-binding caveat is acceptable because the touch user has no
keyboard with which to have remapped it, and a desktop user does not see the
pads.

### Page layout

**A. A grid page mode around the existing canvas (recommended).** Wrap the
canvas in a `#play-area` grid, add the pad/actions/system row as siblings, and
turn the grid on only under a `touch-ui` root class. Portrait and landscape are
two grid placements. The canvas keeps scaling as it does now. No engine
coordinate changes, no duplicated markup.

**B. Absolutely positioned overlays on top of the canvas.** The playfield stays
full-screen and the controls float over its lower corners. Simpler CSS, but the
controls cover part of the maze, which conflicts with the requested layout.

**C. A separate mobile page.** Duplicates the lobby, net glue and config
mirroring. Rejected.

Chosen: **A**.

## 8. Design

### 8.1 Touch mode

Set `touch-ui` on `<html>` before the engine loads when
`matchMedia('(any-pointer: coarse)').matches` or `navigator.maxTouchPoints > 0`.
Allow `?touch=1` and `?touch=0` to force it for testing and for a desktop
touchscreen. The class controls both visibility of `#touch` and the page grid;
without it, `#play-area, #stage { display: contents }` keeps today's centred
canvas as a direct flex item of `body`.

`#touch` is hidden until the engine runtime is ready (`__xbReady`) and hidden
again on `Module.onExit`, so no button can press into a dead runtime.

### 8.2 Layout

`#play-area` is a three-area grid in landscape with a full-width system row:

```
pad | playfield | actions
pause  abort  cancel  back
```

and in portrait:

```
playfield playfield
pad       actions
pause/back (centred, full width)
```

- The canvas sits in the playfield area, centred, `max-width/height: 100%`.
- The pad is a 3×3 grid of square buttons with a STOP button in the centre.
- Actions are equal-sized rectangles: BOMB above KICK, centred vertically on
  the pad's centre line. In portrait the column is flush to the right edge and
  the pad gets the wider column.
- PAUSE, ABORT, CANCEL and BACK sit on the bottom edge in both orientations,
  centred across the full width.
- Sizes use `dvh`/`vw` clamps with a 44 px minimum, and safe-area insets pad
  the page. `100dvh` is used with a `100vh` fallback.
- The KEYHINTS overlay is hidden in touch mode. `#status` stays visible (moved
  to the top centre) so "Loading…" is not a blank screen; the netbar stays,
  because Leave/Invite are needed.

### 8.3 Key map

| Control | Action code | SDL key | Menu role |
|---|---|---|---|
| D-pad | up/down/left/right | Up/Down/Left/Right | navigate |
| centre | stop | BackSpace | previous / change a combo |
| BOMB | bomb | Return | default (Start) |
| SPECIAL | special | Tab in play, Space in menus | select |
| PAUSE | pause | P | none |
| ABORT | abort | `/` | none (level-abort vote) |
| CANCEL | cancel | `.` | none (clears the vote) |
| BACK | back | Escape | abort |

A tap on the playfield is translated into a synthetic
`mousemove`/`mousedown`/`mouseup` on the canvas, because the engine's menus are
mouse-aware and SDL2 forwards no mouse event for a raw touch. Tapping a menu item
therefore selects it. The setup screen keeps the engine's rule that a local game
needs two players before Start activates; the touch buttons can assign them
(tap a combo, Stop cycles its value, Special closes it).

The codes are a small integer enum shared by `web/sdl_web.c` and the page.
`XBWeb_SendKey` sets `state`, `keysym.sym` and `scancode` and returns whether
the event was queued. Escape already triggers the engine's existing
`HotKey_Quit` filter and `XBXK_EXIT` path; the touch button adds no new
behaviour there.

### 8.4 Pointer handling

- Buttons use pointer events with `touch-action: none`,
  `user-select: none` and the tap-highlight removed.
- The pad captures the pointer and hit-tests its 3×3 geometry on move, so a
  thumb can slide from one direction to another without lifting. The four
  corners are dead.
- Track `pointerId → action` and `action → press count`; send keydown on 0→1 and
  keyup on 1→0. This supports direction-plus-bomb multi-touch and prevents a
  second finger from releasing an action it did not start.
- Release every held action on `pointercancel`, `blur` and
  `visibilitychange`, so backgrounding cannot leave a ghost key.
- Action buttons use the same small helper as the pad's centre and action keys.

### 8.5 Mobile lobby

Make `.screen` scroll: `overflow-y: auto`, `align-items: flex-start`, and
`.panel { margin: auto }` so the panel stays centred when it fits and becomes
scrollable when it does not. Add `viewport-fit=cover`, safe-area padding on the
lobby, and keep `touch-action` off the landing content so the inputs still
behave.

### 8.6 Files

- `web/index.html`: markup, touch CSS, activation and pointer handling, lobby
  scroll fix, hint text update.
- `web/sdl_web.c`: `XBWeb_SendKey` and its action enum.
- `scripts/build-web.sh`: export `_XBWeb_SendKey`.
- `scripts/touchtest.py`: headless layout/input smoke test (new).
- `README.md`, `PROGRESS.md`, `AGENTS.md`: controls, status, decision record.

## 9. Testing

- `scripts/touchtest.py`, modelled on `scripts/playtest.py`, drives headless
  Chrome through CDP with a phone viewport and touch emulation:
  1. touch mode is active and `#touch` is visible once the runtime is ready;
  2. portrait geometry: playfield above the pad, pad left of the actions, PAUSE
     and BACK centred at the bottom;
  3. landscape geometry: pad left of the playfield, playfield left of the
     actions;
  4. a CDP touch on the pad records the expected action and sends one event;
  5. after the intro settles, a menu screenshot pair taken with no input is
     identical, and a pad tap changes the canvas — proving the engine consumed
     the pushed key and the menu moved.
- Existing `scripts/playtest.py` must still pass unchanged (desktop).
- Manual: iOS Safari and Android Chrome, portrait and landscape, solo and a
  two-device netplay match; check no page scroll, zoom, or stuck movement after
  backgrounding.

## 10. Open calls left to the builder

- Exact pad and action sizes within the clamps, and the precise safe-area
  padding.
- Whether the portrait system row is inside the grid or positioned absolutely,
  as long as it is centred on the bottom edge.
- The test's screenshot-stability guard: if the engine menu animates, assert
  on the recorded action log and the canvas size instead of a pixel diff.
- Whether to expose a tiny `XBTouch` debug object for the test; it must be
  harmless in production.
