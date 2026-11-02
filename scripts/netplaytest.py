#!/usr/bin/env python3
"""Multi-browser acceptance test for the room-code host/join lobby.

Builds the web bundle, serves it locally, drives a host and up to five guest
pages through headless Chromes, and proves that the host starts listening in
the page-owned room, the guests connect before the host leaves its setup
menu, and every page exchanges reliable control and unreliable action traffic
on the playfield.

Usage: python3 scripts/netplaytest.py [--scenario match|guests|six|refresh|midmatch] [outdir]

`guests` (host + two guests) is the default; `six` needs six pages and is slow.

Set XB_TEST_OFFLINE=1 to skip (the test needs public Nostr relays).
"""
import base64
import functools
import json
import os
import random
import re
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

    def reload(self):
        self.ws.call(self.id(), "Page.reload", {"ignoreCache": False})

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


def start_lobby_page(page, button, room=None):
    """Set the room code and click Host or Join."""
    room = room or ROOM
    return page.ev(f"""(async () => {{
        const room = document.getElementById('room');
        const button = document.getElementById('{button}');
        if (!room || !button) return false;
        room.value = {json.dumps(room)};
        button.click();
        return true;
    }})()""")


def click_rejoin(page):
    """Click the lobby's post-refresh Rejoin button."""
    return page.ev("""(() => {
        const button = document.getElementById('rejoin');
        if (!button) return false;
        button.click();
        return true;
    })()""")


def wait_engine(page):
    page.wait_js(
        "!!(window.__xbReady || (window.Module && Module.calledRun))",
        90, f"{page.label} engine runtime")


def dismiss_intro(page):
    # The intro animates for ~1.75 s, then waits up to 10 s for a key. With
    # several engines running, a dismissal key can land during the animation
    # and only skip it, leaving the intro's own wait to eat the input meant for
    # the menu. A click on an empty menu area ends that wait and does nothing
    # in a menu, so it is safe before, during and after the intro.
    time.sleep(2.5)
    for _ in range(4):
        page.click(480, 650)
        time.sleep(1.2)


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


def run_guests(base, outdir):
    """Three browsers: a host plus two guests reach a match together."""
    room = f"m2-guests-{random.randrange(16 ** 6):06x}"
    host = Page(f"{base}/", "host")
    g1 = Page(f"{base}/", "guest1")
    g2 = Page(f"{base}/", "guest2")
    pages = [host, g1, g2]
    try:
        for page in pages:
            page.wait_js(
                "document.readyState === 'complete' && !!document.getElementById('room')"
                " && !!document.getElementById('host') && !!document.getElementById('join')",
                15, f"{page.label} lobby")

        print(f"== guests room {room} ==", flush=True)
        if not start_lobby_page(host, "host", room):
            raise AssertionError("could not click #host")
        for guest in (g1, g2):
            if not start_lobby_page(guest, "join", room):
                raise AssertionError(f"could not click #join for {guest.label}")
        for page in pages:
            wait_engine(page)
        for page in pages:
            dismiss_intro(page)

        # Both guests connect while the host is still in Start Network Game.
        for guest in (g1, g2):
            choose_first_player(guest)
            guest.key("return")       # Connect
            guest.wait_js(
                "globalThis.__xbnet && __xbnet.connectState(1000) === 1",
                60, f"{guest.label} connected before host Continue")
            print(f"{guest.label} connected while the host was in setup", flush=True)

        choose_first_player(host)
        host_ctl_before = host.ev("globalThis.__xbnet ? __xbnet.stats().ctlRx : 0") or 0
        host.key("return")            # Continue -> listen
        host.wait_js("globalThis.__xbnet && __xbnet.stats().peers === 2",
                     60, "host has two guests")
        host.wait_js(
            f"globalThis.__xbnet && __xbnet.stats().ctlRx >= {host_ctl_before + 100}",
            30, "host received both guests' configs")
        time.sleep(2.0)
        shot(host, os.path.join(outdir, "guests-host-wait.png"))

        act_before = {
            page.label: page.ev("globalThis.__xbnet ? __xbnet.stats().actTx : 0") or 0
            for page in pages
        }
        print(f"actTx before Start: {json.dumps(act_before, sort_keys=True)}", flush=True)

        host.key("return")            # Start
        time.sleep(3.0)
        for page in pages:
            page.key("space")         # dismiss level intro
        time.sleep(2.5)
        for name in ("left", "right", "space"):
            for page in pages:
                page.key(name)
            time.sleep(0.4)
        time.sleep(2.5)

        for page in pages:
            shot(page, os.path.join(outdir, f"guests-{page.label}.png"))
        snapshots = {page.label: page.snapshot() for page in pages}
        for page in pages:
            dump_page(page)

        failures = []
        for label, snap in snapshots.items():
            stats = snap.get("stats") or {}
            want = 2 if label == "host" else 1
            if stats.get("peers") != want:
                failures.append(f"{label}: peers={stats.get('peers')} (expected {want})")
            for counter in ("ctlTx", "ctlRx", "actTx", "actRx"):
                if not stats.get(counter, 0) > 0:
                    failures.append(f"{label}: {counter}={stats.get(counter)}")
            delta = stats.get("actTx", 0) - act_before[label]
            if delta < 100:
                failures.append(f"{label}: actTx delta after Start={delta} (expected >=100)")
            if "show" in (snap.get("overlay") or "").split():
                failures.append(f"{label}: overlay is showing")
        if failures:
            raise AssertionError("; ".join(failures))
        print(f"guests: PASS (room {room})", flush=True)
        return 0
    except Exception:
        for page in pages:
            dump_page(page, "FAIL ")
        traceback.print_exc()
        for page in pages:
            try:
                shot(page, os.path.join(outdir, f"guests-failure-{page.label}.png"))
            except Exception:
                pass
        return 1
    finally:
        for page in pages:
            page.close()


def run_six(base, outdir):
    """Six browsers: host + five guests reach a match; a seventh is refused."""
    room = f"m2-six-{random.randrange(16 ** 6):06x}"
    host = Page(f"{base}/", "host")
    guests = [Page(f"{base}/", f"guest{i + 1}") for i in range(5)]
    pages = [host] + guests
    light = None
    try:
        for page in pages:
            page.wait_js(
                "document.readyState === 'complete' && !!document.getElementById('room')"
                " && !!document.getElementById('host') && !!document.getElementById('join')",
                20, f"{page.label} lobby")

        print(f"== six room {room} ==", flush=True)
        if not start_lobby_page(host, "host", room):
            raise AssertionError("could not click #host")
        for guest in guests:
            if not start_lobby_page(guest, "join", room):
                raise AssertionError(f"could not click #join for {guest.label}")
        for page in pages:
            wait_engine(page)
        for page in pages:
            dismiss_intro(page)

        for guest in guests:
            choose_first_player(guest)
            guest.key("return")       # Connect
            guest.wait_js(
                "globalThis.__xbnet && __xbnet.connectState(1000) === 1",
                90, f"{guest.label} connected before host Continue")
            print(f"{guest.label} connected while the host was in setup", flush=True)

        choose_first_player(host)
        host_ctl_before = host.ev("globalThis.__xbnet ? __xbnet.stats().ctlRx : 0") or 0
        host.key("return")            # Continue -> listen
        host.wait_js("globalThis.__xbnet && __xbnet.stats().peers === 5",
                     90, "host has five guests")
        host.wait_js(
            f"globalThis.__xbnet && __xbnet.stats().ctlRx >= {host_ctl_before + 200}",
            60, "host received every guest's config")
        host.wait_js(
            "document.getElementById('net-state').textContent.indexOf('full') >= 0",
            20, "host lobby says the room is full")
        shot(host, os.path.join(outdir, "six-host-full.png"))

        # A seventh guest joins only the WebRTC room: the lightweight transport
        # page needs no engine to prove the refusal.
        light = Page(f"{base}/test/net.html?role=client&room={room}&scenario=full", "light")
        light.wait_js("globalThis.XBNet && __test.ready === true", 30, "light guest ready")
        light.ev("__test.configure({connectTimeoutMs: 90000})")
        light.ev("__test.open(301, 'stream')")
        light.ev("__test.connect(301)")
        light.wait_js(
            "(() => { const st = __test.connectState(301); const s = XBNet.status(); "
            "return st === -1 && s.connectError === 'The room is full (6 players).'; })()",
            60, "seventh guest refused")
        if light.ev("XBNet.stats().peers") != 0:
            raise AssertionError("refused guest still counts a connected peer")
        if host.ev("globalThis.__xbnet.stats().peers") != 5:
            raise AssertionError("host counted the refused guest as a peer")
        print("seventh guest refused with the room-full message", flush=True)

        time.sleep(3.0)
        act_before = {
            page.label: page.ev("globalThis.__xbnet ? __xbnet.stats().actTx : 0") or 0
            for page in pages
        }
        print(f"actTx before Start: {json.dumps(act_before, sort_keys=True)}", flush=True)

        host.key("return")            # Start
        time.sleep(3.0)
        for page in pages:
            page.key("space")         # dismiss level intro
        time.sleep(3.0)
        for name in ("left", "right", "space"):
            for page in pages:
                page.key(name)
            time.sleep(0.3)
        time.sleep(3.0)

        for page in pages:
            shot(page, os.path.join(outdir, f"six-{page.label}.png"))
        snapshots = {page.label: page.snapshot() for page in pages}
        for page in pages:
            dump_page(page)

        failures = []
        for label, snap in snapshots.items():
            stats = snap.get("stats") or {}
            want = 5 if label == "host" else 1
            if stats.get("peers") != want:
                failures.append(f"{label}: peers={stats.get('peers')} (expected {want})")
            for counter in ("ctlTx", "ctlRx", "actTx", "actRx"):
                if not stats.get(counter, 0) > 0:
                    failures.append(f"{label}: {counter}={stats.get(counter)}")
            delta = stats.get("actTx", 0) - act_before[label]
            if delta < 100:
                failures.append(f"{label}: actTx delta after Start={delta} (expected >=100)")
            if "show" in (snap.get("overlay") or "").split():
                failures.append(f"{label}: overlay is showing")
        if failures:
            raise AssertionError("; ".join(failures))
        print(f"six: PASS (room {room})", flush=True)
        return 0
    except Exception:
        for page in pages + ([light] if light else []):
            dump_page(page, "FAIL ")
        traceback.print_exc()
        for page in pages + ([light] if light else []):
            try:
                shot(page, os.path.join(outdir, f"six-failure-{page.label}.png"))
            except Exception:
                pass
        return 1
    finally:
        for page in pages + ([light] if light else []):
            page.close()


def run_refresh(base, outdir):
    """Guest refreshes in the wait screen, rejoins, and the host replaces it."""
    room = f"m2-refresh-{random.randrange(16 ** 6):06x}"
    host = Page(f"{base}/", "host")
    guest = Page(f"{base}/", "guest")
    pages = [host, guest]
    try:
        for page in pages:
            page.wait_js(
                "document.readyState === 'complete' && !!document.getElementById('room')"
                " && !!document.getElementById('host') && !!document.getElementById('join')",
                15, f"{page.label} lobby")

        print(f"== refresh room {room} ==", flush=True)
        if not start_lobby_page(host, "host", room):
            raise AssertionError("could not click #host")
        if not start_lobby_page(guest, "join", room):
            raise AssertionError("could not click #join")
        for page in pages:
            wait_engine(page)
        dismiss_intro(host)
        dismiss_intro(guest)

        # Guest connects while the host is still in setup; host then continues.
        choose_first_player(guest)
        guest.key("return")
        guest.wait_js(
            "globalThis.__xbnet && __xbnet.connectState(1000) === 1",
            40, "guest connected before host Continue")
        choose_first_player(host)
        host_ctl_before = host.ev("globalThis.__xbnet ? __xbnet.stats().ctlRx : 0") or 0
        host.key("return")
        for page in pages:
            page.wait_js("globalThis.__xbnet && __xbnet.stats().peers >= 1",
                         40, f"{page.label} peer")
        host.wait_js(
            f"globalThis.__xbnet && __xbnet.stats().ctlRx >= {host_ctl_before + 50}",
            20, "host received guest config")
        time.sleep(1.0)
        old_guest = guest.ev("globalThis.__xbnet.status().selfId")
        if not old_guest:
            raise AssertionError("guest selfId missing before refresh")

        print("guest reloads; the lobby offers Rejoin", flush=True)
        guest.reload()
        guest.wait_js(
            "document.readyState === 'complete' && !!document.getElementById('rejoin')",
            20, "guest rejoin banner")
        prefilled = guest.ev("document.getElementById('room').value")
        if prefilled != room:
            raise AssertionError(f"rejoin room prefilled as {prefilled!r}, expected {room!r}")
        if not click_rejoin(guest):
            raise AssertionError("could not click #rejoin")
        wait_engine(guest)
        dismiss_intro(guest)
        choose_first_player(guest)
        guest.key("return")
        guest.wait_js(
            "globalThis.__xbnet && __xbnet.connectState(1000) === 1",
            40, "guest reconnected after refresh")
        new_guest = guest.ev("globalThis.__xbnet.status().selfId")
        if new_guest == old_guest:
            raise AssertionError("refreshed guest reused the old selfId")

        print("host replaces the old client with the refreshed one", flush=True)
        host.wait_js("globalThis.__xbnet && __xbnet.stats().peers === 1",
                     30, "host has one peer after refresh")
        host.wait_js(
            "(() => { try { const ids = __xbnet.peerIds(); return ids.length === 1 && ids[0] === "
            f"{json.dumps(new_guest)}; }} catch (e) {{ return false; }} }})()",
            30, "host replaced the old guest")
        host.wait_js(
            f"globalThis.__xbnet && __xbnet.stats().ctlRx >= {host_ctl_before + 100}",
            20, "host received refreshed guest config")
        time.sleep(2.0)

        print("starting the match after the refresh", flush=True)
        act_before = {
            page.label: page.ev("globalThis.__xbnet ? __xbnet.stats().actTx : 0") or 0
            for page in pages
        }
        host.key("return")
        time.sleep(3.0)
        host.key("space")
        guest.key("space")
        time.sleep(2.0)
        for name in ("left", "right", "space"):
            host.key(name)
            guest.key(name)
            time.sleep(0.4)
        time.sleep(2.0)

        shot(host, os.path.join(outdir, "refresh-host.png"))
        shot(guest, os.path.join(outdir, "refresh-guest.png"))
        snapshots = {page.label: page.snapshot() for page in pages}
        for page in pages:
            dump_page(page)
        failures = []
        for label, snap in snapshots.items():
            stats = snap.get("stats") or {}
            if stats.get("peers", 0) != 1:
                failures.append(f"{label}: peers={stats.get('peers')} (expected 1)")
            for counter in ("ctlTx", "ctlRx", "actTx", "actRx"):
                if not stats.get(counter, 0) > 0:
                    failures.append(f"{label}: {counter}={stats.get(counter)}")
            delta = stats.get("actTx", 0) - act_before.get(label, 0)
            if delta < 100:
                failures.append(f"{label}: actTx delta after Start={delta} (expected >=100)")
        if failures:
            raise AssertionError("; ".join(failures))
        print(f"refresh: PASS (old self={old_guest}, new self={new_guest})", flush=True)
        return 0
    except Exception:
        for page in pages:
            dump_page(page, "FAIL ")
        traceback.print_exc()
        try:
            shot(host, os.path.join(outdir, "refresh-failure-host.png"))
            shot(guest, os.path.join(outdir, "refresh-failure-guest.png"))
        except Exception:
            pass
        return 1
    finally:
        for page in pages:
            page.close()


def run_midmatch(base, outdir):
    """A guest who refreshes after the match starts must fail clearly, not hang."""
    room = f"m2-midmatch-{random.randrange(16 ** 6):06x}"
    host = Page(f"{base}/", "host")
    guest = Page(f"{base}/", "guest")
    pages = [host, guest]
    try:
        for page in pages:
            page.wait_js(
                "document.readyState === 'complete' && !!document.getElementById('room')"
                " && !!document.getElementById('host') && !!document.getElementById('join')",
                15, f"{page.label} lobby")
        print(f"== midmatch room {room} ==", flush=True)
        if not start_lobby_page(host, "host", room):
            raise AssertionError("could not click #host")
        if not start_lobby_page(guest, "join", room):
            raise AssertionError("could not click #join")
        for page in pages:
            wait_engine(page)
        dismiss_intro(host)
        dismiss_intro(guest)

        choose_first_player(guest)
        guest.key("return")
        guest.wait_js(
            "globalThis.__xbnet && __xbnet.connectState(1000) === 1",
            40, "guest connected before host Continue")
        choose_first_player(host)
        host_ctl_before = host.ev("globalThis.__xbnet ? __xbnet.stats().ctlRx : 0") or 0
        host.key("return")
        for page in pages:
            page.wait_js("globalThis.__xbnet && __xbnet.stats().peers >= 1",
                         40, f"{page.label} peer")
        host.wait_js(
            f"globalThis.__xbnet && __xbnet.stats().ctlRx >= {host_ctl_before + 50}",
            20, "host received guest config")
        time.sleep(1.5)
        host.key("return")         # Start
        time.sleep(3.0)
        host.key("space")
        guest.key("space")
        time.sleep(2.0)
        print("match running; guest reloads and tries to rejoin", flush=True)

        guest.reload()
        guest.wait_js(
            "document.readyState === 'complete' && !!document.getElementById('rejoin')",
            20, "guest rejoin banner")
        if not click_rejoin(guest):
            raise AssertionError("could not click #rejoin")
        wait_engine(guest)
        dismiss_intro(guest)
        choose_first_player(guest)
        guest.key("return")
        guest.wait_js(
            "(() => { try { const s = __xbnet.status();"
            " return /already in a match|not accepting players/i.test("
            "s.connectError || s.lastError || ''); } catch (e) { return false; } })()",
            20, "guest gets a clear mid-match refusal")
        if guest.ev("__xbnet.connectState(1000)") != -1:
            raise AssertionError("mid-match connect did not fail")
        reason = guest.ev("__xbnet.status().connectError || __xbnet.status().lastError || ''")
        shot(guest, os.path.join(outdir, "midmatch-guest-error.png"))
        print(f"midmatch: PASS ({reason})", flush=True)
        return 0
    except Exception:
        for page in pages:
            dump_page(page, "FAIL ")
        traceback.print_exc()
        try:
            shot(host, os.path.join(outdir, "midmatch-failure-host.png"))
            shot(guest, os.path.join(outdir, "midmatch-failure-guest.png"))
        except Exception:
            pass
        return 1
    finally:
        for page in pages:
            page.close()


def run_takeover(base, outdir):
    """Host leaves pre-match; a guest takes over and the other auto-rejoins."""
    room = f"m2-takeover-{random.randrange(16 ** 6):06x}"
    host = Page(f"{base}/", "host")
    a = Page(f"{base}/", "guest-a")
    b = Page(f"{base}/", "guest-b")
    pages = [host, a, b]
    try:
        for page in pages:
            page.wait_js(
                "document.readyState === 'complete' && !!document.getElementById('room')"
                " && !!document.getElementById('host') && !!document.getElementById('join')",
                20, f"{page.label} lobby")
        print(f"== takeover room {room} ==", flush=True)
        if not start_lobby_page(host, "host", room):
            raise AssertionError("could not click #host")
        for guest in (a, b):
            if not start_lobby_page(guest, "join", room):
                raise AssertionError(f"could not click #join for {guest.label}")
        for page in pages:
            wait_engine(page)
            dismiss_intro(page)

        for guest in (a, b):
            choose_first_player(guest)
            guest.key("return")
            guest.wait_js(
                "globalThis.__xbnet && __xbnet.connectState(1000) === 1",
                60, f"{guest.label} connected in the host setup")
            guest.ev("""XBNet.__setTakeoverTimings(
                {claimWindowMs: 1000, claimSettleMs: 500, hostReadyTimeoutMs: 90000})""")
        print("both guests connected", flush=True)

        # The guest warning is driven by the host's visibility status.
        host.ev("XBNet.__setHostVisible(false)")
        b.wait_js(
            "document.getElementById('net-state').textContent.indexOf('background') >= 0",
            10, "guest saw the background warning")
        host.ev("XBNet.__setHostVisible(true)")
        b.wait_js(
            "document.getElementById('net-state').textContent.indexOf('background') < 0",
            10, "guest cleared the background warning")

        print("killing the host", flush=True)
        host.close()
        host = None
        for guest in (a, b):
            guest.wait_js(
                "document.getElementById('host-gone').classList.contains('show')",
                20, f"{guest.label} takeover overlay")
            text = guest.ev(
                "document.getElementById('host-gone').textContent.toLowerCase()")
            if "host left" not in text:
                raise AssertionError(f"{guest.label} overlay does not say host left: {text!r}")
            if guest.ev("getComputedStyle(document.getElementById('takeover')).display") == "none":
                raise AssertionError(f"{guest.label} has no Take over button")

        print("guest A takes over", flush=True)
        a.ev("document.getElementById('takeover').click(); true")
        a.wait_js("globalThis.__xbnet && __xbnet.status().role === 'host'",
                  90, "A reloaded as host")
        a.wait_js(f"__xbnet.status().room === {json.dumps(room)}", 30, "A kept the room")
        wait_engine(a)
        dismiss_intro(a)
        choose_first_player(a)
        a.key("return")          # Continue -> listen; B may now auto-rejoin

        wait_engine(b)
        dismiss_intro(b)
        b.wait_js("globalThis.__xbnet && __xbnet.connectState(1000) === 1",
                  60, "B auto-rejoined without a click")
        print("B auto-rejoined", flush=True)

        a.wait_js("globalThis.__xbnet && __xbnet.stats().peers === 1",
                  60, "new host sees B")
        time.sleep(1.5)
        act_before = {page.label: page.ev("__xbnet.stats().actTx") for page in (a, b)}
        a.key("return")          # Start
        time.sleep(3.0)
        for page in (a, b):
            page.key("space")    # dismiss level intro
        time.sleep(2.0)
        for name in ("left", "right", "space"):
            for page in (a, b):
                page.key(name)
            time.sleep(0.4)
        time.sleep(2.0)

        for page in (a, b):
            stats = page.ev("__xbnet.stats()")
            if stats.get("actTx", 0) - act_before[page.label] < 100:
                raise AssertionError(
                    f"{page.label}: no match action traffic after takeover")
            if page.ev("__xbnet.stats().peers") != 1:
                raise AssertionError(f"{page.label}: peer count changed after takeover")
        print("takeover: PASS (new host, auto-rejoined guest, match traffic)", flush=True)
        return 0
    except Exception:
        for page in [p for p in (host, a, b) if p is not None]:
            dump_page(page, "FAIL ")
        traceback.print_exc()
        return 1
    finally:
        for page in [p for p in (host, a, b) if p is not None]:
            page.close()


def run_hostback(base, outdir):
    """The host refreshes and re-hosts; the guest auto-rejoins."""
    room = f"m2-hostback-{random.randrange(16 ** 6):06x}"
    host = Page(f"{base}/", "host")
    guest = Page(f"{base}/", "guest")
    try:
        for page in (host, guest):
            page.wait_js(
                "document.readyState === 'complete' && !!document.getElementById('room')"
                " && !!document.getElementById('host') && !!document.getElementById('join')",
                20, f"{page.label} lobby")
        print(f"== hostback room {room} ==", flush=True)
        if not start_lobby_page(host, "host", room):
            raise AssertionError("could not click #host")
        if not start_lobby_page(guest, "join", room):
            raise AssertionError("could not click #join for guest")
        for page in (host, guest):
            wait_engine(page)
            dismiss_intro(page)

        choose_first_player(guest)
        guest.key("return")
        guest.wait_js(
            "globalThis.__xbnet && __xbnet.connectState(1000) === 1",
            60, "guest connected in the host setup")
        guest.ev("XBNet.__setTakeoverTimings({hostReadyTimeoutMs: 90000})")

        print("host reloads and re-hosts", flush=True)
        host.reload()
        host.wait_js(
            "document.readyState === 'complete' && "
            "document.getElementById('rejoin-banner').classList.contains('show')",
            30, "host rejoin banner")
        host.ev("document.getElementById('rejoin').click(); true")
        wait_engine(host)
        dismiss_intro(host)
        choose_first_player(host)
        host.key("return")       # Continue -> listen

        guest.wait_js(
            "performance.getEntriesByType('navigation')[0].type === 'reload'",
            30, "guest auto-reloaded")
        wait_engine(guest)
        dismiss_intro(guest)
        guest.wait_js("globalThis.__xbnet && __xbnet.connectState(1000) === 1",
                      60, "guest auto-rejoined")
        host.wait_js("globalThis.__xbnet && __xbnet.stats().peers === 1",
                     60, "host sees the guest")
        time.sleep(1.5)

        act_before = {page.label: page.ev("__xbnet.stats().actTx") for page in (host, guest)}
        host.key("return")       # Start
        time.sleep(3.0)
        for page in (host, guest):
            page.key("space")
        time.sleep(2.0)
        for name in ("left", "right", "space"):
            for page in (host, guest):
                page.key(name)
            time.sleep(0.4)
        time.sleep(2.0)
        for page in (host, guest):
            stats = page.ev("__xbnet.stats()")
            if stats.get("actTx", 0) - act_before[page.label] < 100:
                raise AssertionError(f"{page.label}: no match action traffic after rehost")
        print("hostback: PASS (guest auto-rejoined the re-hosted room)", flush=True)
        return 0
    except Exception:
        for page in (host, guest):
            dump_page(page, "FAIL ")
        traceback.print_exc()
        return 1
    finally:
        host.close(); guest.close()


def run_autojoin(base, outdir):
    """A guest with a flushed player config auto-connects from a takeover flag."""
    room = f"m2-autojoin-{random.randrange(16 ** 6):06x}"
    host = Page(f"{base}/", "host")
    guest = Page(f"{base}/", "guest")
    fresh = None
    pages = [host, guest]
    try:
        for page in pages:
            page.wait_js(
                "document.readyState === 'complete' && !!document.getElementById('room')"
                " && !!document.getElementById('host') && !!document.getElementById('join')",
                20, f"{page.label} lobby")
        print(f"== autojoin room {room} ==", flush=True)
        if not start_lobby_page(host, "host", room):
            raise AssertionError("could not click #host")
        if not start_lobby_page(guest, "join", room):
            raise AssertionError("could not click #join for guest")
        for page in pages:
            wait_engine(page)
            dismiss_intro(page)

        choose_first_player(guest)
        guest.key("return")
        guest.wait_js(
            "globalThis.__xbnet && __xbnet.connectState(1000) === 1",
            60, "guest connected before the refresh")
        print("guest connected; flushing config and reloading", flush=True)

        guest.ev("""(() => {
            Module._XBWeb_FlushConfig();
            saveConfig();
            sessionStorage.setItem('xb:takeover', JSON.stringify(
                {mode: 'client', room: %s, autoJoin: true}));
            location.reload();
            return true;
        })()""" % json.dumps(room))
        wait_engine(guest)
        guest.wait_js("globalThis.__xbnet && __xbnet.status().role === 'client'",
                      30, "guest reloaded into the room")
        guest.wait_js("globalThis.__xbnet && __xbnet.connectState(1000) === 1",
                      40, "guest auto-connected without a click")
        print("flushed guest auto-connected", flush=True)

        # A fresh page (no saved player config) must fall back to the join menu.
        fresh = Page(f"{base}/", "fresh")
        fresh.wait_js(
            "document.readyState === 'complete' && !!document.getElementById('room')",
            20, "fresh lobby")
        fresh.ev("""(() => {
            localStorage.removeItem('xblast:config:v2');
            sessionStorage.setItem('xb:takeover', JSON.stringify(
                {mode: 'client', room: %s, autoJoin: true}));
            location.reload();
            return true;
        })()""" % json.dumps(room))
        wait_engine(fresh)
        fresh.wait_js("globalThis.__xbnet && __xbnet.status().role === 'client'",
                      30, "fresh page joined the room")
        time.sleep(4.0)
        if fresh.ev("__xbnet.connectState(1000)") == 1:
            raise AssertionError("a guest with no player config auto-connected")
        print("autojoin: PASS (with config connected, without config stayed in menu)",
              flush=True)
        return 0
    except Exception:
        for page in pages + ([fresh] if fresh else []):
            dump_page(page, "FAIL ")
        traceback.print_exc()
        return 1
    finally:
        for page in pages + ([fresh] if fresh else []):
            page.close()


def main():
    if os.environ.get("XB_TEST_OFFLINE") == "1":
        print("SKIP: XB_TEST_OFFLINE=1; the netplay test needs internet access "
              "to public Nostr relays.", flush=True)
        return 0

    args = sys.argv[1:]
    scenario = "guests"
    if "--scenario" in args:
        index = args.index("--scenario")
        try:
            scenario = args[index + 1]
        except IndexError:
            print("--scenario needs a value", file=sys.stderr)
            return 2
        del args[index:index + 2]
    if scenario not in ("match", "guests", "six", "refresh", "midmatch", "autojoin",
                        "takeover", "hostback"):
        print(f"unknown scenario: {scenario}", file=sys.stderr)
        return 2
    outdir = args[0] if args else tempfile.gettempdir()
    os.makedirs(outdir, exist_ok=True)

    print("== building web bundle ==", flush=True)
    subprocess.run([os.path.join(SCRIPTS, "build-web.sh")], cwd=ROOT, check=True)
    # The six-browser run uses the lightweight transport page for its seventh
    # guest, so a refusal is checked without a seventh engine.
    test_dst = os.path.join(DIST, "test", "net.html")
    os.makedirs(os.path.dirname(test_dst), exist_ok=True)
    shutil.copyfile(os.path.join(ROOT, "web", "test", "net.html"), test_dst)

    server, base = start_server()
    try:
        if scenario == "refresh":
            return run_refresh(base, outdir)
        if scenario == "midmatch":
            return run_midmatch(base, outdir)
        if scenario == "autojoin":
            return run_autojoin(base, outdir)
        if scenario == "takeover":
            return run_takeover(base, outdir)
        if scenario == "hostback":
            return run_hostback(base, outdir)
        if scenario == "guests":
            return run_guests(base, outdir)
        if scenario == "six":
            return run_six(base, outdir)
        return run(base, outdir)
    finally:
        server.shutdown()
        server.server_close()


if __name__ == "__main__":
    sys.exit(main())
