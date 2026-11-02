# Invite links — design

Date: 2026-11-01
Status: approved 2026-11-01
Scope: small change (lobby only, no engine change)

## Intent

A host or participant can copy a URL that opens the game with the room code
already filled in and a Join prompt, so a newcomer does not have to be told the
code and type it. There is still no game browser or lobby list; the room code
remains the only identifier.

This covers joining a room whose host is **waiting** (the room is in its
listening/setup stage). Joining after a match starts is unchanged: the host
refuses it with the existing message. Mid-match join/resume is not in scope.

## Goals

- A **Copy invite link** action in the netbar, available to both host and guest.
- Opening `?room=<code>` prefills the room field and shows an invite prompt.
- One click joins; the visitor is never connected automatically.
- Works from GitHub Pages subpaths and custom hosts, and on mobile.
- No new dependencies.

## Non-goals

- Auto-join on page load.
- A lobby list, room discovery, spectator or mid-match join.
- Short links or a URL shortener service.
- Changing room-code generation or host authority.

## Behaviour

### URL

- Format: the current page URL with `room=<normalized-code>` in the query string,
  e.g. `https://jeremymurray.github.io/xblast-web/?room=quiet-otter-482`.
- The path (including a Pages subpath) and any other query parameters are kept;
  an existing `room` value is replaced. The hash is dropped.
- `normalizeRoom()` is applied; an empty or unusable value is ignored.

### On load with `?room=`

1. Normalize and validate the code. If invalid, ignore it and continue with the
   normal lobby (last-room banner or a fresh code).
2. Fill the room field and show an invite banner inside the landing panel:
   `You've been invited to room <code>` with a **Join** button. The code is set
   with `textContent`, never HTML.
3. The invite banner takes priority over the last-room/rejoin banner for that
   load; the last-room record is not deleted.
4. Consume the parameter with `history.replaceState`, so a later reload behaves
   normally and a copied invite link is always generated from the clean URL.
5. **Join** runs the existing `startNet('client')`. Starting Solo or Host, or
   leaving the lobby, hides the invite banner. No auto-connect.

### Netbar

- Keep the existing room-code **Copy** action, relabel it **Copy code** for
  clarity, and add **Invite** with `title`/`aria-label` "Copy invite link".
  Both are visible to host and guest (the netbar only exists once in a room).
- The invite action builds the absolute URL from `location.href` + `room`, then
  copies it with `navigator.clipboard.writeText()`. If that fails, fall back to a
  temporary textarea + `document.execCommand('copy')`; if both fail, show the URL
  in the existing notice so it can be copied by hand.
- Success notice: `Invite link copied.` The code never contains credentials.

### Errors and limits

- No host listening, room full, or host in a match: the existing client-connect
  errors and timeout messages apply unchanged.
- The link is a room code, not an authorization token; anyone with it can try to
  join while the host is waiting.

## Implementation sketch

- `web/index.html`: invite banner markup and styles; URL parse/consume on load;
  `inviteUrlFor(room)` helper; netbar button and clipboard fallback.
- `scripts/nettest_js.py`: extend the `roomcode` scenario with pure checks for
  `inviteUrlFor()` and a page loaded with `?room=` to assert the field, banner,
  and consumed query string.
- README/PROGRESS: mention the invite link briefly.

## Approaches considered

1. **Auto-join (`?join=`)** — fastest, but connects without confirmation, makes a
   host opening their own link join as a guest, and skips TURN setup.
2. **Prefill + confirm (`?room=`)** — chosen: one extra click, safe for hosts,
   keeps errors and TURN in the lobby.
3. **Copy-only, no URL prefill** — dropped; the recipient still types the code.

## Open questions

None; button placement, both roles, and prefill-with-confirmation were decided in
the design conversation.
