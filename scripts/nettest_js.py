#!/usr/bin/env python3
"""Headless test for web/net.js over real WebRTC + public Nostr signalling.

Runs `./scripts/build-web.sh`, copies `web/test/net.html` into `web/dist/test/`,
serves `web/dist`, and drives two or three headless Chrome pages with the CDP.

Scenarios:
  basic      two pages: stream connect/accept, both directions, half-close,
             datagrams, listen-close keeps accepted peers, peer-close keeps room
  multi      host + clients A/B: closing A's accepted stream leaves B working
  wrong-room a lone guest must fail its connect within the configured timeout

Requires internet: the pages use the public Nostr relays Trystero ships with.
"""
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
TEST_SRC = os.path.join(ROOT, "web", "test", "net.html")
TEST_DST = os.path.join(DIST, "test", "net.html")

sys.path.insert(0, SCRIPTS)
from cdp_shot import CHROME, WS, wait_json  # noqa: E402


def free_port():
    s = socket.socket()
    try:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]
    finally:
        s.close()


def unique_token():
    return "".join(random.choice("0123456789abcdef") for _ in range(8))


def unique_room(prefix="xbjs"):
    return f"{prefix}-{unique_token()}"


def check(cond, msg):
    if not cond:
        raise AssertionError(msg)


def build():
    print("== building web/dist ==", flush=True)
    subprocess.run([os.path.join(SCRIPTS, "build-web.sh")], cwd=ROOT, check=True)
    os.makedirs(os.path.dirname(TEST_DST), exist_ok=True)
    shutil.copyfile(TEST_SRC, TEST_DST)


def start_server():
    class Handler(SimpleHTTPRequestHandler):
        def log_message(self, fmt, *args):
            pass

    class Server(ThreadingHTTPServer):
        daemon_threads = True
        allow_reuse_address = True
        request_queue_size = 128

    port = free_port()
    server = Server(("127.0.0.1", port), functools.partial(Handler, directory=DIST))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, f"http://127.0.0.1:{port}"


class Page:
    def __init__(self, url):
        self.port = free_port()
        self.profile = tempfile.mkdtemp(prefix="xb-nettest-profile-")
        self.proc = subprocess.Popen(
            [
                CHROME, "--headless=new", "--disable-gpu", "--no-sandbox",
                "--disable-features=WebRtcHideLocalIpsWithMdns",
                "--no-first-run", "--no-default-browser-check",
                f"--remote-debugging-port={self.port}",
                f"--user-data-dir={self.profile}",
                "--window-size=1000,800", "about:blank",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        self.ws = None
        self._id = 10
        try:
            wait_json(f"http://127.0.0.1:{self.port}/json/version", timeout=30)
            req = urllib.request.Request(
                f"http://127.0.0.1:{self.port}/json/new?{urllib.parse.quote(url, safe='')}",
                method="PUT",
            )
            with urllib.request.urlopen(req, timeout=15) as r:
                target = json.loads(r.read())
            self.ws = WS(target["webSocketDebuggerUrl"])
            self.ws.call(self.next_id(), "Page.enable")
            self.ws.call(self.next_id(), "Runtime.enable")
            self.ws.call(self.next_id(), "Log.enable")
            self.wait_js("window.__test !== undefined", 30, "test page")
        except Exception:
            self.close()
            raise

    def next_id(self):
        self._id += 1
        return self._id

    def ev(self, expr):
        res = self.ws.call(self.next_id(), "Runtime.evaluate", {
            "expression": expr,
            "returnByValue": True,
        })
        if "exceptionDetails" in res:
            details = res["exceptionDetails"]
            desc = (details.get("exception") or {}).get("description") or details.get("text")
            raise RuntimeError(f"JS error: {desc}\n  expression: {expr}")
        return res.get("result", {}).get("value")

    def wait_js(self, expr, timeout, label):
        end = time.time() + timeout
        last = None
        while time.time() < end:
            try:
                value = self.ev(expr)
            except RuntimeError as e:
                last = str(e)
            else:
                if value:
                    return value
            time.sleep(0.2)
        extra = f" (last error: {last})" if last else ""
        raise TimeoutError(f"{label}: timed out after {timeout}s waiting for {expr}{extra}")

    def console_text(self):
        out = []
        for ev in getattr(self.ws, "events", []) if self.ws else []:
            args = ev.get("args") or ev.get("entry")
            if isinstance(args, dict):
                out.append(str(args.get("text", args)))
            elif args:
                out.append("".join(str(a.get("value", a.get("description", ""))) for a in args
                                   if isinstance(a, dict)))
        return [line for line in out if line]

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


def require_net(page, label):
    kind = page.ev("typeof globalThis.XBNet")
    if kind != "object":
        raise AssertionError(f"{label}: XBNet is undefined (web/net.js did not load)")
    page.wait_js("__test.ready === true", 20, f"{label} enter")
    err = page.ev("__test.error")
    if err:
        raise AssertionError(f"{label}: test page failed: {err}")


def wait_connect(page, fd, timeout=25):
    end = time.time() + timeout
    while time.time() < end:
        state = page.ev(f"__test.connectState({fd})")
        if state == 1:
            return
        if state == -1:
            raise AssertionError(f"connectState({fd}) became -1 while waiting for the host")
        time.sleep(0.1)
    raise TimeoutError(f"connectState({fd}) did not reach 1 within {timeout}s")


def wait_connect_failure(page, fd, timeout=3.0):
    end = time.time() + timeout
    while time.time() < end:
        state = page.ev(f"__test.connectState({fd})")
        if state == -1:
            return
        if state == 1:
            raise AssertionError(f"connectState({fd}) connected to a room with no host")
        time.sleep(0.05)
    raise AssertionError(f"connectState({fd}) did not fail within {timeout}s")


def wait_data(page, fd, max_bytes, expected, timeout=10):
    end = time.time() + timeout
    while time.time() < end:
        r = page.ev(f"__test.recv({fd}, {max_bytes})")
        if r["kind"] == "data":
            check(r["data"] == expected, f"recv({fd}) returned {r['data']}, expected {expected}")
            return r["data"]
        if r["kind"] == "eof":
            raise AssertionError(f"recv({fd}) returned eof before {expected}")
        time.sleep(0.1)
    raise TimeoutError(f"recv({fd}) did not return {expected} within {timeout}s")


def wait_eof(page, fd, timeout=10):
    """Drain queued stream bytes, then require eof. Returns the drained bytes."""
    drained = []
    end = time.time() + timeout
    while time.time() < end:
        r = page.ev(f"__test.recv({fd}, 4096)")
        if r["kind"] == "eof":
            return drained
        if r["kind"] == "data":
            drained.extend(r["data"])
            continue
        time.sleep(0.1)
    raise TimeoutError(f"recv({fd}) did not return eof within {timeout}s")


def wait_accept(page, listen_fd, new_fd, timeout=20):
    end = time.time() + timeout
    while time.time() < end:
        peer = page.ev(f"__test.accept({listen_fd}, {new_fd})")
        if peer:
            return peer
        time.sleep(0.2)
    raise TimeoutError(f"accept({listen_fd}, {new_fd}) returned no peer within {timeout}s")


def peer_ready_expr(peers):
    return (
        "(()=>{try{const s=globalThis.XBNet.status(),t=globalThis.XBNet.stats();"
        f"return s.peers==={peers}&&t.ctlOpen&&t.actOpen}}catch(e){{return false}}}})()"
    )


def run_basic(base):
    room = unique_room()
    print(f"== basic: room {room} ==", flush=True)
    host = Page(f"{base}/test/net.html?role=host&room={room}&scenario=basic")
    client = Page(f"{base}/test/net.html?role=client&room={room}&scenario=basic")
    pages = [("host", host), ("client", client)]
    try:
        for label, page in pages:
            require_net(page, label)
        host_id = host.ev("XBNet.status().selfId")
        client_id = client.ev("XBNet.status().selfId")
        check(bool(host_id) and bool(client_id), "missing selfId")
        check(host_id != client_id, "host and client share a selfId")

        print("1. peer discovery and both channels open", flush=True)
        for label, page in pages:
            page.wait_js(peer_ready_expr(1), 60, f"{label} peer ready")
        check(host.ev("XBNet.stats().ctlOpen && XBNet.stats().actOpen") is True,
              "host ctl/act channels are not both open")
        check(client.ev("XBNet.stats().ctlOpen && XBNet.stats().actOpen") is True,
              "client ctl/act channels are not both open")

        print("2. host listen / client connect", flush=True)
        check(host.ev("__test.open(101, 'stream')") is True, "host open(101) failed")
        check(host.ev("__test.listen(101)") is True, "host listen(101) did not return true")
        check(client.ev("__test.open(201, 'stream')") is True, "client open(201) failed")
        client.ev("__test.connect(201)")
        wait_connect(client, 201)

        print("3. accept returns the client peer id", flush=True)
        accepted = wait_accept(host, 101, 102)
        check(accepted == client_id,
              f"accept returned {accepted!r}, expected client selfId {client_id!r}")

        print("4. host -> client stream bytes", flush=True)
        check(host.ev("__test.send(102, [1,2,3])") == 3, "host send(102) did not accept 3 bytes")
        wait_data(client, 201, 16, [1, 2, 3])

        print("5. client -> host stream bytes", flush=True)
        check(client.ev("__test.send(201, [4,5])") == 2, "client send(201) did not accept 2 bytes")
        wait_data(host, 102, 16, [4, 5])

        print("6. client half-close produces eof after queued data", flush=True)
        client.ev("__test.shutdownWrite(201)")
        drained = wait_eof(host, 102)
        check(drained == [], f"unexpected data before eof: {drained}")

        print("7. datagrams over xb.act", flush=True)
        host_peers = host.ev("XBNet.peerIds()")
        client_peers = client.ev("XBNet.peerIds()")
        check(host_peers == [client_id], f"host peerIds() = {host_peers!r}, expected [{client_id!r}]")
        check(client_peers == [host_id], f"client peerIds() = {client_peers!r}, expected [{host_id!r}]")
        check(host.ev("__test.open(103, 'dgram')") is True, "host open(103,dgram) failed")
        check(host.ev(f"__test.attachPeer(103, {json.dumps(client_id)})") is True,
              "host attachPeer(103) failed")
        check(client.ev("__test.open(202, 'dgram')") is True, "client open(202,dgram) failed")
        check(client.ev(f"__test.attachPeer(202, {json.dumps(host_id)})") is True,
              "client attachPeer(202) failed")
        check(host.ev("__test.send(103, [9,9])") == 2, "host dgram send did not accept 2 bytes")
        wait_data(client, 202, 16, [9, 9])

        print("8. closing the listen fd keeps the accepted stream alive", flush=True)
        host.ev("__test.closeFd(101)")
        check(host.ev("__test.send(102, [6])") == 1,
              "host could not send on the accepted stream after close(101)")
        wait_data(client, 201, 16, [6])

        print("9. closing an accepted stream does not leave the room", flush=True)
        host.ev("__test.closeFd(102)")
        drained = wait_eof(client, 201)
        check(drained == [], f"unexpected data before eof after close(102): {drained}")
        state = client.ev("XBNet.status().state")
        check(state == "joined", f"client room state after close(102) is {state!r}, expected 'joined'")

        print("basic: PASS", flush=True)
    except Exception:
        dump_pages(pages)
        raise
    finally:
        for _, page in pages:
            page.close()


def run_wrong_room(base):
    room = f"no-such-room-{unique_token()}"
    print(f"== wrong-room: room {room} ==", flush=True)
    page = Page(f"{base}/test/net.html?role=client&room={room}&scenario=wrong-room")
    try:
        require_net(page, "guest")
        started = time.time()
        wait_connect_failure(page, 301, timeout=3.0)
        elapsed = time.time() - started
        check(elapsed < 3.0, f"wrong-room connect took {elapsed:.2f}s (limit 3s)")
        print(f"wrong-room: PASS (failed after {elapsed:.2f}s)", flush=True)
    except Exception:
        dump_pages([("guest", page)])
        raise
    finally:
        page.close()


def run_multi(base):
    room = unique_room("xbmulti")
    print(f"== multi: room {room} ==", flush=True)
    host = Page(f"{base}/test/net.html?role=host&room={room}&scenario=multi")
    a = Page(f"{base}/test/net.html?role=client&room={room}&scenario=multi")
    b = Page(f"{base}/test/net.html?role=client&room={room}&scenario=multi")
    pages = [("host", host), ("client-a", a), ("client-b", b)]
    try:
        for label, page in pages:
            require_net(page, label)
        host_id = host.ev("XBNet.status().selfId")
        a_id = a.ev("XBNet.status().selfId")
        b_id = b.ev("XBNet.status().selfId")
        check(len({host_id, a_id, b_id}) == 3, "page selfIds are not distinct")

        print("1. all three pages see each other (mesh)", flush=True)
        for label, page in pages:
            page.wait_js(peer_ready_expr(2), 60, f"{label} peers ready")

        print("2. host listens, both clients connect", flush=True)
        check(host.ev("__test.open(101, 'stream')") is True, "host open(101) failed")
        check(host.ev("__test.listen(101)") is True, "host listen(101) did not return true")
        for label, page, fd in (("client-a", a, 201), ("client-b", b, 202)):
            check(page.ev(f"__test.open({fd}, 'stream')") is True, f"{label} open({fd}) failed")
            page.ev(f"__test.connect({fd})")
            wait_connect(page, fd)

        print("3. host accepts both clients", flush=True)
        accepted = {}
        for new_fd in (102, 103):
            peer = wait_accept(host, 101, new_fd)
            accepted[peer] = new_fd
        check(set(accepted) == {a_id, b_id},
              f"host accepted {sorted(accepted)!r}, expected {sorted([a_id, b_id])!r}")

        print("4. closing client A leaves client B working", flush=True)
        host.ev(f"__test.closeFd({accepted[a_id]})")
        wait_eof(a, 201)
        check(b.ev("__test.send(202, [7,7])") == 2,
              "client B send failed after host closed client A")
        wait_data(host, accepted[b_id], 16, [7, 7])
        state = host.ev("XBNet.status().state")
        check(state == "joined", f"host room state after closing A is {state!r}, expected 'joined'")
        check(b.ev("__test.connectState(202)") == 1, "client B connect state is no longer connected")
        print("multi: PASS", flush=True)
    except Exception:
        dump_pages(pages)
        raise
    finally:
        for _, page in pages:
            page.close()


def dump_pages(pages):
    for label, page in pages:
        print(f"-- {label} page --", file=sys.stderr)
        try:
            state = page.ev("JSON.stringify({test: globalThis.__test, net: globalThis.XBNet ? XBNet.status() : null, stats: globalThis.XBNet ? XBNet.stats() : null})")
            print("state:", state, file=sys.stderr)
        except Exception as e:
            print("state unavailable:", e, file=sys.stderr)
        for line in page.console_text():
            print("console:", line, file=sys.stderr)


SCENARIOS = {
    "basic": run_basic,
    "wrong-room": run_wrong_room,
    "multi": run_multi,
}


def main():
    wanted = sys.argv[1:] or ["basic", "wrong-room", "multi"]
    unknown = [name for name in wanted if name not in SCENARIOS]
    if unknown:
        print(f"unknown scenario(s): {', '.join(unknown)}", file=sys.stderr)
        return 2
    try:
        build()
    except subprocess.CalledProcessError as e:
        print(f"build failed: {e}", file=sys.stderr)
        return 1

    server, base = start_server()
    failures = []
    try:
        for name in wanted:
            print(f"\n===== {name} =====", flush=True)
            try:
                SCENARIOS[name](base)
            except Exception as e:
                failures.append((name, e))
                print(f"{name}: FAIL: {e}", file=sys.stderr)
                traceback.print_exc()
    finally:
        server.shutdown()
        server.server_close()

    if failures:
        print("\nFAILED: " + ", ".join(name for name, _ in failures), file=sys.stderr)
        return 1
    print("\nALL PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
