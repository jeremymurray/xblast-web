#!/usr/bin/env python3
"""Probe the vendored Trystero import map in headless Chrome.

Serves nothing itself: start a static server first, e.g.
    python3 -m http.server -d web/dist 8123
then run:
    python3 scripts/check_vendor.py http://localhost:8123/_vendor_probe.html
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from cdp_shot import CHROME, WS, wait_json

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
DIST = os.path.join(ROOT, "web", "dist")
PROBE = os.path.join(DIST, "_vendor_probe.html")
PORT = 9334

PAGE = """<!doctype html><meta charset="utf-8">
<script type="importmap">
{"imports":{
  "@trystero-p2p/nostr":"./vendor/trystero/nostr/index.mjs",
  "@trystero-p2p/core":"./vendor/trystero/core/index.mjs",
  "@noble/secp256k1":"./vendor/trystero/noble/index.js"
}}
</script>
<script type="module">
import {joinRoom, selfId} from '@trystero-p2p/nostr'
window.__vendor = {ok: typeof joinRoom === 'function' && typeof selfId === 'string', selfId}
</script>
"""


def main():
    url = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8123/_vendor_probe.html"
    profile = tempfile.mkdtemp(prefix="xb-vendor-profile-")
    proc = None
    try:
        os.makedirs(DIST, exist_ok=True)
        with open(PROBE, "w", encoding="utf-8") as f:
            f.write(PAGE)
        proc = subprocess.Popen(
            [
                CHROME, "--headless=new", "--disable-gpu", "--no-sandbox",
                f"--remote-debugging-port={PORT}", f"--user-data-dir={profile}",
                "--window-size=1000,800", "about:blank",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        wait_json(f"http://127.0.0.1:{PORT}/json/version")
        req = urllib.request.Request(
            f"http://127.0.0.1:{PORT}/json/new?{urllib.parse.quote(url, safe='')}",
            method="PUT",
        )
        with urllib.request.urlopen(req, timeout=10) as r:
            target = json.loads(r.read())
        ws = WS(target["webSocketDebuggerUrl"])
        ws.call(1, "Page.enable")
        ws.call(2, "Runtime.enable")
        ws.call(3, "Log.enable")

        info = None
        deadline = time.time() + 15
        while time.time() < deadline:
            result = ws.call(4, "Runtime.evaluate", {
                "expression": "window.__vendor ? JSON.stringify(window.__vendor) : null",
                "returnByValue": True,
            }).get("result", {})
            if result.get("value"):
                info = json.loads(result["value"])
                break
            time.sleep(0.5)

        if info is None:
            print("vendor probe timed out", file=sys.stderr)
            for ev in ws.events:
                if ev.get("args"):
                    text = "".join(str(a.get("value", a.get("description", ""))) for a in ev["args"])
                    print("console:", text, file=sys.stderr)
            return 1

        print(info)
        if not info.get("ok"):
            print("vendor probe failed", file=sys.stderr)
            return 1
        return 0
    finally:
        if proc is not None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
        shutil.rmtree(profile, ignore_errors=True)
        try:
            os.unlink(PROBE)
        except FileNotFoundError:
            pass


if __name__ == "__main__":
    sys.exit(main())
