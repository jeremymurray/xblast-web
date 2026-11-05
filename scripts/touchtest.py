#!/usr/bin/env python3
"""Acceptance test for the mobile touch controls.

Builds the release bundle unless XB_TEST_NO_BUILD=1, serves it locally, and
drives headless Chrome through the DevTools protocol:

  bridge   the C key bridge exists and the engine reacts to a pushed key
  (the layout and pointer checks are added by later tasks)

Usage: python3 scripts/touchtest.py
"""
import base64
import functools
import hashlib
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.parse
import urllib.request
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

SCRIPTS = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(SCRIPTS, ".."))
DIST = os.path.join(ROOT, "web", "dist")
sys.path.insert(0, SCRIPTS)
import cdp_shot as cdp  # noqa: E402

SERVER_PORT = 8123


def free_port():
    sock = socket.socket()
    try:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]
    finally:
        sock.close()


def start_server():
    class Handler(SimpleHTTPRequestHandler):
        def log_message(self, fmt, *args):
            pass

    class Server(ThreadingHTTPServer):
        daemon_threads = True
        allow_reuse_address = True

    handler = functools.partial(Handler, directory=DIST)
    try:
        server = Server(("127.0.0.1", SERVER_PORT), handler)
        port = SERVER_PORT
    except OSError:
        port = free_port()
        server = Server(("127.0.0.1", port), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, f"http://127.0.0.1:{port}"


def wait_js(ws, expression, timeout=90):
    end = time.time() + timeout
    while time.time() < end:
        try:
            result = ws.call(6, "Runtime.evaluate", {
                "expression": expression, "returnByValue": True,
            })
        except RuntimeError:
            time.sleep(0.2)          # the execution context is being replaced
            continue
        if (result.get("result") or {}).get("value"):
            return
        time.sleep(0.2)
    raise AssertionError(f"timed out waiting for {expression}")


def js(ws, expression):
    result = ws.call(6, "Runtime.evaluate", {
        "expression": expression, "returnByValue": True,
    })
    if result.get("exceptionDetails"):
        details = result["exceptionDetails"]
        text = details.get("exception", {}).get("description") or details.get("text")
        raise AssertionError(f"{text} in {expression}")
    if (result.get("result") or {}).get("subtype") == "error":
        raise AssertionError(result["result"].get("description", expression))
    return (result.get("result") or {}).get("value")


def assert_js(ws, expression, message=None):
    if not js(ws, expression):
        raise AssertionError(message or f"assertion failed: {expression}")


def start_solo_ready(ws):
    js(ws, "document.getElementById('play').click(); true")
    wait_js(ws, "!!window.__xbReady")
    time.sleep(0.5)


def dismiss_intro(ws):
    """End the intro's input wait with empty-area clicks, as playtest.py does."""
    for _ in range(3):
        cdp.send_click(ws, 480, 650)
        time.sleep(1.2)
    time.sleep(0.5)


def settle_desktop(ws):
    """The opening sequence from playtest.py: end the intro, open Solo."""
    dismiss_intro(ws)
    cdp.send_click(ws, 480, 168)   # Solo
    time.sleep(1.0)


def shot_hash(ws):
    data = ws.call(30, "Page.captureScreenshot", {"format": "png"})["data"]
    return hashlib.sha256(base64.b64decode(data)).hexdigest()


def save_shot(ws, name):
    folder = os.environ.get("XB_TOUCH_SHOTS")
    if not folder:
        return
    os.makedirs(folder, exist_ok=True)
    data = ws.call(31, "Page.captureScreenshot", {"format": "png"})["data"]
    with open(os.path.join(folder, name + ".png"), "wb") as handle:
        handle.write(base64.b64decode(data))


PHONE_PORTRAIT = {"width": 390, "height": 844, "deviceScaleFactor": 3, "mobile": True}
PHONE_LANDSCAPE = {"width": 844, "height": 390, "deviceScaleFactor": 3, "mobile": True}
DESKTOP = {"width": 1000, "height": 800, "deviceScaleFactor": 1, "mobile": False}


def phone(ws, metrics, touch=True):
    ws.call(40, "Emulation.setDeviceMetricsOverride", metrics)
    ws.call(41, "Emulation.setTouchEmulationEnabled",
            {"enabled": touch, "maxTouchPoints": 5})
    ws.call(42, "Page.reload")
    wait_js(ws, "document.readyState === 'complete' && !!document.getElementById('play')", 30)


def rects(ws, *selectors):
    expression = "JSON.stringify(Object.fromEntries(%s.map(s => { const r =" \
                 " document.querySelector(s).getBoundingClientRect();" \
                 " return [s.replace(/^#/, ''), {top:r.top, bottom:r.bottom, left:r.left," \
                 " right:r.right, width:r.width, height:r.height}]; })))" \
                 % json.dumps(list(selectors))
    return json.loads(js(ws, expression))


def center_x(rect):
    return (rect["left"] + rect["right"]) / 2


ACTIVE_TOUCHES = {}


def center_of(ws, selector):
    expression = ("(() => { const r = document.querySelector(%s)"
                  ".getBoundingClientRect(); return JSON.stringify("
                  "{x: r.left + r.width / 2, y: r.top + r.height / 2}); })()"
                  % json.dumps(selector))
    return json.loads(js(ws, expression))


def dispatch_touch(ws, kind, points):
    ws.call(50, "Input.dispatchTouchEvent", {"type": kind, "touchPoints": points})


def touch_points():
    return [{"x": v["x"], "y": v["y"], "id": k} for k, v in ACTIVE_TOUCHES.items()]


def touch_start(ws, selector, pid=0):
    point = center_of(ws, selector)
    ACTIVE_TOUCHES[pid] = point
    dispatch_touch(ws, "touchStart", touch_points())


def touch_move_to(ws, selector, pid=0):
    ACTIVE_TOUCHES[pid] = center_of(ws, selector)
    dispatch_touch(ws, "touchMove", touch_points())


def touch_release(ws, pid=0):
    point = ACTIVE_TOUCHES.pop(pid, None)
    dispatch_touch(ws, "touchEnd", [point] if point else [])


def tap(ws, selector):
    touch_start(ws, selector, 0)
    time.sleep(0.1)
    touch_release(ws, 0)


def pointer_at(ws, kind, pid, x, y, selector="#pad"):
    expression = """(() => { const el = document.querySelector(%s);
      el.dispatchEvent(new PointerEvent(%s, {
        pointerId: %d, pointerType: 'touch', bubbles: true, cancelable: true,
        clientX: %s, clientY: %s,
      })); return true; })()""" % (
        json.dumps(selector), json.dumps(kind), pid, json.dumps(x), json.dumps(y))
    js(ws, expression)


def rect_union(ws, selector):
    expression = ("(() => { const rs = [...document.querySelectorAll(%s)]"
                  ".map(e => e.getBoundingClientRect()); return JSON.stringify({"
                  "left: Math.min(...rs.map(r => r.left)),"
                  "right: Math.max(...rs.map(r => r.right))}); })()"
                  % json.dumps(selector))
    return json.loads(js(ws, expression))


def canvas_tap(ws, gx, gy):
    """Tap the canvas at engine pixels (480x368), e.g. a menu button."""
    r = rects(ws, "#canvas")["canvas"]
    x = r["left"] + gx / 480 * r["width"]
    y = r["top"] + gy / 368 * r["height"]
    ACTIVE_TOUCHES[99] = {"x": x, "y": y}
    dispatch_touch(ws, "touchStart", [{"x": x, "y": y, "id": 99}])
    dispatch_touch(ws, "touchEnd", [])


def pointer_events(ws, events):
    """Dispatch synthetic PointerEvents.

    Chrome's Input.dispatchTouchEvent ends every touch on touchEnd, so partial
    multi-touch release has to be driven at the pointer layer directly.
    """
    payload = [{"selector": sel, "kind": kind, "id": pid} for sel, kind, pid in events]
    expression = """(() => {
      const evs = %s;
      for (const e of evs) {
        const el = document.querySelector(e.selector);
        const r = el.getBoundingClientRect();
        el.dispatchEvent(new PointerEvent(e.kind, {
          pointerId: e.id, pointerType: 'touch', isPrimary: e.id === evs[0].id,
          bubbles: true, cancelable: true,
          clientX: r.left + r.width / 2, clientY: r.top + r.height / 2,
        }));
      }
      return true;
    })()""" % json.dumps(payload)
    js(ws, expression)


def slide(ws, start, end, pid=0):
    touch_start(ws, start, pid)
    time.sleep(0.1)
    touch_move_to(ws, end, pid)


def check_bridge(ws):
    start_solo_ready(ws)
    dismiss_intro(ws)              # settle on the engine main menu
    assert_js(ws, "typeof Module._XBWeb_SendKey === 'function'",
              "the C key bridge is not exported")
    # The main menu's abort button is Quit; Escape must leave the engine and the
    # page's onExit must show the "Play again" overlay. Before the key, it is not
    # showing, so the change is caused by the pushed event.
    assert_js(ws, "!document.getElementById('overlay').classList.contains('show')",
              "overlay is already visible before sending the key")
    js(ws, "Module._XBWeb_SendKey(8, 1); Module._XBWeb_SendKey(8, 0); true")
    wait_js(ws, "document.getElementById('overlay').classList.contains('show')", 15)


def check_layout_portrait(ws):
    phone(ws, PHONE_PORTRAIT)
    assert_js(ws, "document.documentElement.classList.contains('touch-ui')",
              "touch mode did not activate on a phone viewport")
    assert_js(ws, "getComputedStyle(document.getElementById('play-area')).display === 'grid'",
              "the touch page grid is not active")
    start_solo_ready(ws)
    r = rects(ws, "#stage", "#pad", "#actions", "#sys")
    width = js(ws, "innerWidth")
    if not r["stage"]["top"] < r["pad"]["top"]:
        raise AssertionError("the playfield is not pinned above the pad in portrait")
    if not r["stage"]["bottom"] <= r["pad"]["top"] + 1:
        raise AssertionError("the playfield overlaps the pad in portrait")
    if not r["pad"]["right"] <= r["actions"]["left"] + 1:
        raise AssertionError("the pad overlaps the actions in portrait")
    if not abs(center_x(r["sys"]) - width / 2) < 2:
        raise AssertionError("the system row is not centred in portrait")
    if not r["sys"]["bottom"] >= r["actions"]["bottom"] - 1:
        raise AssertionError("the system row is not at the bottom in portrait")


def check_layout_landscape(ws):
    phone(ws, PHONE_LANDSCAPE)
    start_solo_ready(ws)
    r = rects(ws, "#pad", "#stage", "#actions", "#sys")
    if not r["pad"]["right"] <= r["stage"]["left"] + 1:
        raise AssertionError("the pad overlaps the playfield in landscape")
    if not r["stage"]["right"] <= r["actions"]["left"] + 1:
        raise AssertionError("the actions overlap the playfield in landscape")
    if not abs(center_x(r["sys"]) - center_x(r["actions"])) < 2:
        raise AssertionError("the system row is not under the actions in landscape")
    for width, height in ((568, 320), (640, 360)):
        phone(ws, {"width": width, "height": height, "deviceScaleFactor": 2, "mobile": True})
        start_solo_ready(ws)
        pad = rect_union(ws, "#pad [data-action]")
        canvas = rects(ws, "#canvas")["canvas"]
        actions = rect_union(ws, "#actions [data-action]")
        if pad["right"] > canvas["left"] + 0.5:
            raise AssertionError(f"pad overlaps the canvas at {width}x{height}")
        if canvas["right"] > actions["left"] + 0.5:
            raise AssertionError(f"actions overlap the canvas at {width}x{height}")


def check_desktop_unchanged(ws):
    phone(ws, DESKTOP, touch=False)
    assert_js(ws, "!document.documentElement.classList.contains('touch-ui')",
              "touch mode appeared on desktop")
    assert_js(ws, "getComputedStyle(document.getElementById('play-area')).display === 'contents'",
              "the desktop play area is not transparent")
    assert_js(ws, "getComputedStyle(document.getElementById('stage')).display === 'contents'",
              "the desktop stage box is not transparent")
    assert_js(ws, "getComputedStyle(document.getElementById('touch')).display === 'none'",
              "the touch controls are visible on desktop")


def check_lobby_scroll(ws):
    phone(ws, {"width": 390, "height": 600, "deviceScaleFactor": 2, "mobile": True})
    assert_js(ws, "document.getElementById('landing').scrollHeight > "
                  "document.getElementById('landing').clientHeight",
              "the lobby does not scroll on a short screen")
    js(ws, "document.getElementById('landing').scrollTop = 0; true")
    assert_js(ws, "document.querySelector('#landing .panel h1').getBoundingClientRect().top >= 0",
              "the top of the lobby is clipped")
    js(ws, "document.getElementById('host').scrollIntoView({block: 'center'}); true")
    time.sleep(0.2)
    assert_js(ws, "(() => { const r = document.getElementById('host').getBoundingClientRect();"
                  " return r.top >= 0 && r.bottom <= innerHeight + 1; })()",
              "the host button cannot be reached by scrolling")


def check_input(ws):
    ACTIVE_TOUCHES.clear()
    phone(ws, PHONE_PORTRAIT)
    start_solo_ready(ws)
    assert_js(ws, "typeof XBTouch === 'object' && XBTouch.enabled === true",
              "XBTouch is not enabled after the runtime starts")

    # one tap sends the action down and up
    tap(ws, "#pad [data-action=down]")
    assert_js(ws, "XBTouch.log.some(e => e.name === 'down' && e.down === true)",
              "a tap did not press down")
    assert_js(ws, "XBTouch.log.some(e => e.name === 'down' && e.down === false)",
              "a tap did not release down")

    # a thumb that leaves the pad and comes back keeps tracking
    pad = rects(ws, "#pad")["pad"]
    pointer_events(ws, [("#pad [data-action=left]", "pointerdown", 21)])
    assert_js(ws, "JSON.stringify(XBTouch.active()) === JSON.stringify(['left'])")
    pointer_at(ws, "pointermove", 21, pad["left"] - 30, pad["top"] - 30)
    assert_js(ws, "XBTouch.active().length === 0", "off-pad move did not stop the direction")
    up = center_of(ws, "#pad [data-action=up]")
    pointer_at(ws, "pointermove", 21, up["x"], up["y"])
    assert_js(ws, "JSON.stringify(XBTouch.active()) === JSON.stringify(['up'])",
              "returning to the pad did not resume tracking")
    pointer_at(ws, "pointerup", 21, up["x"], up["y"])
    assert_js(ws, "XBTouch.active().length === 0")

    # two fingers: direction + bomb stay held, releasing one keeps the other
    pointer_events(ws, [
        ("#pad [data-action=left]", "pointerdown", 11),
        ("#actions [data-action=bomb]", "pointerdown", 12),
    ])
    assert_js(ws, "JSON.stringify(XBTouch.active()) === JSON.stringify(['bomb','left'])",
              "two-finger press did not hold both actions")
    pointer_events(ws, [("#pad [data-action=left]", "pointerup", 11)])
    assert_js(ws, "JSON.stringify(XBTouch.active()) === JSON.stringify(['bomb'])",
              "releasing the direction released the bomb")
    pointer_events(ws, [("#actions [data-action=bomb]", "pointerup", 12)])
    assert_js(ws, "XBTouch.active().length === 0", "two-finger release left an action held")

    # sliding from left to up switches without sticking
    slide(ws, "#pad [data-action=left]", "#pad [data-action=up]")
    time.sleep(0.1)
    assert_js(ws, "JSON.stringify(XBTouch.active()) === JSON.stringify(['up'])",
              "sliding did not switch the pad direction")
    touch_release(ws, 0)
    time.sleep(0.1)
    assert_js(ws, "XBTouch.active().length === 0", "the slide left an action held")

    # blur releases everything
    touch_start(ws, "#pad [data-action=right]", 3)
    time.sleep(0.1)
    assert_js(ws, "XBTouch.active().length === 1", "touch press did not register")
    assert_js(ws, "window.dispatchEvent(new Event('blur')); true")
    time.sleep(0.1)
    assert_js(ws, "XBTouch.active().length === 0", "blur left an action held")
    touch_release(ws, 3)

    # a button is usable again after a blur that delivered no pointerup
    pointer_events(ws, [("#actions [data-action=bomb]", "pointerdown", 51)])
    assert_js(ws, "JSON.stringify(XBTouch.active()) === JSON.stringify(['bomb'])")
    assert_js(ws, "window.dispatchEvent(new Event('blur')); true")
    pointer_events(ws, [("#actions [data-action=bomb]", "pointerdown", 52)])
    assert_js(ws, "JSON.stringify(XBTouch.active()) === JSON.stringify(['bomb'])",
              "button stayed dead after a blur without pointerup")
    pointer_events(ws, [("#actions [data-action=bomb]", "pointerup", 52)])

    # before the runtime is ready the layer is inert
    phone(ws, PHONE_PORTRAIT)                      # reload; engine not started
    assert_js(ws, "typeof XBTouch === 'undefined' || XBTouch.enabled !== true",
              "touch input is live before the runtime is ready")
    assert_js(ws, "getComputedStyle(document.getElementById('touch')).display === 'none'",
              "touch controls are visible before the runtime is ready")

    # after the runtime handler runs, presses are inert
    start_solo_ready(ws)
    assert_js(ws, "(() => { const n = XBTouch.log.length; Module.onExit(0);"
                  " XBTouch.press('down'); return XBTouch.enabled === false &&"
                  " XBTouch.log.length === n; })()",
              "a press reached the bridge after exit")

    # engine integration on desktop: XBTouch could not press through to the
    # engine if the menu's Quit abort did not run; the overlay proves it did.
    phone(ws, DESKTOP, touch=False)
    start_solo_ready(ws)
    dismiss_intro(ws)
    assert_js(ws, "!document.getElementById('overlay').classList.contains('show')",
              "overlay is already visible before pressing back")
    js(ws, "XBTouch.press('back'); XBTouch.release('back'); true")
    wait_js(ws, "document.getElementById('overlay').classList.contains('show')", 15)


def check_touch_menus(ws):
    """Reach the engine's setup menu by tapping, then assign a player.

    A full touch-started match is a manual check: the setup menu needs two
    players and its modal combo close is ambiguous through the key bridge.
    """
    ACTIVE_TOUCHES.clear()
    phone(ws, PHONE_PORTRAIT)
    start_solo_ready(ws)
    assert_js(ws, "typeof Module._XBWeb_IsMenu === 'function'",
              "the menu-mode probe is not exported")
    assert_js(ws, "typeof Module._XBWeb_LocalPlayerCount === 'function'",
              "the local-player probe is not exported")
    time.sleep(11)                    # the intro's input wait times out
    assert_js(ws, "Module._XBWeb_IsMenu() === 1")
    canvas_tap(ws, 240, 84)           # Solo (main menu)
    time.sleep(1.5)
    assert_js(ws, "Module._XBWeb_IsMenu() === 1")
    assert_js(ws, "Module._XBWeb_LocalPlayerCount() === 0")
    canvas_tap(ws, 192, 84)           # Right Keyboard value
    time.sleep(0.5)
    js(ws, "XBTouch.press('stop'); XBTouch.release('stop'); true")
    time.sleep(0.5)
    assert_js(ws, "Module._XBWeb_LocalPlayerCount() === 1",
              "the tap plus STOP did not assign a keyboard player")
    js(ws, "XBTouch.press('kick'); XBTouch.release('kick'); true")   # Select
    assert_js(ws, "XBTouch.log.slice(-2).some(e => e.name === 'kick' && e.key === 'select')",
              "KICK did not send the menu select key")


def main():
    if os.environ.get("XB_TEST_NO_BUILD") != "1":
        print("== building web bundle ==", flush=True)
        subprocess.run([os.path.join(SCRIPTS, "build-web.sh")], cwd=ROOT, check=True)

    server, base = start_server()
    port = 9334
    profile = tempfile.mkdtemp(prefix="xb-touch-profile-")
    proc = subprocess.Popen(
        [cdp.CHROME, "--headless=new", "--disable-gpu", "--no-sandbox",
         f"--remote-debugging-port={port}", f"--user-data-dir={profile}",
         "--window-size=1000,800", "about:blank"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        cdp.wait_json(f"http://127.0.0.1:{port}/json/version")
        url = f"{base}/index.html"
        req = urllib.request.Request(
            f"http://127.0.0.1:{port}/json/new?{urllib.parse.quote(url, safe='')}",
            method="PUT")
        with urllib.request.urlopen(req, timeout=10) as r:
            target = json.loads(r.read())
        ws = cdp.WS(target["webSocketDebuggerUrl"])
        ws.call(1, "Page.enable")
        ws.call(2, "Runtime.enable")
        wait_js(ws, "document.readyState === 'complete' && !!document.getElementById('play')", 30)

        checks = [
            ("bridge", check_bridge),
            ("portrait", check_layout_portrait),
            ("landscape", check_layout_landscape),
            ("desktop", check_desktop_unchanged),
            ("lobby", check_lobby_scroll),
            ("input", check_input),
            ("menus", check_touch_menus),
        ]
        only = os.environ.get("XB_TOUCH_ONLY", "")
        for name, check in checks:
            if not only or only == name:
                check(ws)
        print("PASS: touch controls", flush=True)
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
        shutil.rmtree(profile, ignore_errors=True)
        server.shutdown()


if __name__ == "__main__":
    try:
        main()
    except AssertionError as error:
        print(f"FAIL: {error}", file=sys.stderr, flush=True)
        sys.exit(1)
