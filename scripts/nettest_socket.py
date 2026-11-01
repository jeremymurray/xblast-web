#!/usr/bin/env python3
"""Two-page wasm test for web/net_web.c over real WebRTC DataChannels."""
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
from cdp_shot import CHROME, WS, wait_json  # noqa: E402


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

    port = free_port()
    server = Server(("127.0.0.1", port), functools.partial(Handler, directory=DIST))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, f"http://127.0.0.1:{port}"


class Page:
    def __init__(self, url):
        self.port = free_port()
        self.profile = tempfile.mkdtemp(prefix="xb-socket-test-profile-")
        self.proc = subprocess.Popen([
            CHROME, "--headless=new", "--disable-gpu", "--no-sandbox",
            "--disable-features=WebRtcHideLocalIpsWithMdns",
            "--no-first-run", "--no-default-browser-check",
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
            self.wait_js("window.__nettest !== undefined", 30, "nettest page")
        except Exception:
            self.close()
            raise

    def id(self):
        self.next_id += 1
        return self.next_id

    def ev(self, expression):
        result = self.ws.call(self.id(), "Runtime.evaluate", {
            "expression": expression, "returnByValue": True,
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

    def console_text(self):
        lines = []
        for event in getattr(self.ws, "events", []) if self.ws else []:
            args = event.get("args") or event.get("entry")
            if isinstance(args, dict):
                lines.append(str(args.get("text", args)))
            elif args:
                lines.append("".join(str(arg.get("value", arg.get("description", "")))
                                     for arg in args if isinstance(arg, dict)))
        return [line for line in lines if line]

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


def dump_page(label, page):
    try:
        print(f"{label}: state={page.ev('window.__nettest')}", file=sys.stderr)
        print(f"{label}: XBNet={page.ev('globalThis.XBNet ? XBNet.status() : null')}", file=sys.stderr)
        for line in page.console_text():
            print(f"{label}: console: {line}", file=sys.stderr)
    except Exception as error:
        print(f"{label}: could not dump page: {error}", file=sys.stderr)


def main():
    print("== building socket shim harness ==", flush=True)
    subprocess.run([os.path.join(SCRIPTS, "build-web.sh")], cwd=ROOT, check=True)
    subprocess.run([os.path.join(SCRIPTS, "build-nettest.sh")], cwd=ROOT, check=True)

    server, base = start_server()
    pages = []
    try:
        room = "xbsock-" + "".join(random.choice("0123456789abcdef") for _ in range(8))
        print(f"== room {room} ==", flush=True)
        host = Page(f"{base}/nettest.html?role=host&room={room}")
        pages.append(("host", host))
        client = Page(f"{base}/nettest.html?role=client&room={room}")
        pages.append(("client", client))
        client_id = client.ev("XBNet.status().selfId")
        if not client_id:
            raise AssertionError("client XBNet.status().selfId is empty")

        deadline = time.time() + 30
        states = {}
        while time.time() < deadline:
            for label, page in pages:
                states[label] = page.ev("window.__nettest")
            if all(state and state.get("done") for state in states.values()):
                break
            if any(state and str(state.get("msg", "")).startswith("fail:")
                   for state in states.values()):
                break
            time.sleep(0.1)
        else:
            raise TimeoutError(f"socket harness did not finish in 30s: {states}")

        host_msg = states["host"].get("msg", "")
        client_msg = states["client"].get("msg", "")
        expected_host = f"host-ok:{client_id}"
        if expected_host not in host_msg.split():
            raise AssertionError(f"host result {host_msg!r} lacks {expected_host!r}")
        if "client-ok" not in client_msg.split():
            raise AssertionError(f"client result is {client_msg!r}")
        for label, message in (("host", host_msg), ("client", client_msg)):
            tokens = message.split()
            for expected in ("dgram-ok", "listen-close-ok"):
                if expected not in tokens:
                    raise AssertionError(f"{label} result {message!r} lacks {expected!r}")
        print(f"host: {host_msg}")
        print(f"client: {client_msg}")
        print("socket shim: PASS")
    except Exception:
        for label, page in pages:
            dump_page(label, page)
        traceback.print_exc()
        return 1
    finally:
        for _, page in pages:
            page.close()
        server.shutdown()
        server.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
