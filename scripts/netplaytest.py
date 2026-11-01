#!/usr/bin/env python3
"""Two-browser acceptance test for the room-code host/join lobby.

Builds the web bundle, serves it locally, drives a host and a guest page
through two headless Chromes, and proves that the host starts listening in
the page-owned room, the guest connects before the host leaves its setup
menu, and both pages exchange reliable control and unreliable action traffic
on the playfield.

Usage: python3 scripts/netplaytest.py [outdir]

Set XB_TEST_OFFLINE=1 to skip (the test needs public Nostr relays).
"""
import base64
import functools
import json
import os
import random
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import traceback
import urllib.parse
import urllib.request
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

SCRIPTS = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(SCRIPTS, ".."))
DIST = os.path.join(ROOT, "web", "dist")
sys.path.insert(0, SCRIPTS)
from cdp_shot import CHROME, WS, wait_json, send_key, send_click  # noqa: E402

ROOM = os.environ.get("XB_TEST_ROOM", "m2-test-01")
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
        request_queue_size = 128

    handler = functools.partial(Handler, directory=DIST)
    try:
        server = Server(("127.0.0.1", SERVER_PORT), handler)
        port = SERVER_PORT
    except OSError:
        port = free_port()
        server = Server(("127.0.0.1", port), handler)
        print(f"port {SERVER_PORT} busy, serving on {port}", flush=True)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, f"http://127.0.0.1:{port}"


def shot(page, path):
    data = page.ws.call(page.id(), "Page.captureScreenshot", {"format": "png"})["data"]
    with open(path, "wb") as handle:
        handle.write(base64.b64decode(data))
    print("wrote", path, flush=True)


class Page:
    def __init__(self, url, label):
        self.label = label
        self.port = free_port()
        self.profile = tempfile.mkdtemp(prefix=f"xb-netplay-{label}-")
        self.proc = subprocess.Popen([
            CHROME, "--headless=new", "--disable-gpu", "--no-sandbox",
            "--disable-features=WebRtcHideLocalIpsWithMdns",
            "--no-first-run", "--no-default-browser-check",
            "--autoplay-policy=no-user-gesture-required",
            f"--remote-debugging-port={self.port}",
            f"--user-data-dir={self.profile}",
            "--window-size=1000,800", "about:blank",
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.ws = None
        self.next_id = 10
        try:
            wait_json(f"http://127.0.0.1:{self.port}/json/version", timeout=30)
            request = urllib.request.Request(
                f"http://127.0.0.1:{self.port}/json/new?{urllib.parse.quote(url, safe='')}",
                method="PUT")
            with urllib.request.urlopen(request, timeout=15) as response:
                target = json.loads(response.read())
            self.ws = WS(target["webSocketDebuggerUrl"])
            self.ws.call(self.id(), "Page.enable")
            self.ws.call(self.id(), "Runtime.enable")
            self.ws.call(self.id(), "Log.enable")
        except Exception:
            self.close()
            raise

    def id(self):
        self.next_id += 1
        return self.next_id

    def ev(self, expression):
        result = self.ws.call(self.id(), "Runtime.evaluate", {
            "expression": expression, "returnByValue": True,
            "awaitPromise": True,
        })
        if "exceptionDetails" in result:
            details = result["exceptionDetails"]
            description = (details.get("exception") or {}).get("description") or details.get("text")
            raise RuntimeError(f"JS error: {description}\n  expression: {expression}")
        return result.get("result", {}).get("value")

    def wait_js(self, expression, timeout, label):
        deadline = time.time() + timeout
        last_error = None
        while time.time() < deadline:
            try:
                value = self.ev(expression)
            except RuntimeError as error:
                last_error = str(error)
            else:
                if value:
                    return value
            time.sleep(0.1)
        extra = f" (last error: {last_error})" if last_error else ""
        raise TimeoutError(f"{label}: timed out after {timeout}s waiting for {expression}{extra}")

    def key(self, name):
        send_key(self.ws, name)

    def click(self, gx, gy):
        send_click(self.ws, gx, gy)

    def console_events(self):
        """Return (errors, warnings) collected from Runtime and Log."""
        errors = []
        warnings = []
        for event in getattr(self.ws, "events", []) if self.ws else []:
            if event.get("type") == "error":
                text = "".join(str(arg.get("value", arg.get("description", "")))
                               for arg in event.get("args", []) if isinstance(arg, dict))
                if text:
                    errors.append(text)
            elif event.get("type") in ("warning", "warn"):
                text = "".join(str(arg.get("value", arg.get("description", "")))
                               for arg in event.get("args", []) if isinstance(arg, dict))
                if text:
                    warnings.append(text)
            entry = event.get("entry")
            if isinstance(entry, dict):
                text = str(entry.get("text", ""))
                if entry.get("level") == "error":
                    errors.append(text)
                elif entry.get("level") == "warning":
                    warnings.append(text)
        return errors, warnings

    def snapshot(self):
        return self.ev("""(() => {
            const net = globalThis.__xbnet;
            return {
                stats: net ? net.stats() : null,
                status: net ? net.status() : null,
                peers: net ? net.peerIds() : [],
                connectState: net ? net.connectState(1000) : null,
                overlay: document.getElementById('overlay').className,
                landing: document.getElementById('landing').className,
                statusText: document.getElementById('status').textContent,
                netbar: document.getElementById('netbar') ? document.getElementById('netbar').className : null,
            };
        })()""")

    def close(self):
        if self.ws:
            try:
                self.ws.sock.close()
            except OSError:
                pass
            self.ws = None
        if self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait(timeout=5)
        shutil.rmtree(self.profile, ignore_errors=True)


def start_lobby_page(page, button):
    """Set the room code and click Host or Join."""
    return page.ev(f"""(async () => {{
        const room = document.getElementById('room');
        const button = document.getElementById('{button}');
        if (!room || !button) return false;
        room.value = {json.dumps(ROOM)};
        button.click();
        return true;
    }})()""")


def wait_engine(page):
    page.wait_js(
        "!!(window.__xbReady || (window.Module && Module.calledRun))",
        90, f"{page.label} engine runtime")


def dismiss_intro(page):
    # The intro animates for ~1.75 s, then waits up to 10 s for a key.
    time.sleep(3.0)
    page.key("space")
    time.sleep(2.0)


def choose_first_player(page):
    page.click(384, 168)       # first player combo (Right Keyboard)
    time.sleep(0.2)
    page.key("space")          # open combo
    time.sleep(0.2)
    page.key("down")           # choose the first player
    time.sleep(0.2)
    page.key("space")          # close combo
    time.sleep(0.6)


def dump_page(page, prefix=""):
    try:
        print(f"{prefix}{page.label}: {json.dumps(page.snapshot(), sort_keys=True)}",
              file=sys.stderr, flush=True)
    except Exception as error:
        print(f"{prefix}{page.label}: could not snapshot: {error}",
              file=sys.stderr, flush=True)
    errors, warnings = page.console_events()
    for line in warnings:
        print(f"{prefix}{page.label}: console warning: {line}", file=sys.stderr, flush=True)
    for line in errors:
        print(f"{prefix}{page.label}: console error: {line}", file=sys.stderr, flush=True)


def run(base, outdir):
    host = Page(f"{base}/", "host")
    guest = Page(f"{base}/", "guest")
    pages = [host, guest]
    try:
        for page in pages:
            page.wait_js(
                "document.readyState === 'complete' && !!document.getElementById('room')"
                " && !!document.getElementById('host') && !!document.getElementById('join')",
                15, f"{page.label} lobby")

        print(f"== room {ROOM} ==", flush=True)
        if not start_lobby_page(host, "host"):
            raise AssertionError("could not click #host")
        # Page B starts while page A is still in Start Network Game.
        if not start_lobby_page(guest, "join"):
            raise AssertionError("could not click #join")

        for page in pages:
            wait_engine(page)

        dismiss_intro(host)
        dismiss_intro(guest)
        shot(host, os.path.join(outdir, "netplay-host-setup.png"))
        shot(guest, os.path.join(outdir, "netplay-guest-join.png"))

        # Guest picks a player and connects while the host is still in setup.
        choose_first_player(guest)
        guest.key("return")        # Connect
        guest.wait_js(
            "globalThis.__xbnet && __xbnet.connectState(1000) === 1",
            40, "guest connected before host Continue")
        print("guest connected while host was still in Start Network Game", flush=True)
        shot(guest, os.path.join(outdir, "netplay-guest-wait.png"))

        # Host picks a player and continues to the wait screen.
        choose_first_player(host)
        host_ctl_before = host.ev("globalThis.__xbnet ? __xbnet.stats().ctlRx : 0") or 0
        host.key("return")         # Continue
        for page in pages:
            page.wait_js(
                "globalThis.__xbnet && __xbnet.stats().peers >= 1",
                40, f"{page.label} peer")
        host.wait_js(
            "globalThis.__xbnet && __xbnet.stats().ctlOpen",
            20, "host control channel open")
        guest.wait_js(
            "globalThis.__xbnet && __xbnet.stats().ctlOpen",
            20, "guest control channel open")
        # The server requests the guest's game/player config after accepting.
        # Starting before those arrive makes Network_CreateGlobalGameConfig
        # see only the host's player ("Need at least two teams/players"), so
        # this wait is a hard gate, not a warning.
        host.wait_js(
            f"globalThis.__xbnet && __xbnet.stats().ctlRx >= {host_ctl_before + 50}",
            20, "host received guest config")
        time.sleep(1.5)
        print("both peers connected; starting the match", flush=True)

        # Activity counters only prove the DataChannels are alive. Record
        # actTx immediately before Start, then require a substantial increase
        # after the movement phase: pings alone add only single digits.
        act_before = {
            page.label: page.ev("globalThis.__xbnet ? __xbnet.stats().actTx : 0") or 0
            for page in pages
        }
        print(f"actTx before Start: {json.dumps(act_before, sort_keys=True)}", flush=True)

        host.key("return")         # Start (default)
        time.sleep(3.0)
        host.key("space")          # dismiss level intro
        guest.key("space")
        time.sleep(2.0)

        for name in ("left", "right", "space"):
            host.key(name)
            guest.key(name)
            time.sleep(0.4)
        time.sleep(2.0)

        shot(host, os.path.join(outdir, "netplay-host.png"))
        shot(guest, os.path.join(outdir, "netplay-guest.png"))

        snapshots = {}
        for page in pages:
            snapshots[page.label] = page.snapshot()
            dump_page(page)

        failures = []
        for label, snap in snapshots.items():
            stats = snap.get("stats") or {}
            if stats.get("peers", 0) < 1:
                failures.append(f"{label}: peers={stats.get('peers')}")
            for counter in ("ctlTx", "ctlRx", "actTx", "actRx"):
                if not stats.get(counter, 0) > 0:
                    failures.append(f"{label}: {counter}={stats.get(counter)}")
            # A match that never left the wait menus still exchanges pings,
            # but not the per-frame action traffic a running game produces.
            act_delta = stats.get("actTx", 0) - act_before.get(label, 0)
            if act_delta < 100:
                failures.append(
                    f"{label}: actTx delta after Start={act_delta} (expected >=100)")
            if "show" in (snap.get("overlay") or "").split():
                failures.append(f"{label}: overlay is showing")
            if not snap.get("peers"):
                failures.append(f"{label}: no peer ids")
        if failures:
            raise AssertionError("; ".join(failures))

        print(f"room: {ROOM}")
        for label, snap in snapshots.items():
            status = snap.get("status") or {}
            stats = snap.get("stats") or {}
            act_delta = stats.get("actTx", 0) - act_before.get(label, 0)
            print(f"{label}: self={status.get('selfId')} peers={snap.get('peers')}")
            print(f"{label}: stats={json.dumps(stats, sort_keys=True)}")
            print(f"{label}: actTx delta after Start={act_delta}")
        print("netplay: PASS")
        return 0
    except Exception:
        for page in pages:
            dump_page(page, "FAIL ")
        traceback.print_exc()
        try:
            shot(pages[0], os.path.join(outdir, "netplay-failure-host.png"))
            shot(pages[1], os.path.join(outdir, "netplay-failure-guest.png"))
        except Exception:
            pass
        return 1
    finally:
        for page in pages:
            page.close()


def main():
    if os.environ.get("XB_TEST_OFFLINE") == "1":
        print("SKIP: XB_TEST_OFFLINE=1; the netplay test needs internet access "
              "to public Nostr relays.", flush=True)
        return 0

    outdir = sys.argv[1] if len(sys.argv) > 1 else tempfile.gettempdir()
    os.makedirs(outdir, exist_ok=True)

    print("== building web bundle ==", flush=True)
    subprocess.run([os.path.join(SCRIPTS, "build-web.sh")], cwd=ROOT, check=True)

    server, base = start_server()
    try:
        return run(base, outdir)
    finally:
        server.shutdown()
        server.server_close()


if __name__ == "__main__":
    sys.exit(main())
