# Mobile Touch Controls Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a phone or tablet user start and play XBlast TNT with on-screen controls, without changing desktop play.

**Architecture:** A small C function in `web/sdl_web.c` pushes real SDL key events for nine abstract actions. `web/index.html` adds a touch-only grid around the existing canvas and a pointer layer that calls that function. Both orientations use the same markup; two grid placements arrange it. A CDP smoke test drives headless Chrome with phone metrics.

**Tech Stack:** Emscripten 6.0.13 / SDL2 2.32.10, plain HTML/CSS/JS (no frameworks), Python 3 + Chrome DevTools Protocol for tests.

**Spec:** `docs/superpowers/specs/2026-11-04-mobile-touch-controls-design.md`

## Global Constraints

- Licence: GPL-2.0-or-later. No new third-party libraries.
- No engine gameplay, netcode, or `cfg_control` changes. The C bridge lives in `web/`.
- Touch actions map to the web defaults: up/down/left/right `Up`/`Down`/`Left`/`Right`, stop `BackSpace`, bomb `Return`, kick `Tab`, pause `P`, back `Escape`.
- Minimum touch target 44 px; `touch-action: none` on controls; safe-area insets respected.
- Desktop (no `touch-ui` class) must render exactly as today.
- Local build: `./scripts/build-web.sh --target lite-debug` (writes `web/dist-lite-debug`) or `./scripts/build-web.sh` (default release, writes `web/dist`, what the tests serve).
- Never reuse the id `play`: it is the lobby's Play button. The new wrapper is `play-area`.
- Commits: `git commit -s` and end the body with `Assisted-by: DeepSeek V4.1 Flash Free (opencode/deepseek-v4.1-flash-free)`.
- Keep `PROGRESS.md` and `AGENTS.md` current; they are the handoff documents.

## Review Focus

1. A thumb sliding off one direction onto another, or lifting outside the pad — direction must switch or stop, never stick.
2. Two fingers at once (direction + bomb) — both actions stay down; releasing one must not release the other.
3. Tab switch, phone call, or window blur while a button is held — every action releases, so the player does not return to a ghost key.
4. A touchscreen laptop or a narrow desktop window — no touch furniture appears and the desktop canvas stays centred.
5. A tap before the wasm runtime is ready or after it exits — no call into a missing/dead runtime and no console error.
6. Controls must not cover the playfield in either orientation (the requested layout).

Each item is pinned to a step in the task that owns its code.

---

### Task 1: C key bridge and build export

**Files:**
- Modify: `web/sdl_web.c`
- Modify: `scripts/build-web.sh:182`
- Create: `scripts/touchtest.py`

**Interfaces:**
- Produces: exported C function `int XBWeb_SendKey(int action, int down)`, visible in JS as `Module._XBWeb_SendKey(action, down)`. Returns 1 when the event was queued, 0 otherwise.
- Action codes: `0` up, `1` down, `2` left, `3` right, `4` stop, `5` bomb, `6` kick, `7` pause, `8` back.
- Consumes: nothing.

- [ ] **Step 1: Write the failing bridge test**

Create `scripts/touchtest.py`, modelled on `scripts/playtest.py` for Chrome launch/CDP plumbing and `scripts/netplaytest.py` for its HTTP server. Build `web/dist` with `scripts/build-web.sh` (default release) unless `XB_TEST_NO_BUILD=1`. Launch Chrome headless with `--window-size=1000,800` exactly as `playtest.py` does, so its canvas coordinates apply. The first check is `check_bridge(ws)`:

```python
# scripts/touchtest.py (core assertions)
def settle_desktop(ws):
    # exactly playtest.py's opening: end the intro, then open Solo's setup screen
    for _ in range(3):
        cdp.send_click(ws, 480, 650)
        time.sleep(1.2)
    time.sleep(0.5)
    cdp.send_click(ws, 480, 168)          # Solo
    time.sleep(1.0)

def check_bridge(ws):
    start_solo_ready(ws)                  # Play button click, wait for __xbReady
    settle_desktop(ws)
    assert_js(ws, "typeof Module._XBWeb_SendKey === 'function'")
    before = shot_hash(ws)
    time.sleep(0.5)
    assert shot_hash(ws) == before, "setup menu is not static; widen the settle wait"
    assert_js(ws, "Module._XBWeb_SendKey(5, 1)")   # bomb / Return down
    ws.call(6, "Runtime.evaluate", {"expression": "Module._XBWeb_SendKey(5, 0)"})
    time.sleep(2.5)                       # Return starts the local game
    assert shot_hash(ws) != before, "engine ignored the pushed Return key"
```

`start_solo_ready(ws)` clicks `document.getElementById('play')` and waits for
`window.__xbReady`. `shot_hash` captures the page with `Page.captureScreenshot`
and hashes the bytes. `assert_js` evaluates an expression and raises on a falsy
result. Exit non-zero on assertion failure and print `PASS` on success.

- [ ] **Step 2: Run the test to verify it fails**

Run: `python3 scripts/touchtest.py`
Expected: FAIL at `typeof Module._XBWeb_SendKey === 'function'` (or at the build/export, if the old export list is still in place).

- [ ] **Step 3: Implement the C bridge in `web/sdl_web.c`**

Add below `XBWeb_Present`:

```c
/* web port: feed engine key events from the on-screen touch controls. */
enum {
	XBWEB_KEY_UP = 0,
	XBWEB_KEY_DOWN,
	XBWEB_KEY_LEFT,
	XBWEB_KEY_RIGHT,
	XBWEB_KEY_STOP,
	XBWEB_KEY_BOMB,
	XBWEB_KEY_KICK,
	XBWEB_KEY_PAUSE,
	XBWEB_KEY_BACK
};

int
XBWeb_SendKey (int action, int down)
{
	SDL_Event event;
	SDL_Keycode sym;

	switch (action) {
	case XBWEB_KEY_UP:    sym = SDLK_UP;        break;
	case XBWEB_KEY_DOWN:  sym = SDLK_DOWN;      break;
	case XBWEB_KEY_LEFT:  sym = SDLK_LEFT;      break;
	case XBWEB_KEY_RIGHT: sym = SDLK_RIGHT;     break;
	case XBWEB_KEY_STOP:  sym = SDLK_BACKSPACE; break;
	case XBWEB_KEY_BOMB:  sym = SDLK_RETURN;    break;
	case XBWEB_KEY_KICK:  sym = SDLK_TAB;       break;
	case XBWEB_KEY_PAUSE: sym = SDLK_p;         break;
	case XBWEB_KEY_BACK:  sym = SDLK_ESCAPE;    break;
	default: return 0;
	}

	SDL_zero (event);
	event.type = down ? SDL_KEYDOWN : SDL_KEYUP;
	event.key.state = down ? SDL_PRESSED : SDL_RELEASED;
	event.key.keysym.sym = sym;
	event.key.keysym.scancode = SDL_GetScancodeFromKey (sym);
	event.key.keysym.mod = KMOD_NONE;
	return SDL_PushEvent (&event) > 0;
}
```

- [ ] **Step 4: Export it from `scripts/build-web.sh`**

Change the export list at line 182 to:

```bash
"-sEXPORTED_FUNCTIONS=['_main','_XBWeb_FlushConfig','_XBWeb_SendKey']"
```

- [ ] **Step 5: Rebuild and run the test to verify it passes**

Run: `python3 scripts/touchtest.py`
Expected: `PASS` (the setup menu is static, and the canvas changes after the injected Return).

- [ ] **Step 6: Commit**

```bash
git add web/sdl_web.c scripts/build-web.sh scripts/touchtest.py
git commit -s -m "web: push engine key events from a touch bridge" -m "Assisted-by: DeepSeek V4.1 Flash Free (opencode/deepseek-v4.1-flash-free)"
```

---

### Task 2: Touch mode, responsive layout, scrollable lobby

**Files:**
- Modify: `web/index.html` (markup, `<style>`, startup script)
- Modify: `scripts/touchtest.py` (layout, desktop and lobby checks)

**Interfaces:**
- Consumes: the `touch-ui` class on `<html>`, set before engine load.
- Produces: `#play-area` (grid), `#stage` (canvas box), `#touch` (contents in touch mode), `#pad` with `[data-action="up|down|left|right|stop"]`, `#actions` with `[data-action="bomb|kick"]`, `#sys` with `[data-action="pause|back"]`.
- Produces: `?touch=1` forces touch mode on, `?touch=0` forces it off.
- No pointer handlers yet; Task 3 adds them.

- [ ] **Step 1: Write the failing layout tests**

Extend `scripts/touchtest.py`:

```python
PHONE_PORTRAIT  = {"width": 390, "height": 844, "deviceScaleFactor": 3, "mobile": True}
PHONE_LANDSCAPE = {"width": 844, "height": 390, "deviceScaleFactor": 3, "mobile": True}
DESKTOP         = {"width": 1000, "height": 800, "deviceScaleFactor": 1, "mobile": False}

def phone(ws, metrics, touch=True):
    ws.call(Emulation.setDeviceMetricsOverride, metrics)
    ws.call(Emulation.setTouchEmulationEnabled, {"enabled": touch, "maxTouchPoints": 5})
    ws.call(Page.reload)
    wait_js(ws, "document.readyState === 'complete'")

def check_layout_portrait(ws):
    phone(ws, PHONE_PORTRAIT)
    assert_js(ws, "document.documentElement.classList.contains('touch-ui')")
    assert_js(ws, "getComputedStyle(document.getElementById('play-area')).display === 'grid'")
    start_solo_ready(ws)
    r = rects(ws, "#stage", "#pad", "#actions", "#sys")
    assert r["stage"]["top"] < r["pad"]["top"]                  # playfield pinned above
    assert r["stage"]["bottom"] <= r["pad"]["top"] + 1           # never overlapped
    assert r["pad"]["right"] <= r["actions"]["left"] + 1
    assert abs(center_x(r["sys"]) - 390 / 2) < 2                 # system row centred
    assert r["sys"]["bottom"] >= r["actions"]["bottom"] - 1      # at the bottom edge

def check_layout_landscape(ws):
    phone(ws, PHONE_LANDSCAPE)
    start_solo_ready(ws)
    r = rects(ws, "#pad", "#stage", "#actions", "#sys")
    assert r["pad"]["right"] <= r["stage"]["left"] + 1           # pad | playfield | actions
    assert r["stage"]["right"] <= r["actions"]["left"] + 1
    assert abs(center_x(r["sys"]) - center_x(r["actions"])) < 2

def check_desktop_unchanged(ws):
    phone(ws, DESKTOP, touch=False)
    assert_js(ws, "!document.documentElement.classList.contains('touch-ui')")
    assert_js(ws, "getComputedStyle(document.getElementById('play-area')).display === 'contents'")
    assert_js(ws, "getComputedStyle(document.getElementById('stage')).display === 'contents'")
    assert_js(ws, "getComputedStyle(document.getElementById('touch')).display === 'none'")
    # If Chrome keeps maxTouchPoints after the override, open a fresh target for
    # this check instead of weakening the assertion.

def check_lobby_scroll(ws):
    phone(ws, {"width": 390, "height": 600, "deviceScaleFactor": 2, "mobile": True})
    assert_js(ws, "document.getElementById('landing').scrollHeight > "
                  "document.getElementById('landing').clientHeight")
    assert_js(ws, "document.getElementById('landing').scrollTop = 1e6; true")
    assert_js(ws, "(() => { const r = document.getElementById('host').getBoundingClientRect();"
                  " return r.top >= 0 && r.bottom <= innerHeight + 1; })()")
```

`rects` returns `document.querySelector(sel).getBoundingClientRect()` as JSON.

- [ ] **Step 2: Run to verify it fails**

Run: `python3 scripts/touchtest.py`
Expected: FAIL — no `touch-ui` class, `#play-area` does not exist, `#touch` is missing.

- [ ] **Step 3: Add the touch-mode startup script**

In `web/index.html`, immediately after `<body>` (before the canvas), add:

```html
<script>
  (function () {
    var q = new URLSearchParams(location.search).get('touch');
    var forcedOff = q === '0';
    var forcedOn = q === '1';
    var coarse = window.matchMedia('(any-pointer: coarse)').matches ||
                 navigator.maxTouchPoints > 0;
    if (forcedOn || (coarse && !forcedOff)) {
      document.documentElement.classList.add('touch-ui');
    }
  })();
</script>
```

- [ ] **Step 4: Wrap the canvas and add the controls markup**

Replace the bare `<canvas>` with:

```html
<div id="play-area">
  <div id="stage">
    <canvas id="canvas" tabindex="-1" oncontextmenu="event.preventDefault()"></canvas>
  </div>
  <div id="touch" aria-label="Touch controls">
    <div id="pad">
      <span class="pad-gap"></span>
      <button class="pad-key" data-action="up" aria-label="Move up">&#9650;</button>
      <span class="pad-gap"></span>
      <button class="pad-key" data-action="left" aria-label="Move left">&#9664;</button>
      <button class="pad-key pad-stop" data-action="stop" aria-label="Stop">STOP</button>
      <button class="pad-key" data-action="right" aria-label="Move right">&#9654;</button>
      <span class="pad-gap"></span>
      <button class="pad-key" data-action="down" aria-label="Move down">&#9660;</button>
      <span class="pad-gap"></span>
    </div>
    <div id="actions">
      <button class="touch-big" data-action="bomb" aria-label="Drop bomb">BOMB</button>
      <button class="touch-big" data-action="kick" aria-label="Kick">KICK</button>
    </div>
    <div id="sys">
      <button class="touch-small" data-action="pause" aria-label="Pause">PAUSE</button>
      <button class="touch-small" data-action="back" aria-label="Back">BACK</button>
    </div>
  </div>
</div>
```

- [ ] **Step 5: Add the layout CSS**

Desktop keeps its current geometry: `#play-area, #stage { display: contents; }` and
`#touch { display: none; }`. `display: contents` on both wrappers leaves the
canvas as the direct flex item of `body`, so all existing `max-width/height`
percentages keep resolving as they do today.

Touch mode rules (add to the existing `<style>`):

```css
html.touch-ui, html.touch-ui body { height: 100%; overflow: hidden; }
html.touch-ui body { display: block; }
html.touch-ui #play-area {
  display: grid; box-sizing: border-box;
  width: 100vw; height: 100vh; height: 100dvh;
  grid-template-columns: minmax(0, 1fr) minmax(0, 2.4fr) minmax(0, 1fr);
  grid-template-rows: minmax(0, 1fr) auto;
  align-items: center; gap: 8px;
  padding: max(6px, env(safe-area-inset-top)) max(6px, env(safe-area-inset-right))
           max(6px, env(safe-area-inset-bottom)) max(6px, env(safe-area-inset-left));
}
/* landscape placement: pad and stage span both rows, actions centred on them,
   system row at the bottom of the action column */
html.touch-ui #pad    { grid-area: 1 / 1 / 3 / 2; }
html.touch-ui #stage  { grid-area: 1 / 2 / 3 / 3; }
html.touch-ui #actions{ grid-area: 1 / 3 / 3 / 4; }
html.touch-ui #sys    { grid-area: 2 / 3 / 3 / 4; }
html.touch-ui #stage {
  display: flex; align-items: center; justify-content: center;
  min-width: 0; min-height: 0; width: 100%; height: 100%;
}
html.touch-ui #touch { display: contents; }
html.touch-ui #pad {
  display: grid; grid-template-columns: repeat(3, 1fr);
  gap: 6px; width: 100%; max-width: calc(3 * 64px + 12px);
  align-self: center; justify-self: center;
}
html.touch-ui #actions {
  display: flex; flex-direction: column; justify-content: center;
  gap: 12px; align-self: stretch; min-height: 0;
}
html.touch-ui #sys { display: flex; justify-content: center; align-items: flex-end; gap: 10px; }
html.touch-ui canvas { max-width: 100%; max-height: 100%; width: auto; height: auto; }

html.touch-ui .pad-key {
  aspect-ratio: 1; min-width: 44px; min-height: 44px; padding: 0;
  font: 600 clamp(12px, 3.2vmin, 18px)/1 ui-monospace, monospace;
  color: #ddd; background: #262626; border: 1px solid #555; border-radius: 10px;
  touch-action: none; user-select: none; -webkit-user-select: none;
  -webkit-tap-highlight-color: transparent;
}
html.touch-ui .pad-key.pad-stop { background: #332e17; border-color: #8a7a30; color: #ffd400; font-size: 10px; }
html.touch-ui .pad-gap { visibility: hidden; }
html.touch-ui .touch-big {
  width: 100%; min-height: 56px; height: clamp(56px, 19vh, 84px);
  border-radius: 10px; font: 700 clamp(10px, 2.6vmin, 13px)/1.2 ui-monospace, monospace;
  color: #ff8a8a; background: #3a1f1f; border: 2px solid #7a3b3b;
  touch-action: none; user-select: none; -webkit-user-select: none;
  -webkit-tap-highlight-color: transparent;
}
html.touch-ui .touch-big[data-action="kick"] { color: #ffd400; background: #332e17; border-color: #7a6a2b; }
html.touch-ui .touch-small {
  min-height: 44px; padding: 8px 14px; border-radius: 6px;
  font: 600 10px/1 ui-monospace, monospace; letter-spacing: .08em;
  color: #bbb; background: #222; border: 1px solid #555;
  touch-action: none; user-select: none; -webkit-user-select: none;
  -webkit-tap-highlight-color: transparent;
}

@media (orientation: portrait) {
  html.touch-ui #play-area {
    grid-template-columns: minmax(0, 1.7fr) minmax(0, 1fr);
    grid-template-rows: auto minmax(0, 1fr) auto;
    grid-template-areas: "stage stage" "pad actions" "sys sys";
    align-items: center;
  }
  html.touch-ui #stage   { grid-area: stage; aspect-ratio: 480 / 368; align-self: start; height: auto; }
  html.touch-ui #pad     { grid-area: pad; }
  html.touch-ui #actions { grid-area: actions; align-self: center; padding-right: 0; }
  html.touch-ui #sys     { grid-area: sys; align-self: end; justify-content: center; padding-top: 4px; }
}
```

Notes the implementer must keep:
- In landscape `#actions` spans both rows so Bomb+Kick centre on the pad's centre
  line; `#sys` occupies the bottom row of that same column.
- In portrait Bomb+Kick are centred in the controls row and the system row
  spans both columns at the bottom, centred.
- Hide the keys hints and move (do not hide) the status line:

```css
html.touch-ui #keyhints { display: none !important; }
html.touch-ui #status {
  top: max(6px, env(safe-area-inset-top)); bottom: auto; left: 50%;
  transform: translateX(-50%); white-space: nowrap;
}
```

- [ ] **Step 6: Make the lobby scroll on short screens**

In the existing `.screen` rule add `overflow-y: auto; -webkit-overflow-scrolling: touch;`
and change `align-items: center` to `align-items: flex-start`; change `.panel`
to `margin: auto;` so it centres when it fits and scrolls from the top when it
does not. (Centring a flex container that overflows clips the top; auto margins
do not.) Add `viewport-fit=cover` to the viewport meta tag
and give `#landing .panel` `padding-bottom: max(2em, env(safe-area-inset-bottom));`.

- [ ] **Step 7: Run the tests to verify they pass**

Run: `python3 scripts/touchtest.py`
Expected: `PASS` for bridge + portrait + landscape + desktop + lobby scroll.

- [ ] **Step 8: Commit**

```bash
git add web/index.html scripts/touchtest.py
git commit -s -m "web: add touch layout for landscape and portrait" -m "Assisted-by: DeepSeek V4.1 Flash Free (opencode/deepseek-v4.1-flash-free)"
```

---

### Task 3: Pointer handling, action mapping, release safety

**Files:**
- Modify: `web/index.html` (pointer layer and `XBTouch` helper)
- Modify: `scripts/touchtest.py` (`check_input`)

**Interfaces:**
- Consumes: `Module._XBWeb_SendKey(code, down)` from Task 1; `[data-action]` elements from Task 2.
- Produces: `globalThis.XBTouch` with:
  - `press(name: string): void` and `release(name: string): void`, `name` one of `up down left right stop bomb kick pause back`;
  - `active(): string[]` (sorted, currently held);
  - `log: Array<{name: string, down: boolean, ts: number}>` (last 50);
  - `enabled: boolean` (true only after the runtime is ready and false after exit).
- Produces: `data-action` → action code map in the page, matching Task 1. `XBTouch` exists whenever the runtime is ready, even without the touch UI, so the test can drive it on desktop.

- [ ] **Step 1: Write the failing input tests**

Add to `scripts/touchtest.py`:

```python
def check_input(ws):
    phone(ws, PHONE_PORTRAIT)
    start_solo_ready(ws)
    assert_js(ws, "typeof XBTouch === 'object' && XBTouch.enabled === true")

    # one tap sends the action down and up
    tap(ws, "#pad [data-action=down]")
    assert_js(ws, "XBTouch.log.some(e => e.name === 'down' && e.down === true)")
    assert_js(ws, "XBTouch.log.some(e => e.name === 'down' && e.down === false)")

    # two fingers: direction + bomb stay held, releasing one keeps the other
    multi_touch_start(ws, [("#pad [data-action=left]", 1), ("#actions [data-action=bomb]", 2)])
    assert_js(ws, "JSON.stringify(XBTouch.active()) === JSON.stringify(['bomb','left'])")
    touch_release(ws, 1)
    assert_js(ws, "JSON.stringify(XBTouch.active()) === JSON.stringify(['bomb'])")
    touch_release(ws, 2)

    # sliding from left to up switches without sticking
    slide(ws, "#pad [data-action=left]", "#pad [data-action=up]")
    assert_js(ws, "JSON.stringify(XBTouch.active()) === JSON.stringify(['up'])")

    # blur releases everything
    touch_start(ws, "#pad [data-action=right]", 3)
    assert_js(ws, "XBTouch.active().length === 1")
    assert_js(ws, "window.dispatchEvent(new Event('blur')); true")
    assert_js(ws, "XBTouch.active().length === 0")
    touch_release(ws, 3)

    # before the runtime is ready the layer is inert
    phone(ws, PHONE_PORTRAIT)                      # reload; engine not started
    assert_js(ws, "typeof XBTouch === 'undefined' || XBTouch.enabled !== true")
    assert_js(ws, "document.getElementById('touch').offsetParent === null")

    # after the runtime handler runs, presses are inert
    start_solo_ready(ws)
    assert_js(ws, "(() => { const n = XBTouch.log.length; Module.onExit(0);"
                  " XBTouch.press('down'); return XBTouch.enabled === false &&"
                  " XBTouch.log.length === n; })()")

    # engine integration: the same desktop path as Task 1, driven by XBTouch
    phone(ws, DESKTOP, touch=False)
    start_solo_ready(ws)
    settle_desktop(ws)
    before = shot_hash(ws)
    time.sleep(0.5)
    assert shot_hash(ws) == before
    assert_js(ws, "XBTouch.press('bomb'); XBTouch.release('bomb'); true")
    time.sleep(2.5)
    assert shot_hash(ws) != before
```

Helpers `tap`, `touch_start`, `touch_move`, `touch_release`, `multi_touch_start`
and `slide` wrap CDP `Input.dispatchTouchEvent` with element-centre coordinates.
`touch_release(ws, id)` sends a `touchEnd` whose `touchPoints` contains the
still-active points (an empty list releases all). Element centres come from
`getBoundingClientRect()`.

- [ ] **Step 2: Run to verify it fails**

Run: `python3 scripts/touchtest.py`
Expected: FAIL — `XBTouch` is undefined and tapping the pad changes nothing.

- [ ] **Step 3: Implement the action map and bridge calls**

In the main page script add:

```js
const TOUCH_ACTIONS = {
  up: 0, down: 1, left: 2, right: 3, stop: 4, bomb: 5, kick: 6, pause: 7, back: 8,
};
```

`XBTouch.press(name)` calls `Module._XBWeb_SendKey(code, 1)`; `release` calls it
with 0. Neither calls into the module unless `XBTouch.enabled` is true and the
export exists. `enabled` becomes true in `Module.onRuntimeInitialized` and false
in `Module.onExit`. Append to `log` on every successful call and cap it at 50
entries.

- [ ] **Step 4: Implement the pointer layer**

- The Bomb, Kick, Pause and Back buttons each use their own handler:
  `pointerdown` → capture (`setPointerCapture`), `press(action)`; `pointerup`,
  `pointercancel`, `lostpointercapture` → `release(action)`.
- The pad buttons have no individual handlers; `#pad` uses one delegated capture model: on `pointerdown` inside the pad,
  record `pointerId → action` and press it; on `pointermove`, convert the
  pointer's client coordinates into one of the nine cells with the pad's
  bounding rect. Corners are dead. If the cell's action changes, release the old
  action and press the new one. On `pointerup`/`pointercancel`/
  `lostpointercapture`, release and forget the pointer.
- Maintain `pressedCount[action]`; only call the bridge on 0→1 and 1→0 so
  multiple pointers and repeated actions do not double-send.
- `window.addEventListener('blur', releaseAll)` and a `visibilitychange`
  listener that calls `releaseAll` when `document.visibilityState === 'hidden'`.
- Call `event.preventDefault()` on control `pointerdown`; CSS already sets
  `touch-action: none`.

- [ ] **Step 5: Run the input tests to verify they pass**

Run: `python3 scripts/touchtest.py`
Expected: `PASS`.

- [ ] **Step 6: Desktop regression**

Run: `./scripts/build-web.sh`
Run in a second shell: `python3 -m http.server 8123 --directory web/dist`
Run: `python3 scripts/playtest.py http://localhost:8123/index.html <outdir>`
Expected: the scripted keyboard play still reaches the maze and writes its screenshots.

- [ ] **Step 7: Commit**

```bash
git add web/index.html scripts/touchtest.py
git commit -s -m "web: wire touch buttons to the engine and release held keys" -m "Assisted-by: DeepSeek V4.1 Flash Free (opencode/deepseek-v4.1-flash-free)"
```

---

### Task 4: Documentation and progress record

**Files:**
- Modify: `README.md`
- Modify: `PROGRESS.md`
- Modify: `AGENTS.md`

- [ ] **Step 1: README controls**

Add a paragraph after the keyboard controls list: touch controls appear
automatically on touch devices (`?touch=1` forces them, `?touch=0` hides them);
movement pad with centre Stop on the left, Bomb/Kick on the right, Pause and
Back at the bottom; they follow the default web bindings, so a remapped P1
keyboard layout is not mirrored.

- [ ] **Step 2: PROGRESS.md**

Add the touch-control item to the current checklist, note `scripts/touchtest.py`
under how to run, and set the next task to manual iOS/Android acceptance.

- [ ] **Step 3: AGENTS.md**

Record the decisions: the C SDL key bridge instead of synthetic keyboard
events, the action→key table, automatic `touch-ui` activation with `?touch`
overrides, the two layouts, and the default-binding limitation.

- [ ] **Step 4: Verify**

Run: `grep -n "touch" README.md PROGRESS.md AGENTS.md`
Expected: the new sections are present and consistent with the key map.

- [ ] **Step 5: Commit**

```bash
git add README.md PROGRESS.md AGENTS.md
git commit -s -m "docs: describe the mobile touch controls" -m "Assisted-by: DeepSeek V4.1 Flash Free (opencode/deepseek-v4.1-flash-free)"
```

---

## Final verification

- [ ] `python3 scripts/touchtest.py` passes from a clean `web/dist` build.
- [ ] `python3 scripts/playtest.py` still passes against the same build.
- [ ] Manual, recorded in `PROGRESS.md`: iOS Safari and Android Chrome, portrait
      and landscape, solo and a two-device netplay match; no page scroll, no
      zoom, no stuck movement after backgrounding.
- [ ] Tag the release only after the manual pass, per the project versioning rule.
