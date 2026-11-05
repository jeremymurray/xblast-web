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
        result = ws.call(6, "Runtime.evaluate", {
            "expression": expression, "returnByValue": True,
        })
        if (result.get("result") or {}).get("value"):
            return
        time.sleep(0.2)
    raise AssertionError(f"timed out waiting for {expression}")


def js(ws, expression):
    result = ws.call(6, "Runtime.evaluate", {
        "expression": expression, "returnByValue": True,
    })
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

        check_bridge(ws)
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
