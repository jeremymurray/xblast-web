#!/usr/bin/env python3
"""Minimal localhost Nostr relay for the transport tests.

This is test infrastructure, not a relay for players. It binds 127.0.0.1, keeps
nothing on disk, and does not verify signatures. It implements the subset of the
Nostr relay protocol Trystero uses and honours the REQ kind/topic filters, so a
new page does not receive every event from earlier scenarios.

  ["EVENT", event]        -> OK to the sender; ["EVENT", subId, event] to each
                             matching subscription on the other clients
  ["REQ", subId, filter]  -> matching stored events, then EOSE
  ["CLOSE", subId]        -> forget it
"""
import argparse
import json
import threading

from websockets.sync.server import serve

MAX_EVENTS = 2000
EVENT_LIMIT = 200

clients = {}
events = []
lock = threading.Lock()


def event_matches(event, filters):
    if not filters:
        return True
    kind = event.get("kind")
    tags = event.get("tags") or []
    topics = {tag[1] for tag in tags
              if isinstance(tag, list) and len(tag) > 1 and tag[0] == "t"}
    for query in filters:
        if not isinstance(query, dict):
            continue
        if "kinds" in query and kind not in query["kinds"]:
            continue
        wanted = query.get("#t")
        if wanted and not topics.intersection(wanted):
            continue
        return True
    return False


def send(client, payload):
    with client["lock"]:
        client["ws"].send(payload)


def handler(ws):
    client = {"ws": ws, "subs": {}, "lock": threading.Lock()}
    with lock:
        clients[ws] = client
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
                send(client, json.dumps(["OK", str(event.get("id", "")), True, ""]))
                with lock:
                    events.append(event)
                    if len(events) > MAX_EVENTS:
                        del events[:len(events) - MAX_EVENTS]
                    targets = [(other, dict(other["subs"]))
                               for other in clients.values() if other is not client]
                for other, subs in targets:
                    for sub_id, filters in subs.items():
                        if event_matches(event, filters):
                            try:
                                send(other, json.dumps(["EVENT", sub_id, event]))
                            except Exception:
                                pass
            elif kind == "REQ" and len(message) > 1:
                sub_id = message[1]
                filters = message[2:]
                with lock:
                    client["subs"][sub_id] = filters
                    history = list(events)[-EVENT_LIMIT:]
                for event in history:
                    if event_matches(event, filters):
                        try:
                            send(client, json.dumps(["EVENT", sub_id, event]))
                        except Exception:
                            pass
                send(client, json.dumps(["EOSE", sub_id]))
            elif kind == "CLOSE" and len(message) > 1:
                with lock:
                    client["subs"].pop(message[1], None)
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
