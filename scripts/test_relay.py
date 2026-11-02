#!/usr/bin/env python3
"""Minimal localhost Nostr relay for the transport tests.

This is test infrastructure, not a relay for players. It binds 127.0.0.1, keeps
nothing on disk, does not verify signatures, and ignores filters: Trystero's
clients filter by topic themselves.

Protocol subset used by Trystero:
  ["EVENT", event]        -> OK to the sender, broadcast to the other clients
  ["REQ", subId, ...]     -> EOSE
  ["CLOSE", subId]        -> ignored
"""
import argparse
import json
import threading

from websockets.sync.server import serve

clients = set()
lock = threading.Lock()


def handler(ws):
    with lock:
        clients.add(ws)
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
                ws.send(json.dumps(["OK", str(event.get("id", "")), True, ""]))
                with lock:
                    others = [client for client in clients if client is not ws]
                for client in others:
                    try:
                        client.send(raw)
                    except Exception:
                        pass
            elif kind == "REQ" and len(message) > 1:
                ws.send(json.dumps(["EOSE", message[1]]))
            elif kind == "CLOSE":
                pass
    finally:
        with lock:
            clients.discard(ws)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, required=True)
    args = parser.parse_args()
    with serve(handler, "127.0.0.1", args.port) as server:
        print("READY", flush=True)
        server.serve_forever()


if __name__ == "__main__":
    main()
