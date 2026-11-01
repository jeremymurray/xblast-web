# Reconnect/replace — short design

Date: 2026-10-31
Status: awaiting approval
Scope: M3 slice 1, pre-match guest refresh/rejoin
Related: `docs/superpowers/specs/2026-10-31-m2-p2p-design.md` (M2 transport)

## 1. Intent

A guest who refreshes the page before the match starts should be able to rejoin the same
room and have the host replace the stale client instead of ending up with two clients,
one of them dead. A refresh during a running match should fail immediately with a clear
"the host is already playing" message, not hang in the wait screen.

This is the first M3 slice. It uses the existing room and socket shim; no engine netcode
changes.

## 2. Goals

1. A refreshed guest gets a stable per-tab client id, rejoins the same room, and the host
   replaces the old peer with the same id.
2. The host frees the old client slot (the engine sees the old stream EOF) and accepts the
   new peer.
3. A refresh after the match has started fails fast with a clear reason.
4. The lobby remembers the last room/role and offers a one-click **Rejoin** after a reload.
5. The change is JS/HTML only; no `socket.h`, `com_*`, `net_*`, or game-logic edits.

## 3. Non-goals

- **Mid-match resume/replay.** A refreshed guest rejoining an in-progress match needs an
  engine state snapshot/replay. Recorded as a later todo in `PROGRESS.md`.
- Host migration. A refreshed host restarts as a new host; guests reconnect manually.
- Reconnect after a network drop (as opposed to a page reload).
- Room passwords or stronger access control.
- Six-player UI work beyond the replacement mechanism scaling naturally.

## 4. Current behaviour

- `web/net.js` creates one Trystero room per page and two negotiated channels per peer.
- The ctl hello is `[CTL_HELLO, HELLO_VERSION=1, role]`; peers are identified only by
  Trystero `selfId`, which changes on every page load.
- The host accepts any pending client; a refreshed guest therefore appears as a second
  client while the old peer/stream is still alive.
- The guest's `connectState` returns success as soon as a host hello is present. If the
  host is already in a match, the guest enters the wait screen and waits for config that
  will never come.

## 5. Protocol v2

Bump `HELLO_VERSION` to 2.

```
CTL_HELLO  = 1: [1, 2, role, idLen, ...idBytes, stage]
CTL_DATA   = 2: [2, ...engine bytes]
CTL_EOF    = 3: [3]
CTL_CLOSE  = 4: [4]
CTL_STATUS = 5: [5, stage]
```

- `role`: `1` host, `2` client.
- `idLen`: 1 byte, 16 for our ids.
- `idBytes`: 16 random bytes, hex-encoded in JS for map keys. Stable per tab via
  `sessionStorage`; if storage is unavailable, fall back to a per-page id.
- `stage`: the sender's host stage (see below); clients send `0`.
- `CTL_STATUS` is sent by the host after hello and whenever the stage changes. Clients
  ignore a status frame from a non-host peer.
- A peer with version != 2, a bad role, or a bad id length is `invalid` (no engine traffic).

## 6. Host stages

```
0 setup     host page entered, engine not listening yet
1 listening host is accepting clients (wait screen)
2 match     listen socket closed, accepted clients still connected
3 idle      no listen, no accepted clients (stopped/back at menu)
```

- `enter('host')` → 0.
- `listen()` → 1.
- `close(listenFd)` → 2 if any accepted peer is still open, else 3.
- Accepted peer closes/leaves → recompute 2/3 (if listen is closed).
- `leave()` clears the session.
- The host broadcasts `CTL_STATUS` to active peers on every change; the hello carries the
  current stage so the guest sees it immediately.

Guest `connectState(fd)`:
- host stage 2 → `-1`, `connectError = "The host is already in a match."`
- host stage 3 → `-1`, `connectError = "The host is not accepting players."`
- stages 0/1 or unknown → success once the host hello/ctl is open (the guest may wait for
  the host to finish setup, as in M2).

The lobby shows `connectError` and returns to the join menu; it does not hang.

## 7. Host replacement

On a host hello with `clientId`:

1. Find any other peer with the same `clientId` (scan the small peer map).
2. If found and it is a different `peerId`:
   - `closePeerChannels(old, sendClose=true)`; this sets `closed/eof` and sends
     `CTL_CLOSE`.
   - Remove it from `pending`; mark it `replacedBy`.
   - Keep the peer object in the map while bound fds still reference it; `activePeers`
     excludes closed peers.
3. Store `clientId` on the new peer; enqueue it in `pending` as today.
4. The host's existing accepted stream for the old peer sees EOF, so the engine's
   `DeleteToClient`/`Server_StreamEvent` frees the old client slot on the next tick.
5. `accept()` skips closed peers, so the new peer is accepted next.
6. If the old peer was only pending, nothing else is needed.

The engine may briefly hold both the old and new client slots; it already supports up to
`MAX_HOSTS`. The host wait menu removes the old client on `XBNW_Disconnected` and shows the
new one on `XBNW_Accepted`.

Host refresh:
- The host has no state to resume. `sessionStorage` offers **Re-host room X**; the new host
  page starts fresh. Guests see the old host leave and must rejoin.
- The host's client id is stable but irrelevant to replacement (there is only one host).

## 8. Lobby rejoin

- `startNet(mode)` stores `{mode, room}` and the stable client id in `sessionStorage`
  (`xb:lastRoom`, `xb:clientId`).
- On load, if `xb:lastRoom` is valid, prefill the room input and show a small **Rejoin room
  X** / **Re-host room X** button. It calls `startNet(mode)`; the engine loads and the user
  continues through the existing setup/join menu. No auto-load, so a reload is not
  surprising and a mid-match refresh can show the failure reason.
- **Leave** clears `xb:lastRoom` before reloading; **Solo** also clears it.
- If `sessionStorage` is unavailable, no banner and a per-page id; the rest still works.

## 9. Edge cases

- **Host still in setup (stage 0):** guest connects and waits; replacement works in
  `pending`.
- **Host listening (stage 1):** normal replacement of an accepted client.
- **Host in match (stage 2):** guest's connect fails with "already in a match".
- **Host idle/stopped (stage 3):** guest's connect fails with "not accepting players".
- **Two tabs share a client id** (duplicated tab): they will replace each other. Document;
  `sessionStorage` is per tab except when a tab is duplicated.
- **Spoofed client id:** any peer in the room can evict another by claiming its id. The room
  code is the only access control; no worse than today. A room password is future work.
- **Old build (hello v1):** invalid; both pages must load the same build.
- **Host refresh mid-match:** old guests see the old host leave; no automatic migration.
- **Stale Trystero peer** that has not fired `onPeerLeave`: replacement still closes the
  old channels, which sends EOF and frees the engine slot.

## 10. Testing

1. **JS transport replacement** (extend `scripts/nettest_js.py`): host + client; client
   connects with id A; a second client page with the same id A connects; host ends with one
   active client, old accepted fd sees EOF, new fd exchanges bytes.
2. **Refresh/rejoin end-to-end** (extend `scripts/netplaytest.py`): host waits; guest joins;
   reload the guest page; click **Rejoin**; choose a player and Connect; host sees the old
   client disconnect and the new client accepted; start the match and assert ctl/act
   traffic. Assert the host ends with one client, not two.
3. **Mid-match refresh** (second netplay scenario): start a match; reload the guest; click
   **Rejoin**; assert the guest's `connectError` mentions "already in a match" and the engine
   returns to the join menu within a few seconds, not a hang.
4. **Regression:** the existing basic/multi/wrong-room transport tests and solo playtest.

The netplay tests need internet (public Nostr relays) and the existing
`--disable-features=WebRtcHideLocalIpsWithMdns` flag.

## 11. Files

- `web/net.js`: hello v2, client id, replacement, host stage/status, `connectState` error.
- `web/index.html`: `sessionStorage` rejoin banner, clear on Leave/Solo, status display.
- `scripts/nettest_js.py`: replacement scenario.
- `scripts/netplaytest.py`: refresh/rejoin and mid-match scenarios.
- `PROGRESS.md` / `AGENTS.md`: mid-match resume todo, slice notes.
- No engine files.

## 12. Risks

- The host can briefly have two client slots while the old stream EOF is processed. The
  engine supports it; the UI settles. The test waits for one active client.
- A guest that refreshes at the exact moment the host starts may see stage 1, connect, and
  then the match starts; the guest is in the wait screen and receives config. The stage
  status is advisory, not a lock.
- `sessionStorage` duplication and spoofing are documented limitations.
- The host stage is a JS heuristic (accepted peers open when listen closes); a cancel can
  briefly report `match` before settling to `idle`. The guest sees a clear error either way.

## 13. Process

Implement inline; use a subagent only if a problem genuinely needs independent eyes, and
then on DeepSeek 4.1 Flash. Keep one commit per logical change; every commit carries the
attribution trailer. Update `PROGRESS.md` and `AGENTS.md` when the slice lands.

## 14. Left to the builder

- Exact hello byte layout helpers and client-id encoding.
- Exact stage update points in `listen`/`close`/`accept`/peer-leave.
- Exact rejoin banner wording/layout.
- Test wait/retry details and whether the mid-match scenario can reuse the netplay harness
  or needs a small second script.
