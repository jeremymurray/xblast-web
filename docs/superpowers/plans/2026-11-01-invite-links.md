# Invite Links Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a copyable invite URL that opens the lobby with a room code prefilled and a one-click Join prompt, for both hosts and guests.

**Architecture:** All work is in the `web/index.html` page script and the existing headless-browser test harness. A URL helper builds `?room=<normalized>` links; a load-time reader consumes the parameter, fills the room field and shows an invite banner inside the landing panel. A netbar button copies the link. Nothing connects automatically, and the engine/netcode are untouched.

**Tech Stack:** Vanilla browser JavaScript in `web/index.html`, Python CDP test harness in `scripts/nettest_js.py`.

**Spec:** `docs/superpowers/specs/2026-11-01-invite-link-design.md`

## Global Constraints

- No new dependencies or libraries.
- No auto-connect: opening an invite URL must not call `startNet` or import `net.js`.
- The room code is always normalized with the existing `normalizeRoom()` and inserted with `textContent`, never HTML.
- Preserve the current page path (GitHub Pages subpath) and other query parameters; the generated URL drops the hash.
- Host and guest both get the invite button; it lives in the existing `#netbar`.
- Mid-match join is unchanged: the host still rejects peers once the stage is `match`.
- Do not change `web/net.js`, the engine, room-code generation or host authority.

## Review Focus

- **Malformed/empty `?room=`** (spaces, punctuation, overlong): ignored, normal lobby appears, no crash or partial state.
- **Host opens their own invite link**: field prefilled and banner shown, but no client connection starts; Host still works.
- **Pages subpath and extra query params** (`/xblast-web/?foo=1&room=x`): invite URL keeps the path and unrelated params, replaces `room`, and drops the hash.
- **Clipboard unavailable or denied**: the user still gets the URL (execCommand fallback, then a visible notice), never a silent no-op.
- **Reload after opening an invite**: the parameter is consumed, so reload shows the normal rejoin/last-room state rather than re-offering the invite.

---

### Task 1: Invite URL helper, prefill banner and consume-on-load

**Files:**
- Modify: `web/index.html` (CSS near `#rejoin-banner`; markup before `#rejoin-banner`; script refs near line 248; helpers near `normalizeRoom`; init block near line 930; `startSolo`/`startNet`)
- Test: `scripts/nettest_js.py` (`run_roomcode`)

**Interfaces:**
- Produces: `inviteUrlFor(room: string): string` — absolute URL for a normalized room, `''` if the room is empty after normalization; preserves `location.pathname` and other query params, drops the hash.
- Produces: `readInviteRoom(): string` — reads `room` from `location.search`, normalizes it, removes only `room` with `history.replaceState`, returns the code or `''`.
- Produces: `showInviteBanner(code: string): void`, `hideInviteBanner(): void`.
- Produces DOM ids: `invite-banner`, `invite-room`, `invite-join`.
- Consumes: existing `normalizeRoom()`, `startNet('client')`, `readLastRoom()`, `showRejoinBanner()`, `makeCode()`.

- [ ] **Step 1: Write the failing test**

Add to `run_roomcode` in `scripts/nettest_js.py`, after the existing `normalizeRoom` check and before `finally`:

```python
        check(page.ev("inviteUrlFor(' Quiet Otter 482 ')") ==
              f"{base}/index.html?room=quiet-otter-482",
              "inviteUrlFor did not normalize/build the invite URL")
        check(page.ev("inviteUrlFor('')") == "",
              "inviteUrlFor accepted an empty room")
        check(page.ev("inviteUrlFor('<img src=x>')") ==
              f"{base}/index.html?room=img-src-x",
              "inviteUrlFor did not sanitize the room")
```

Append a second page to `run_roomcode` after the existing page is closed:

```python
    invite = Page(
        f"{base}/index.html?room=Quiet%20Otter%20482",
        wait_for="document.getElementById('invite-banner') && " +
                 "document.getElementById('invite-banner').classList.contains('show')")
    try:
        check(invite.ev("document.getElementById('room').value") == "quiet-otter-482",
              "invite did not prefill the room field")
        check(invite.ev("document.getElementById('invite-room').textContent") ==
              "quiet-otter-482", "invite banner shows the wrong room")
        check(invite.ev("location.search") == "",
              "invite parameter was not consumed")
        check(invite.ev("typeof XBNet === 'undefined'"),
              "opening an invite must not load net.js or connect")
    finally:
        invite.close()
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python3 scripts/nettest_js.py roomcode`
Expected: FAIL with `inviteUrlFor is not defined` (or the invite page times out because `#invite-banner` does not exist).

- [ ] **Step 3: Add the invite banner markup and styles**

In `web/index.html`, extend the existing banner CSS selectors so they cover both banners:

```css
  #rejoin-banner,
  #invite-banner {
    display: none; align-items: center; justify-content: space-between; gap: 1em;
    margin: 0 0 1em; padding: 0.7em 0.9em; border: 1px solid #555; border-radius: 6px;
    background: rgba(255, 212, 0, 0.08); color: #ddd; font-size: 13px;
  }
  #rejoin-banner.show,
  #invite-banner.show { display: flex; }
  #rejoin-banner button,
  #invite-banner button {
    margin: 0; padding: 0.45em 0.9em; font: 13px monospace; white-space: nowrap;
  }
```

Add this markup immediately before the existing `#rejoin-banner` element:

```html
    <div id="invite-banner">
      <span>You've been invited to room <span id="invite-room"></span></span>
      <button id="invite-join" type="button">Join</button>
    </div>
```

- [ ] **Step 4: Add refs, helpers and load-time handling**

Near the other element refs:

```js
  const inviteBannerEl = document.getElementById('invite-banner');
  const inviteRoomEl = document.getElementById('invite-room');
  const inviteJoinEl = document.getElementById('invite-join');
```

After `normalizeRoom`, add:

```js
  function inviteUrlFor(room) {
    const code = normalizeRoom(room);
    if (!code) return '';
    const url = new URL(location.href);
    url.searchParams.set('room', code);
    url.hash = '';
    return url.toString();
  }

  function readInviteRoom() {
    try {
      const params = new URLSearchParams(location.search);
      if (!params.has('room')) return '';
      const code = normalizeRoom(params.get('room'));
      params.delete('room');
      const query = params.toString();
      history.replaceState(null, '', location.pathname +
        (query ? '?' + query : '') + location.hash);
      return code;
    } catch (error) {
      return '';
    }
  }

  function hideInviteBanner() {
    inviteBannerEl.classList.remove('show');
  }

  function showInviteBanner(code) {
    inviteRoomEl.textContent = code;
    roomEl.value = code;
    inviteBannerEl.classList.add('show');
  }
```

In `hideRejoinBanner()`'s caller area, keep the two banners independent. In `startSolo()` and at the start of `startNet()`, call `hideInviteBanner()`. In the init block, replace:

```js
    const lastRoom = readLastRoom();
    if (lastRoom) showRejoinBanner(lastRoom);
    else roomEl.value = makeCode();
```

with:

```js
    const invitedRoom = readInviteRoom();
    const lastRoom = readLastRoom();
    if (invitedRoom) {
      hideRejoinBanner();
      showInviteBanner(invitedRoom);
    } else if (lastRoom) {
      showRejoinBanner(lastRoom);
    } else {
      roomEl.value = makeCode();
    }
```

Add the Join handler next to the other lobby handlers:

```js
  inviteJoinEl.addEventListener('click', () => startNet('client'));
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `python3 scripts/nettest_js.py roomcode`
Expected: PASS, including all `inviteUrlFor`, prefill, consumed-query and no-`XBNet` checks.

- [ ] **Step 6: Commit**

```bash
git add web/index.html scripts/nettest_js.py
git commit -s -m "lobby: prefill rooms from invite links

Read ?room=, normalize it, fill the room field and show an invite banner
with a Join button. Consume the parameter with replaceState and never
connect automatically.

Assisted-by: DeepSeek V4.1 Flash Free (opencode/deepseek-v4.1-flash-free)"
```

---

### Task 2: Netbar invite button and clipboard fallback

**Files:**
- Modify: `web/index.html` (netbar markup around line 210; refs near line 250; copy handler near line 1000)
- Modify: `README.md` (Play section)
- Modify: `PROGRESS.md` (M5/known features)
- Test: `scripts/nettest_js.py` (`run_roomcode`)

**Interfaces:**
- Consumes: `inviteUrlFor(room)` from Task 1.
- Produces: `copyText(text: string): Promise<boolean>` — tries `navigator.clipboard.writeText`, then a temporary textarea + `document.execCommand('copy')`, returns success.
- Produces DOM id `net-invite`.

- [ ] **Step 1: Write the failing test**

In `run_roomcode`, after the existing `normalizeRoom` check, add:

```python
        check(page.ev("document.getElementById('net-room').tagName") == "BUTTON",
              "room code should be a copy button")
        check(page.ev("document.getElementById('net-room').getAttribute('title')") ==
              "Copy room code", "room-code button needs a title")
        check(page.ev("document.getElementById('net-room').getAttribute('aria-label')") ==
              "Copy room code", "room-code button needs an accessible label")
        check(page.ev("document.getElementById('net-invite') !== null"),
              "invite button is missing from the netbar")
        check(page.ev("document.getElementById('net-invite').getAttribute('aria-label')") ==
              "Copy invite link", "invite button needs an accessible label")
        check(page.ev("typeof copyText === 'function'"),
              "copyText helper is missing")
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python3 scripts/nettest_js.py roomcode`
Expected: FAIL because `#net-room` is still a `<span>`.

- [ ] **Step 3: Add the netbar button and copy helper**

Change the netbar markup:

```html
  <button id="net-room" class="room" type="button" title="Copy room code"
          aria-label="Copy room code"></button>
  <button id="net-invite" type="button" title="Copy invite link"
          aria-label="Copy invite link">Invite</button>
```

Add a ref:

```js
  const netInviteEl = document.getElementById('net-invite');
```

Add the helper near the invite helpers:

```js
  async function copyText(text) {
    try {
      await navigator.clipboard.writeText(text);
      return true;
    } catch (error) {
      // fall through to the legacy path
    }
    try {
      const field = document.createElement('textarea');
      field.value = text;
      field.setAttribute('readonly', '');
      field.style.position = 'fixed';
      field.style.opacity = '0';
      document.body.appendChild(field);
      field.select();
      const ok = document.execCommand('copy');
      field.remove();
      return ok;
    } catch (error) {
      return false;
    }
  }
```

Replace the existing room-code copy handler with one on `netRoomEl` using `copyText(room)` and a "Room code copied." notice, keeping the fallback notice. Add:

```js
  netInviteEl.addEventListener('click', async () => {
    const room = globalThis.xbConfig && globalThis.xbConfig.room;
    const url = inviteUrlFor(room);
    if (!url) return;
    if (await copyText(url)) showNotice('Invite link copied.');
    else showNotice('Invite link: ' + url);
  });
```

- [ ] **Step 4: Update README and PROGRESS**

In `README.md` under **Play → Multiplayer**, add one sentence: the host or any guest can use **Invite** in the netbar to copy a link that opens the room prefilled for one-click joining.

In `PROGRESS.md`, add an M5 checklist line:

```markdown
- [x] Invite links: `?room=` prefills the lobby for host or guest; netbar **Invite** copies the URL
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `python3 scripts/nettest_js.py roomcode`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add web/index.html README.md PROGRESS.md scripts/nettest_js.py
git commit -s -m "lobby: copy invite links from the netbar

Add an Invite button for host and guest, with a clipboard fallback, and
document the pre-filled join flow.

Assisted-by: DeepSeek V4.1 Flash Free (opencode/deepseek-v4.1-flash-free)"
```

---

### Task 3: End-to-end verification and handoff

**Files:**
- Modify: `PROGRESS.md` (verification note / known issues if needed)

- [ ] **Step 1: Run the full transport suite**

Run: `python3 scripts/nettest_js.py`
Expected: `ALL PASS`. The public-relay `full` scenario may flake; rerun it once if the only failure is `full`.

- [ ] **Step 2: Manual two-browser invite check**

```sh
./scripts/build-web.sh --target release
python3 -m http.server -d web/dist 8123
```

In browser A: open `http://localhost:8123/`, click **Host**, then **Invite**; copy the URL.
In browser B: open the copied URL; confirm the room field is filled, the invite banner is visible, and the page has not started connecting. Click **Join**; confirm the host sees the guest and a match can start. Repeat with browser B copying the invite link as a guest.

- [ ] **Step 3: Check the mid-match refusal**

With a match running, open a fresh invite URL in browser C. Click **Join** and confirm the existing "host is already in a match" message appears (no new spectator path).

- [ ] **Step 4: Commit the verification note if anything changed**

If the manual check reveals no code change, no commit is needed; note the result in the final report and, only if useful, in `PROGRESS.md` known issues.

---

## Self-Review

- Spec coverage: URL format, prefill, banner, consume, both roles, no auto-connect, clipboard fallback, mid-match unchanged, tests and docs each map to Tasks 1–3.
- No new dependencies; only `web/index.html`, `scripts/nettest_js.py`, `README.md`, `PROGRESS.md`.
- Interfaces match: `inviteUrlFor`, `readInviteRoom`, `showInviteBanner`, `hideInviteBanner`, `copyText`, ids `invite-*` and `net-invite`.
- Review Focus items each have a test or a manual step: malformed and sanitized rooms (Task 1 tests), host/no-auto-connect (Task 1 test), extra params/subpath (Task 1 helper uses `URL`), reload consume (Task 1 test), clipboard fallback (Task 2 implementation + Task 3 manual).
