#!/usr/bin/env python3
"""Scripted playtest: start a local game with a keyboard player and capture
screenshots before/after movement and a bomb.

Usage: python3 scripts/playtest.py [url] [outdir]
"""
import base64
import json
import shutil
import subprocess
import sys
import time
import urllib.parse
import urllib.request

import cdp_shot as cdp


def shot(ws, path):
    data = ws.call(100, "Page.captureScreenshot", {"format": "png"})["data"]
    with open(path, "wb") as f:
        f.write(base64.b64decode(data))
    print("wrote", path)


def wait_js(ws, expression, timeout=60):
    """Poll the page until `expression` is truthy; no fixed-load sleeps."""
    end = time.time() + timeout
    while time.time() < end:
        result = ws.call(6, "Runtime.evaluate", {
            "expression": expression, "returnByValue": True,
        })
        if (result.get("result") or {}).get("value"):
            return
        time.sleep(0.2)
    raise RuntimeError(f"timed out after {timeout}s waiting for {expression}")


def main():
    url = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8123/index.html"
    outdir = sys.argv[2] if len(sys.argv) > 2 else "/tmp"
    port = 9334
    profile = "/tmp/xb-playtest-profile"
    shutil.rmtree(profile, ignore_errors=True)

    proc = subprocess.Popen(
        [cdp.CHROME, "--headless=new", "--disable-gpu", "--no-sandbox",
         f"--remote-debugging-port={port}", f"--user-data-dir={profile}",
         "--window-size=1000,800", "about:blank"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        cdp.wait_json(f"http://127.0.0.1:{port}/json/version")
        req = urllib.request.Request(
            f"http://127.0.0.1:{port}/json/new?{urllib.parse.quote(url, safe='')}",
            method="PUT")
        with urllib.request.urlopen(req, timeout=10) as r:
            target = json.loads(r.read())
        ws = cdp.WS(target["webSocketDebuggerUrl"])
        ws.call(1, "Page.enable")
        ws.call(2, "Runtime.enable")
        wait_js(ws, "document.readyState === 'complete' && !!document.getElementById('play')",
                30)
        ws.call(5, "Runtime.evaluate", {
            "expression": "document.getElementById('play') && document.getElementById('play').click()",
        })
        wait_js(ws, "!!window.__xbReady", 90)   # engine runtime up
        time.sleep(1.0)
        # The intro animates, then waits up to 10 s for input. Clicking an empty
        # area ends that wait and does nothing in a menu, so the timing stops
        # mattering under load.
        for _ in range(3):
            cdp.send_click(ws, 480, 650)
            time.sleep(1.2)
        time.sleep(0.5)
        cdp.send_click(ws, 480, 168)       # Start Local Game
        time.sleep(2)
        cdp.send_click(ws, 384, 168)       # focus Right Keyboard combo
        cdp.send_key(ws, "space")          # open combo
        cdp.send_key(ws, "down")           # cycle to the next control
        cdp.send_key(ws, "space")          # close combo
        cdp.send_click(ws, 790, 454)       # focus Bot combo
        cdp.send_key(ws, "space")
        cdp.send_key(ws, "down")           # Bot: yes
        cdp.send_key(ws, "space")
        time.sleep(1)
        shot(ws, f"{outdir}/play-setup.png")
        cdp.send_key(ws, "return")         # Start (menu default)
        time.sleep(3)
        cdp.send_key(ws, "space")          # dismiss level intro
        time.sleep(2)
        shot(ws, f"{outdir}/play-before.png")

        for _ in range(3):
            cdp.send_key(ws, "right")
            time.sleep(0.4)
        cdp.send_key(ws, "space")          # bomb
        time.sleep(0.5)
        shot(ws, f"{outdir}/play-after.png")

        state = ws.call(101, "Runtime.evaluate", {
            "expression": "JSON.stringify({status: document.getElementById('status').textContent, overlay: document.getElementById('overlay').className})",
            "returnByValue": True,
        })
        print("page:", state["result"]["value"])
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
        shutil.rmtree(profile, ignore_errors=True)


if __name__ == "__main__":
    main()
