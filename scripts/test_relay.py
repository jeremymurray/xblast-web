#!/usr/bin/env python3
"""Minimal localhost Nostr relay for the transport tests.

This is test infrastructure, not a relay for players. It binds 127.0.0.1, keeps
nothing on disk, does not verify signatures, and ignores filters: Trystero's
clients filter by topic themselves.

Protocol subset used by Trystero:
  ["EVENT", event]        -> OK to the sender; to every other client, one
                             ["EVENT", subId, event] per subscription
  ["REQ", subId, ...]     -> EOSE
  ["CLOSE", subId]        -> forget it
"""
import argparse
import json
import threading

from websockets.sync.server import serve

clients = {}
lock = threading.Lock()


def send(ws, payload):
    with lock:
        ws.send(payload)


def handler(ws):
    with lock:
        clients[ws] = set()
    try:
        for raw in ws:
            try:
                message = json.loads(raw)
            except ValueError:
                continue
            if not isinstance(message, list) or not message:
                continue
            kind = message[0]
            if kind == "EVENT" and len(message) > 1 and isinstance(message[1], dict):
                event = message[1]
                send(ws, json.dumps(["OK", str(event.get("id", "")), True, ""]))
                with lock:
                    targets = [(other, set(subs)) for other, subs in clients.items()
                               if other is not ws]
                for other, subs in targets:
                    for sub_id in subs:
                        try:
                            send(other, json.dumps(["EVENT", sub_id, event]))
                        except Exception:
                            pass
            elif kind == "REQ" and len(message) > 1:
                with lock:
                    clients.setdefault(ws, set()).add(message[1])
                send(ws, json.dumps(["EOSE", message[1]]))
            elif kind == "CLOSE" and len(message) > 1:
                with lock:
                    clients.get(ws, set()).discard(message[1])
    finally:
        with lock:
            clients.pop(ws, None)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, required=True)
    args = parser.parse_args()
    with serve(handler, "127.0.0.1", args.port) as server:
        print("READY", flush=True)
        server.serve_forever()


if __name__ == "__main__":
    main()
