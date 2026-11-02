#!/usr/bin/env python3
"""Capture a screenshot from headless Chrome via the DevTools protocol.

No third-party dependencies: speaks just enough WebSocket and CDP for a
screenshot plus a JS evaluation.
"""
import base64
import json
import os
import shutil
import socket
import struct
import subprocess
import sys
import time
import urllib.parse
import urllib.request

def _find_chrome():
    """Locate Chrome/Chromium on macOS or Linux; XB_CHROME overrides."""
    env = os.environ.get("XB_CHROME")
    candidates = [env] if env else []
    candidates += [
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/usr/bin/google-chrome",
        "/usr/bin/google-chrome-stable",
        "/usr/bin/chromium",
        "/usr/bin/chromium-browser",
        "/snap/bin/chromium",
    ]
    for path in candidates:
        if path and os.path.exists(path):
            return path
    for name in ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser"):
        found = shutil.which(name)
        if found:
            return found
    return "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"


CHROME = _find_chrome()


class WS:
    def __init__(self, url):
        u = urllib.parse.urlparse(url)
        self.sock = socket.create_connection((u.hostname, u.port), timeout=30)
        key = base64.b64encode(os.urandom(16)).decode()
        req = (
            f"GET {u.path} HTTP/1.1\r\nHost: {u.hostname}:{u.port}\r\n"
            "Upgrade: websocket\r\nConnection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n"
        )
        self.sock.sendall(req.encode())
        self.events = []
        buf = b""
        while b"\r\n\r\n" not in buf:
            buf += self.sock.recv(4096)
        if b" 101 " not in buf.split(b"\r\n", 1)[0]:
            raise RuntimeError("websocket handshake failed")

    def send(self, obj):
        payload = json.dumps(obj).encode()
        header = bytearray([0x81])
        n = len(payload)
        if n < 126:
            header.append(0x80 | n)
        elif n < 65536:
            header.append(0x80 | 126)
            header += struct.pack("!H", n)
        else:
            header.append(0x80 | 127)
            header += struct.pack("!Q", n)
        mask = os.urandom(4)
        header += mask
        masked = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
        self.sock.sendall(bytes(header) + masked)

    def _read(self, n):
        out = b""
        while len(out) < n:
            chunk = self.sock.recv(n - len(out))
            if not chunk:
                raise RuntimeError("websocket closed")
            out += chunk
        return out

    def recv(self):
        while True:
            b1, b2 = self._read(2)
            opcode = b1 & 0x0F
            n = b2 & 0x7F
            if n == 126:
                n = struct.unpack("!H", self._read(2))[0]
            elif n == 127:
                n = struct.unpack("!Q", self._read(8))[0]
            data = self._read(n)
            if opcode == 0x8:
                raise RuntimeError("websocket closed")
            if opcode == 0x9:  # ping
                continue
            return json.loads(data)

    def call(self, id_, method, params=None):
        self.send({"id": id_, "method": method, "params": params or {}})
        while True:
            msg = self.recv()
            if msg.get("id") == id_:
                if "error" in msg:
                    raise RuntimeError(f"{method}: {msg['error']}")
                return msg.get("result", {})
            if msg.get("method") == "Runtime.consoleAPICalled":
                self.events.append(msg["params"])
            elif msg.get("method") == "Log.entryAdded":
                self.events.append(msg["params"])


def wait_json(url, timeout=20):
    end = time.time() + timeout
    while time.time() < end:
        try:
            with urllib.request.urlopen(url, timeout=1) as r:
                return json.loads(r.read())
        except Exception:
            time.sleep(0.2)
    raise RuntimeError(f"timed out waiting for {url}")


def send_key(ws, name):
    keys = {
        "space": (" ", "Space", 32),
        "return": ("\r", "Enter", 13),
        "escape": ("Escape", "Escape", 27),
        "tab": ("Tab", "Tab", 9),
        "up": ("ArrowUp", "ArrowUp", 38),
        "down": ("ArrowDown", "ArrowDown", 40),
        "left": ("ArrowLeft", "ArrowLeft", 37),
        "right": ("ArrowRight", "ArrowRight", 39),
    }
    key, code, vk = keys[name.lower()]
    for typ in ("keyDown", "keyUp"):
        ws.call(10, "Input.dispatchKeyEvent", {
            "type": typ,
            "key": key,
            "code": code,
            "windowsVirtualKeyCode": vk,
            "nativeVirtualKeyCode": vk,
            "text": key if typ == "keyDown" and len(key) == 1 else "",
        })


def send_click(ws, gx, gy, gw=960, gh=736):
    rect = ws.call(20, "Runtime.evaluate", {
        "expression": "JSON.stringify(document.getElementById('canvas').getBoundingClientRect())",
        "returnByValue": True,
    })["result"]["value"]
    r = json.loads(rect)
    print("canvas rect:", r)
    x = r["left"] + gx * r["width"] / gw
    y = r["top"] + gy * r["height"] / gh
    ws.call(22, "Runtime.evaluate", {
        "expression": "window.__clicks=[];document.getElementById('canvas').addEventListener('mousedown',e=>window.__clicks.push([e.offsetX,e.offsetY,e.clientX,e.clientY]));",
    })
    for typ in ("mousePressed", "mouseReleased"):
        ws.call(21, "Input.dispatchMouseEvent", {
            "type": typ, "x": x, "y": y, "button": "left", "buttons": 1, "clickCount": 1,
        })
    got = ws.call(23, "Runtime.evaluate", {
        "expression": "JSON.stringify(window.__clicks)", "returnByValue": True,
    })["result"]["value"]
    print("click at page", round(x, 1), round(y, 1), "->", got)


def main():
    url = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8123/index.html"
    out = sys.argv[2] if len(sys.argv) > 2 else "/tmp/xblast-shot.png"
    wait = float(sys.argv[3]) if len(sys.argv) > 3 else 8.0
    port = 9333
    profile = "/tmp/xb-cdp-profile"
    shutil.rmtree(profile, ignore_errors=True)

    proc = subprocess.Popen(
        [
            CHROME, "--headless=new", "--disable-gpu", "--no-sandbox",
            f"--remote-debugging-port={port}", f"--user-data-dir={profile}",
            "--window-size=1000,800", "about:blank",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        wait_json(f"http://127.0.0.1:{port}/json/version")
        req = urllib.request.Request(
            f"http://127.0.0.1:{port}/json/new?{urllib.parse.quote(url, safe='')}",
            method="PUT",
        )
        with urllib.request.urlopen(req, timeout=10) as r:
            target = json.loads(r.read())
        ws = WS(target["webSocketDebuggerUrl"])
        ws.call(1, "Page.enable")
        ws.call(2, "Runtime.enable")
        ws.call(5, "Runtime.evaluate", {
            "expression": "document.getElementById('play') && document.getElementById('play').click()",
        })
        time.sleep(wait)
        if len(sys.argv) > 4:
            for token in sys.argv[4].split(","):
                if ":" in token:
                    name, delay = token.rsplit(":", 1)
                    time.sleep(float(delay))
                else:
                    name = token
                send_key(ws, name)
            time.sleep(2.0)
        if len(sys.argv) > 5:
            gx, gy = (float(v) for v in sys.argv[5].split(","))
            send_click(ws, gx, gy)
            time.sleep(3.0)
        state = ws.call(3, "Runtime.evaluate", {
            "expression": "JSON.stringify({status: document.getElementById('status') && document.getElementById('status').textContent, title: document.title, overlay: document.getElementById('overlay').className, canvases: [...document.querySelectorAll('canvas')].map(c => [c.id, c.width, c.height, c.getBoundingClientRect().x, c.getBoundingClientRect().y])})",
            "returnByValue": True,
        })
        print("page:", state.get("result", {}).get("value"))
        shot = ws.call(4, "Page.captureScreenshot", {"format": "png"})
        for ev in ws.events:
            if ev.get("args"):
                text = "".join(str(a.get("value", a.get("description", ""))) for a in ev["args"])
                if "xb:" in text:
                    print("console:", text)
        with open(out, "wb") as f:
            f.write(base64.b64decode(shot["data"]))
        print("wrote", out)
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
        shutil.rmtree(profile, ignore_errors=True)


if __name__ == "__main__":
    main()
