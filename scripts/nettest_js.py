#!/usr/bin/env python3
"""Headless test for web/net.js over real WebRTC + public Nostr signalling.

Runs `./scripts/build-web.sh`, copies `web/test/net.html` into `web/dist/test/`,
serves `web/dist`, and drives two to seven headless Chrome pages with the CDP.

Scenarios:
  basic      two pages: stream connect/accept, both directions, half-close,
             datagrams, listen-close keeps accepted peers, peer-close keeps room
  multi      host + clients A/B: closing A's accepted stream leaves B working
  replace    a rejoin with a stable client id replaces the old peer
  wrong-room a lone guest must fail its connect within the configured timeout
  full       host + five clients fill the room; a sixth is refused, a rejoin
             replaces while full, a freed slot reopens it, and a match stage
             outranks the capacity message

Requires internet: the pages use the public Nostr relays Trystero ships with.
"""
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


def unique_client_id():
    return "".join(random.choice("0123456789abcdef") for _ in range(32))


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
    def __init__(self, url, wait_for="window.__test !== undefined"):
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
            self.wait_js(wait_for, 30, "test page")
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

    def reload(self):
        self.ws.call(self.next_id(), "Page.reload", {"ignoreCache": False})

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


def finish_pages(pages, ok, error=None):
    """Mark every driven page complete, then await its done/ok state."""
    value_ok = "true" if ok else "false"
    value_error = json.dumps(str(error) if error is not None else None)
    for label, page in pages:
        page.ev(f"__test.finish({value_ok}, {value_error})")
    for label, page in pages:
        page.wait_js("__test.done === true", 5, f"{label} completion")
        got = page.ev("__test.ok")
        check(got is ok, f"{label}: __test.ok is {got!r}, expected {ok!r}")


def finish_pages_best_effort(pages, error):
    try:
        finish_pages(pages, False, error)
    except Exception as e:
        print(f"could not mark test pages finished: {e}", file=sys.stderr)


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
    """Wait for the active connect to fail and prove it was the timeout path.

    A per-peer Trystero/relay error may be displayed, but it must not be a
    session-wide error: only the active connect's own timeout may fail it.
    """
    end = time.time() + timeout
    while time.time() < end:
        state = page.ev(f"__test.connectState({fd})")
        if state == -1:
            status = page.ev("XBNet.status()")
            check(status.get("error") is None,
                  f"connectState({fd}) failed with session error {status.get('error')!r}, "
                  "not the connect timeout")
            check(status.get("connectTimedOut") is True,
                  f"connectState({fd}) failed without connectTimedOut; status={status!r}")
            check(bool(status.get("connectError")),
                  f"connectState({fd}) timed out without a connectError; status={status!r}")
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

        finish_pages(pages, True)
        print("basic: PASS", flush=True)
    except Exception as e:
        finish_pages_best_effort(pages, e)
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
        # The page configured connectTimeoutMs = 500 and recorded performance.now()
        # immediately before connect(). A failure before that window would mean an
        # unrelated error, not the timeout path.
        failed_after_ms = page.ev("performance.now() - __test.connectAt")
        check(isinstance(failed_after_ms, (int, float)), "wrong-room page did not record connectAt")
        check(failed_after_ms >= 450,
              f"wrong-room connect failed after only {failed_after_ms:.0f}ms; expected the 500ms timeout")
        check(failed_after_ms < 3000,
              f"wrong-room connect failed after {failed_after_ms:.0f}ms; limit 3000ms")

        # A failed/timed-out connect must not poison the session: pressing
        # Connect again has to start a fresh attempt, not fail immediately.
        print("wrong-room: retry starts a clean connect", flush=True)
        retry_state = page.ev("__test.connect(301)")
        check(retry_state == 0,
              f"second connect returned {retry_state!r}, expected 0 (connecting)")
        check(page.ev("XBNet.status().connectTimedOut") is False,
              "second connect kept the previous connectTimedOut flag")
        retry_started = time.time()
        wait_connect_failure(page, 301, timeout=3.0)
        retry_elapsed = time.time() - retry_started
        check(retry_elapsed < 3.0,
              f"wrong-room retry failed after {retry_elapsed:.2f}s (limit 3s)")
        finish_pages([("guest", page)], True)
        print(f"wrong-room: PASS (failed after {failed_after_ms:.0f}ms; "
              f"retry failed after {retry_elapsed:.0f}ms)", flush=True)
    except Exception as e:
        finish_pages_best_effort([("guest", page)], e)
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

        print("1. host sees both guests; each guest sees the host", flush=True)
        # Clients ignore each other's channel hello (same role), so the
        # connected-peer count on a guest is one: the host. The host sees both.
        for label, page, expected in (("host", host, 2), ("client-a", a, 1), ("client-b", b, 1)):
            page.wait_js(peer_ready_expr(expected), 60, f"{label} peers ready")

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
        finish_pages(pages, True)
        print("multi: PASS", flush=True)
    except Exception as e:
        finish_pages_best_effort(pages, e)
        dump_pages(pages)
        raise
    finally:
        for _, page in pages:
            page.close()


def run_replace(base):
    room = unique_room("xbreplace")
    cid = unique_client_id()
    print(f"== replace: room {room} clientId {cid} ==", flush=True)
    host = Page(f"{base}/test/net.html?role=host&room={room}&scenario=replace")
    a = Page(f"{base}/test/net.html?role=client&room={room}&scenario=replace&clientId={cid}")
    pages = [("host", host), ("client-a", a)]
    a2 = None
    try:
        for label, page in pages:
            require_net(page, label)
        a_id = a.ev("XBNet.status().selfId")
        check(a.ev("XBNet.status().clientId") == cid,
              "client A did not use the fixed client id")

        print("1. host listens, client A connects and is accepted", flush=True)
        check(host.ev("__test.open(101, 'stream')") is True, "host open(101) failed")
        check(host.ev("__test.listen(101)") is True, "host listen(101) returned false")
        check(host.ev("XBNet.status().hostStage") == 1, "host stage is not listening")
        check(a.ev("__test.open(201, 'stream')") is True, "client A open(201) failed")
        a.ev("__test.connect(201)")
        wait_connect(a, 201)
        accepted = wait_accept(host, 101, 102)
        check(accepted == a_id, f"host accepted {accepted!r}, expected A {a_id!r}")
        check(host.ev("__test.send(102, [1])") == 1, "host send(102) failed")
        wait_data(a, 201, 16, [1])

        print("2. a second page with the same client id replaces A", flush=True)
        a2 = Page(f"{base}/test/net.html?role=client&room={room}&scenario=replace&clientId={cid}")
        pages.append(("client-a2", a2))
        require_net(a2, "client-a2")
        a2_id = a2.ev("XBNet.status().selfId")
        check(a2_id != a_id, "replacement page reused A's selfId")
        check(a2.ev("XBNet.status().clientId") == cid, "A2 did not use the fixed client id")
        check(a2.ev("__test.open(301, 'stream')") is True, "client A2 open(301) failed")
        a2.ev("__test.connect(301)")
        wait_connect(a2, 301)

        print("3. host closes the old peer and accepts the new one", flush=True)
        drained = wait_eof(a, 201)
        check(drained == [], f"unexpected data before old client eof: {drained}")
        host.wait_js("XBNet.stats().peers === 1", 20, "host has one active peer")
        check(host.ev("XBNet.peerIds()") == [a2_id],
              f"host peers {host.ev('XBNet.peerIds()')!r}, expected [{a2_id!r}]")
        accepted2 = wait_accept(host, 101, 103)
        check(accepted2 == a2_id, f"host accepted {accepted2!r}, expected A2 {a2_id!r}")
        check(host.ev("__test.send(103, [7,7])") == 2, "host send(103) failed")
        wait_data(a2, 301, 16, [7, 7])
        check(host.ev("XBNet.status().hostStage") == 1,
              "host stage changed away from listening after replacement")

        finish_pages(pages, True)
        print("replace: PASS", flush=True)
    except Exception as e:
        finish_pages_best_effort(pages, e)
        dump_pages(pages)
        raise
    finally:
        for _, page in pages:
            page.close()


def run_full(base):
    """Room capacity: five guests fit, a sixth is refused, a freed slot reopens it."""
    room = unique_room("xbfull")
    print(f"== full: room {room} ==", flush=True)
    host = Page(f"{base}/test/net.html?role=host&room={room}&scenario=full")
    guests = [Page(f"{base}/test/net.html?role=client&room={room}&scenario=full")
              for _ in range(5)]
    extra = None
    rejoiner = None
    late = None
    pages = [("host", host)] + [(f"guest-{i + 1}", g) for i, g in enumerate(guests)]
    try:
        for label, page in pages:
            require_net(page, label)
            # Seven light pages plus a full Trystero mesh can take longer than
            # the 20 s product default to complete ICE; the capacity checks do
            # not depend on being quick.
            page.ev("__test.configure({connectTimeoutMs: 180000})")
        host_id = host.ev("XBNet.status().selfId")
        guest_ids = [g.ev("XBNet.status().selfId") for g in guests]
        check(len({host_id, *guest_ids}) == 6, "page selfIds are not distinct")
        check(host.ev("XBNet.status().maxClients") == 5,
              "status().maxClients is not the five-guest cap")

        print("1. host listens, five guests connect", flush=True)
        check(host.ev("__test.open(101, 'stream')") is True, "host open(101) failed")
        check(host.ev("__test.listen(101)") is True, "host listen(101) did not return true")
        for i, guest in enumerate(guests):
            fd = 201 + i
            check(guest.ev(f"__test.open({fd}, 'stream')") is True,
                  f"guest {i + 1} open({fd}) failed")
            guest.ev(f"__test.connect({fd})")
            wait_connect(guest, fd, timeout=170)
        host.wait_js("XBNet.status().peers === 5", 180, "host sees five helloed guests")

        print("2. host accepts four; one stays pending", flush=True)
        accepted = {}
        for new_fd in (102, 103, 104, 105):
            accepted[wait_accept(host, 101, new_fd)] = new_fd
        check(len(accepted) == 4 and set(accepted) <= set(guest_ids),
              f"host accepted {sorted(accepted)!r}, expected four of {sorted(guest_ids)!r}")

        print("3. a sixth guest is refused while one is still pending", flush=True)
        extra = Page(f"{base}/test/net.html?role=client&room={room}&scenario=full")
        require_net(extra, "guest-6")
        extra.ev("__test.configure({connectTimeoutMs: 180000})")
        extra.ev("__test.open(301, 'stream')")
        extra.ev("__test.connect(301)")
        extra.wait_js(
            "(() => { const s = XBNet.status(); return s.connectError === "
            "'The room is full (6 players).'; })()",
            30, "sixth guest got the room-full message")
        check(extra.ev("__test.connectState(301)") == -1,
              "sixth guest connect did not fail")
        check(extra.ev("XBNet.stats().peers") == 0,
              "rejected guest still counts a connected peer")
        check(host.ev("XBNet.status().peers") == 5,
              "host peer count changed after the reject")
        check(host.ev("XBNet.status().full") is True,
              "host does not report the room as full")
        extra.wait_js("__test.recv(301, 64).kind === 'eof'", 15,
                      "the refused guest's stream ended")

        print("3b. a later Connect on the refused page fails at once", flush=True)
        check(extra.ev("__test.connect(301)") == -1,
              "connect after a refusal did not fail immediately")
        extra.wait_js(
            "XBNet.status().connectError === 'The room is full (6 players).'",
            10, "refused guest kept the room-full reason")

        print("4. the pending guest is accepted; the room stays full", flush=True)
        pending = set(guest_ids) - set(accepted)
        check(len(pending) == 1, f"expected one pending guest, got {sorted(pending)!r}")
        accepted[wait_accept(host, 101, 106)] = 106
        check(set(accepted) == set(guest_ids), "host did not accept every helloed guest")
        check(host.ev("XBNet.status().peers") == 5, "host peer count is not five")
        check(host.ev("XBNet.status().full") is True, "host stopped reporting full")

        print("5. a rejoin of an existing client id still replaces while full", flush=True)
        joiner_id = guests[1].ev("XBNet.status().clientId")
        rejoiner = Page(f"{base}/test/net.html?role=client&room={room}"
                        f"&scenario=full&clientId={joiner_id}")
        require_net(rejoiner, "rejoiner")
        rejoiner.ev("__test.configure({connectTimeoutMs: 180000})")
        rejoiner.ev("__test.open(401, 'stream')")
        rejoiner.ev("__test.connect(401)")
        wait_connect(rejoiner, 401)
        check(wait_accept(host, 101, 107) == rejoiner.ev("XBNet.status().selfId"),
              "host accepted the wrong peer for the rejoining client")
        wait_eof(guests[1], 202)
        host.wait_js("XBNet.status().peers === 5", 15, "host still has five guests")
        check(host.ev("XBNet.status().full") is True, "host stopped reporting full")

        print("6. a match stage outranks the capacity message", flush=True)
        host.ev("__test.closeFd(101)")          # listen closes, accepted peers stay
        host.wait_js("XBNet.status().hostStage === 2", 15, "host stage match")
        check(host.ev("XBNet.status().full") is True, "host stopped reporting full")
        late = Page(f"{base}/test/net.html?role=client&room={room}&scenario=full")
        require_net(late, "late")
        late.ev("__test.configure({connectTimeoutMs: 180000})")
        late.ev("__test.open(501, 'stream')")
        late.ev("__test.connect(501)")
        # Poll like the engine does: the host's hello (and with it the stage)
        # can arrive after the first connectState call.
        late.wait_js(
            "(() => { const st = __test.connectState(501); const s = XBNet.status(); "
            "return st === -1 && s.connectError === "
            "'The host is already in a match.'; })()",
            30, "late guest got the match message")
        check(late.ev("__test.connectState(501)") == -1, "late guest connect did not fail")
        check(host.ev("XBNet.status().peers") == 5,
              "host counted the late guest as a peer")

        print("6b. a hello retransmit cannot evict an accepted guest", flush=True)
        host_id = host.ev("XBNet.status().selfId")
        guests[2].ev(f"XBNet.__resendHello({json.dumps(host_id)})")
        time.sleep(1.0)
        check(host.ev("XBNet.status().peers") == 5,
              "a hello retransmit dropped an accepted guest")

        print("7. a guest leaving frees the slot", flush=True)
        first = guest_ids[0]
        host.ev(f"__test.closeFd({accepted[first]})")
        wait_eof(guests[0], 201)
        host.wait_js("XBNet.status().full === false", 15, "host no longer full")
        check(host.ev("XBNet.stats().peers") == 4,
              "host peer count is not four after a leave")

        finish_pages(pages + [("guest-6", extra), ("rejoiner", rejoiner),
                              ("late", late)], True)
        print("full: PASS", flush=True)
    except Exception as e:
        finish_pages_best_effort(pages + [("guest-6", extra), ("rejoiner", rejoiner),
                                          ("late", late)], e)
        dump_pages([p for p in pages + [("guest-6", extra), ("rejoiner", rejoiner),
                                        ("late", late)] if p[1] is not None])
        raise
    finally:
        for page in [host, *guests, extra, rejoiner, late]:
            if page is not None:
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


def run_roomcode(base):
    page = open_lobby(base)
    try:
        page.wait_js("typeof makeCode === 'function'", 10, "room-code generator")
        codes = page.ev("Array.from({length: 200}, () => makeCode())")
        for code in codes:
            check(re.fullmatch(r"[a-z]{5}-[a-z]{3,5}-[1-9][0-9]{2}", code) is not None,
                  f"bad room code {code!r}")
            adj, noun, num = code.split("-")
            check(100 <= int(num) <= 999, f"bad number in {code!r}")
            check(page.ev(f"ADJECTIVES.includes({json.dumps(adj)})"),
                  f"unknown adjective {adj!r}")
            check(page.ev(f"ANIMALS.includes({json.dumps(noun)})"),
                  f"unknown animal {noun!r}")
        check(page.ev("normalizeRoom(' Quiet Otter 482 ')") == "quiet-otter-482",
              "normalizeRoom did not normalize spaces/case")
    finally:
        page.close()


def run_turn_config(base):
    page = Page(f"{base}/test/net.html?scenario=turn-config")
    try:
        page.wait_js("__test.ready === true", 20, "turn-config ready")
        page.wait_js("__test.done === true", 20, "turn-config done")
        err = page.ev("__test.error")
        if err:
            raise AssertionError(f"turn-config failed: {err}")
        check(page.ev("__test.ok") is True, "turn-config did not pass")
        for line in page.ev("__test.lines"):
            print(line, flush=True)
    finally:
        page.close()


def open_lobby(base):
    return Page(f"{base}/index.html",
                wait_for="!!document.getElementById('turn-advanced')")


def set_turn_fields(page, urls, username, credential):
    page.ev(
        "document.getElementById('turn-urls').value = " + json.dumps(urls) + ";" +
        "document.getElementById('turn-user').value = " + json.dumps(username) + ";" +
        "document.getElementById('turn-cred').value = " + json.dumps(credential) + "; true")


def run_turn_ui(base):
    # Storage, hydration and Forget.
    page = open_lobby(base)
    try:
        check(page.ev("document.getElementById('turn-cred').type") == "password",
              "credential field is not a password input")
        page.ev("sessionStorage.setItem('xb:turn', JSON.stringify({"
                "urls:['turn:relay.example.org:3478'],username:'u',"
                "credential:'sekrit-credential-123'})); true")
        page.reload()
        page.wait_js("document.getElementById('turn-urls').value === "
                     "'turn:relay.example.org:3478'", 10, "stored override")
        check(page.ev("document.getElementById('turn-advanced').open") is True,
              "stored override did not open the panel")
        check(page.ev("document.getElementById('turn-user').value") == "u",
              "stored username was not restored")
        check(not page.ev("document.body.innerText.includes('sekrit-credential-123')"),
              "credential leaked into page text")
        check(page.ev("localStorage.getItem('xb:turn')") is None,
              "override leaked into localStorage")
        page.ev("document.getElementById('turn-forget').click()")
        page.wait_js("document.getElementById('turn-urls').value === ''", 5, "forget url")
        page.wait_js("document.getElementById('turn-user').value === ''", 5, "forget user")
        page.wait_js("document.getElementById('turn-cred').value === ''", 5, "forget credential")
        check(page.ev("sessionStorage.getItem('xb:turn')") is None,
              "Forget left the override in storage")
    finally:
        page.close()

    # A malformed override must be visible and must not start the room.
    page = open_lobby(base)
    try:
        set_turn_fields(page, "stun:stun.example.org", "u", "p")
        page.ev("document.getElementById('host').click(); true")
        page.wait_js("document.getElementById('turn-error').textContent.length > 0",
                     10, "invalid override error")
        check(page.ev("document.getElementById('landing').classList.contains('show')") is True,
              "invalid override left the lobby")
        check(page.ev("globalThis.XBNet ? XBNet.status().role : null") is None,
              "invalid override started a session")

        # Fixing the fields and retrying uses the player override before enter().
        set_turn_fields(page, "turn:relay.example.org:3478", "u", "p")
        page.ev("document.getElementById('host').click(); true")
        page.wait_js("globalThis.XBNet && XBNet.status().turnSource === 'player'",
                     20, "player override applied")
        check(page.ev("XBNet.status().turnConfigured") is True,
              "player override was not configured")
        check(page.ev("document.getElementById('landing').classList.contains('show')") is False,
              "valid override did not leave the lobby")
        check(any("TURN configured" in line for line in page.console_text()),
              "missing one-time TURN configured log")
    finally:
        page.close()

    # A malformed turn.json must not stop Host.
    malformed = os.path.join(DIST, "turn.json")
    with open(malformed, "w", encoding="utf-8") as handle:
        handle.write("{not json")
    page = open_lobby(base)
    try:
        page.ev("document.getElementById('host').click(); true")
        page.wait_js("globalThis.XBNet && XBNet.status().role === 'host'",
                     20, "host with malformed turn.json")
        check(page.ev("XBNet.status().turnConfigured") is False,
              "malformed turn.json produced TURN config")
    finally:
        page.close()
        try:
            os.remove(malformed)
        except OSError:
            pass


SCENARIOS = {
    "basic": run_basic,
    "wrong-room": run_wrong_room,
    "multi": run_multi,
    "replace": run_replace,
    "full": run_full,
    "turn-config": run_turn_config,
    "turn-ui": run_turn_ui,
    "roomcode": run_roomcode,
}


def main():
    wanted = sys.argv[1:] or [
        "basic", "wrong-room", "multi", "replace", "full", "turn-config", "turn-ui",
        "roomcode",
    ]
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
