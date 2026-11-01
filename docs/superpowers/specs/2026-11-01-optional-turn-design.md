# Optional TURN relay — short design

Date: 2026-11-01
Status: approved 2026-11-01
Scope: M3 slice — optional TURN with static, endpoint or player-supplied credentials
Related: `docs/superpowers/specs/2026-10-31-m2-p2p-design.md`,
`docs/superpowers/specs/2026-11-01-six-players-design.md`

## 1. Intent

Some host/guest pairs cannot connect with STUN alone: symmetric NAT, carrier-grade NAT, or a
firewall that refuses inbound UDP. TURN fixes that by relaying the encrypted WebRTC packets
through a server with a public address.

The project has no game backend and must stay deployable as plain static files. This slice adds
TURN as an **optional component** with three credential modes:

- **static** — a TURN URL and credential in `turn.json`, for hosters who run or rent a relay and
  accept that the credential is public;
- **endpoint** — a `credentialsUrl` in `turn.json` pointing at a small credential-minting
  service, for public deployments that need short-lived credentials;
- **player-supplied** — an advanced lobby panel where a player enters their own relay for this
  browser only, without changing the deployed site.

A deployment with no TURN configuration behaves exactly as today. The project ships no
credentials, no provider choice and no relay of its own. TURN is optional infrastructure for the
peers that need it, not a change to the game architecture.

The project's own deployment stays at **Tier 0**: static files, no TURN service and no
credential endpoint. A player who cannot connect has two supported answers:

1. **Host your own copy** — publish the static files somewhere and run a TURN relay (coturn or
   managed). This is the recommended path and is documented as a hosting profile. It is not a
   game server; the game remains peer-to-peer.
2. **Bring your own TURN** — enter a TURN URL and credentials in the lobby of an existing
   deployment, including the project's static one. This is a local, advanced option.

The project does not run infrastructure to rescue either case. The self-hosted copy is the
normal answer; the player-side override is the escape hatch when the player has a relay but the
site owner does not.

## 2. What already exists

- `web/net.js` calls `joinRoom({ appId: APP_ID }, room, callbacks)`. Trystero builds one
  `RTCPeerConnection` per peer and already accepts `turnConfig` in that config map
  (`web/vendor/trystero/core/peer.mjs`), appending it to the default Google/Cloudflare STUN
  servers.
- `web/net.js` already has `configure({ connectTimeoutMs })` and a `status()` surface used by
  the lobby and the JS test harness.
- The build is a static bundle (`web/dist/`); `web/index.html` is copied by
  `scripts/build-web.sh`. There is no runtime server-side code in the default path.
- The README currently states that relay mode is not wired up.

## 3. Goals

1. With no `turn.json`, multiplayer works exactly as it does now: at most one same-origin
   request that may 404, and no new failure mode.
2. A deployer can add `turn.json` beside `index.html` without rebuilding the engine.
3. A deployer with a credential endpoint can point `turn.json` at it and receive short-lived
   credentials at room join.
4. A malformed file, failed endpoint or unreachable relay never stops the lobby or the game; the
   page logs a clear warning and continues with STUN only.
5. A host or guest can see whether TURN is configured (count and source, not credentials)
   through `XBNet.status()` and a one-time console line.
6. A player can enter their own TURN URL and credentials in the lobby, before Host/Join, and
   use them for that browser only, on any deployment including the project's static one.
7. The existing netplay and transport tests pass unchanged without TURN.

## 4. Non-goals

- Running, paying for or recommending a TURN provider or relay. Examples in the docs are
  illustrative, not endorsements.
- Hosting the credential endpoint as part of this project. The client supports the endpoint
  shape; the hoster deploys it.
- Automatically discovering a TURN provider, testing a player's relay from the lobby, or
  storing player credentials beyond the tab.
- Forcing relay mode (`iceTransportPolicy: 'relay'`) in normal play. Direct ICE remains
  preferred.
- Refreshing credentials mid-match or doing an ICE restart.
- TURN for signalling. Nostr relays still carry only SDP/ICE.
- Guaranteeing connectivity for every NAT pair. Without a configured relay, the current
  limitation remains.

## 5. Approaches

**A. Runtime `turn.json` with static credentials.** A small JSON file beside `index.html` is
fetched, validated and passed to `XBNet.configure({ turnConfig })` before the room is joined.
Smallest possible seam, no backend, but the credential is public.

**B. Runtime `turn.json` with a `credentialsUrl`.** The same file points at a credential
endpoint; the page fetches short-lived credentials at room join. The endpoint holds the TURN
secret (or provider API key) and never exposes it. This is the only mode suitable for anonymous
public players.

**C. Player-supplied TURN in the lobby.** A small advanced panel in the landing lobby takes a
TURN URL and credentials, applies them to this browser only, and never shares them. It works on
any deployment, including the project's static one. Adds a UI, local storage and validation, but
no server and no shared secret.

**D. Build-time environment variable.** Requires a rebuild, puts credentials in build scripts or
generated output, and makes a static deployment harder to change. Rejected.

**E. Bake in a public relay.** Zero setup, but shared, abusable and likely to disappear.
Rejected as a project default.

A, B and C are supported. Static is the low-effort hoster path; endpoint is the public hoster
path; player-supplied is the escape hatch when the player has a relay and the hoster does not.
If `turn.json` has both A and B, the endpoint wins and the static list is the fallback when it
fails. A valid player override replaces the deployer's TURN list for that browser; the default
STUN servers remain.

## 6. Behaviour

### `turn.json`

`turn.json` sits next to `index.html` in the deployed bundle. Either form is valid:

```json
{
  "turnConfig": [
    {
      "urls": ["turn:turn.example.org:3478?transport=udp"],
      "username": "xblast",
      "credential": "replace-me"
    }
  ]
}
```

```json
{
  "credentialsUrl": "https://turn.example.com/credentials"
}
```

Both may appear; the endpoint is preferred and the static list is the fallback.

- `turnConfig` is an array of ICE-server objects; `urls` may be a string or an array.
- Ports are optional: `turn:` defaults to 3478 and `turns:` to 5349 (RFC 7065). A URL with no
  host, an embedded userinfo part or an out-of-range port is rejected.
- `username` and `credential` are passed through unchanged.
- Only `turnConfig` and `credentialsUrl` are accepted. Arbitrary `rtcConfig` is not, so a config
  file cannot silently replace STUN or set a relay-only policy.
- An empty array, an absent file or an absent endpoint means “no TURN”.

### Credential endpoint contract

The endpoint returns the same shape as the file:

```json
{
  "turnConfig": [
    {
      "urls": ["turns:turn.example.com:5349?transport=tcp"],
      "username": "1750000000:xblast",
      "credential": "base64-hmac"
    }
  ]
}
```

The client validates it with the same rule as a static list. A single ICE-server object
(`{ "urls": ..., "username": ..., "credential": ... }`) is also accepted and wrapped, so a small
worker can be simple.

The endpoint must:

- allow the game origin via CORS (the browser fetches it cross-origin);
- hold the TURN shared secret or provider API key server-side;
- issue credentials whose lifetime covers a whole match, because this slice does not refresh
  them. A ten-minute credential can expire during a long game; use a bounded but generous TTL
  (e.g. four hours) and rate-limit the endpoint;
- use HTTPS.

CORS and an origin check discourage casual misuse; they do not stop non-browser clients. The
real limits are short-lived credentials, provider quotas and rate limiting.

### Loading and precedence

- `web/index.html` loads `./turn.json` with `cache: 'no-cache'` at page load. A 404, network
  error or invalid JSON logs one informational/warning line and resolves to “no TURN”. It never
  blocks the lobby.
- At **room join**, `startNet()` asks the helper for the effective TURN list:
  - a valid player override from the lobby wins immediately; no file or endpoint fetch;
  - otherwise, if `turn.json` has a `credentialsUrl`, fetch it fresh with `cache: 'no-store'`, a
    short timeout and `mode: 'cors'`;
  - if that fails, use a static `turnConfig` from the same file, if present;
  - otherwise return an empty list.
- The result is passed to `XBNet.configure({ turnConfig })` before `XBNet.enter()`.
- `XBNet.configure()` validates the list: it keeps only entries with a non-empty `urls` whose
  scheme is `turn:` or `turns:`, and ignores malformed entries with a warning. Calling
  `configure()` again replaces the previous list.
- `enter()` passes `turnConfig` in the `joinRoom` config map only when the list is non-empty, so
  the no-TURN path sends exactly the same config as today.

### Visibility

- `XBNet.status()` gains `turnConfigured: boolean`, `turnServers: number` and
  `turnSource: 'file' | 'endpoint' | 'player' | null`. It never exposes `username` or
  `credential`.
- On a successful load, the page logs `xb: TURN configured (N server(s), source)` once.
- No netbar text is added in this slice: “configured” does not prove the relay is reachable, and
  a misleading indicator is worse than none. A later UI can show candidate types from
  `getStats()`.

### Player-supplied TURN

The landing lobby gets a collapsed **Advanced: TURN** panel below the Host/Join buttons:

- Fields: TURN URL(s), username, credential. The URL field accepts one or more
  comma/whitespace-separated `turn:`/`turns:` URLs for one credential.
- Help text: “Only needed if you cannot connect. Use a relay you trust. Hosting your own copy
  with TURN is the recommended fix; this is for advanced users.”
- A “Forget” button clears the fields and the stored value.
- The panel is only used before Host/Join. Changing it after a room is joined requires Leave or
  reload; the UI does not hot-apply it to an existing peer connection.

Storage and precedence:

- The values live in `sessionStorage` only (per tab). Closing the tab clears them. They are not
  written to `localStorage`, the room, the engine config or the control channel.
- At Host/Join, a valid player override is used **instead of** the deployer's TURN list; the
  default STUN servers remain. This makes the player's explicit choice predictable and avoids
  mixing an unknown shared credential with their own.
- Invalid input is shown inline and is not applied. The first Host/Join click is refused: the
  landing stays visible, the panel opens and the player corrects the fields or presses Forget.
  A retry with cleared or valid fields proceeds. This keeps a typo from silently starting the
  room without the relay the player asked for; the lobby itself remains usable.
- If the player override is present, the page does not fetch `credentialsUrl`.
- `turnSource` is `'player'` when the override is in use.

Security handling:

- Accept only `turn:`/`turns:` URLs with a hostname; reject everything else. Do not accept
  arbitrary `rtcConfig`, `stun:` replacement, or an `iceTransportPolicy`.
- Never log or render the credential in the netbar, status, errors or page text. Use a password
  input; do not put values in a URL query, and do not autocomplete them.
- The values are local to the page and go only to the TURN server the player names. They are
  never sent to the host or other guests, so there is no shared secret to abuse and no new
  project infrastructure.
- The TURN operator can see the IPs, ports and traffic volume of the peers on that connection;
  it cannot read DTLS-protected game traffic or impersonate a peer without also breaking
  signalling. The UI/README should say “use a relay you trust.”
- A relay on one side may rescue a connection where the other side is restricted. If both sides
  are badly restricted, both may need TURN; the help text should not promise a universal fix.

## 7. Hosting profiles

The README/hosting guide gets an “I want to host this” section with four profiles:

1. **No TURN (default, and the project's own deployment).** Static files plus HTTPS. No extra
   process. Some NAT pairs cannot connect.
2. **Self-hosted copy with static TURN.** The player/hoster publishes the static files on any
   HTTPS host and runs coturn or a managed TURN service, creates a credential with quotas, and
   puts it in `turn.json`. This is the recommended answer for “I can't connect”: host your own
   copy with a relay. It is not a game server; the game remains peer-to-peer.
3. **Self-hosted copy with public TURN.** The same, but coturn uses a REST shared secret and the
   hoster deploys a small credential worker (Cloudflare Workers, Netlify/Vercel function, Deno
   Deploy, Lambda) that returns short-lived credentials. `turn.json` contains
   `credentialsUrl`.
4. **Player-supplied TURN.** A player on any deployment, including the project's static one,
   enters their own relay in the lobby. No hosting changes, no shared credential, advanced
   users only. This is the escape hatch, not the primary recommendation.

For coturn, the documented checklist covers: a public VPS, DNS, ports 3478/5349 UDP+TCP and a
relay range, TLS for `turns:`, a realm, `external-ip`, quotas, private-range denials, and the
credential mode. For managed TURN, the checklist covers creating the app/credential, quotas,
TLS-capable URLs, and the provider's credential API. The guide also repeats that the browser
sends TURN credentials to the relay, so a static credential is public and must be quota-limited
and rotated.

## 8. Deployment and files

- `web/turn.example.json` (static) and `web/turn.example.endpoint.json` are committed with
  placeholders.
- A real `web/turn.json` is gitignored. `scripts/build-web.sh` copies it and the TURN helper into
  `web/dist/` when present. For a host that publishes `web/dist/` directly, the file can simply
  be placed there.
- `web/turn.js` is a small ES module with the loader/validator and the player-override
  validation/storage helpers. Keeping it separate makes the file, endpoint and player paths
  testable without a browser lobby.
- `web/index.html` adds the **Advanced: TURN** panel, imports the helper at Host/Join and passes
  the effective list to `XBNet.configure`.
- `web/net.js` gains `turnConfig` in `configure`, the `joinRoom` merge and the `status()` fields.
- `scripts/build-web.sh` copies `web/turn.js` and an optional `web/turn.json`.
- `README.md` or `docs/hosting.md`, `PROGRESS.md`, `AGENTS.md` record the optional TURN decision,
  hosting profiles, schema, credential warning and test note.

Static credentials in a public file are visible to every player. The README must say so: use a
dedicated credential with quotas, rotate it, and prefer the endpoint mode for public play.

## 9. Tests

- **`nettest_js.py` `turn-config` scenario** (no network, no relay):
  - `XBNet.configure({ turnConfig })` accepts a valid list and `status()` reports count/source;
  - malformed entries are dropped;
  - `configure({ turnConfig: [] })` clears it;
  - `web/turn.js` handles an absent file, a static file, an endpoint response, a malformed
    file, a failed endpoint with static fallback, and a failed endpoint with no fallback, using
    an injected `fetchImpl`;
  - a player override validates, is stored only in `sessionStorage`, takes precedence over the
    file/endpoint, is not logged in `status()`, and a malformed override is rejected without
    blocking the lobby;
  - “Forget” clears both the fields and the stored value.
- **Existing scenarios:** `basic`, `wrong-room`, `multi`, `replace`, `full` and the netplay
  scenarios run with no `turn.json` and must be unchanged.
- **Malformed file:** a temporary invalid `turn.json` leaves the lobby usable and logs a
  warning.
- **Manual relay check (documented, not default):** run a local coturn, deploy a `turn.json`,
  and confirm a selected candidate pair reports `localCandidateType === "relay"` in
  `chrome://webrtc-internals`. Do not add coturn to the default test dependencies.

## 10. Risks

- **Public static credentials.** A static file cannot hide them; anyone can use the relay.
  Mitigate with a dedicated credential, quotas and rotation; the endpoint mode is the answer for
  public play.
- **Endpoint availability.** If the credential service is down, TURN is unavailable; the client
  falls back to static credentials or STUN-only and continues. The endpoint is an optional
  dependency, like the public Nostr relays.
- **Credential lifetime.** No mid-match refresh in this slice. The endpoint must issue
  credentials that outlive a match; document the TTL and the limitation.
- **Cost and latency.** Relayed traffic is billed by the relay operator and adds a hop. Only
  peers that fail direct ICE use it; game traffic itself is low-bandwidth.
- **A bad file or endpoint must not break play.** Validation and the no-TURN fallback are part
  of the contract, not an afterthought.
- **Caching.** `no-cache` for the file and `no-store` for credentials avoid stale configuration.
- **Player-supplied relay trust.** A player choosing a malicious relay exposes their connection
  metadata and can have that connection dropped; DTLS still protects content. Document “use a
  relay you trust” and prefer `turns:`.
- **Local credential handling.** Player credentials live in `sessionStorage`; any script on the
  origin can read them. Keep them out of logs, status, URLs and HTML, use a password field, and
  clear them on “Forget”.
- **One-sided relay is not universal.** A player's relay may rescue a connection with a
  restricted host, but if both sides are badly restricted both may need TURN. Do not promise a
  fix in the UI.
- **No default test proves a real relay path.** The suite proves wiring and validation; the relay
  check is manual and documented.

## 11. Decisions taken here

- Support static `turnConfig`, `credentialsUrl` and a player-supplied override; default
  deployment and tests stay TURN-free.
- The project's own deployment stays Tier 0: no TURN service and no credential endpoint. TURN
  support is for third-party hosters, self-deployed copies and players with their own relay.
- “Host your own copy with TURN” is the primary answer for a player who cannot connect;
  player-supplied TURN is the optional escape hatch on an existing deployment.
- The project does not host or ship a credential service; it defines the contract and documents
  a reference worker shape.
- Player credentials are local, session-scoped and never shared; they replace the deployer's
  TURN list for that browser.
- Only `turnConfig`/`credentialsUrl`/player fields are accepted; no arbitrary RTC configuration.
- Endpoint credentials are preferred over static ones when both are configured.
- No netbar indicator in this slice; expose configured count/source through `status()` and the
  console.

## 12. Left to the builder

- Exact `web/turn.js` API and whether it takes an injected `fetchImpl` or a small adapter.
- Validation details: drop malformed entries individually or reject the whole list.
- Endpoint timeout value and whether a failed endpoint is retried on the next join.
- Whether the endpoint response accepts only `turnConfig` or also a bare ICE-server object.
- Exact `nettest_js` scenario shape and whether it exercises the file loader separately from the
  endpoint loader.
- Exact player-panel wording, field limits and whether the override is stored as one ICE-server
  entry with multiple URLs or as a small JSON blob.
- Whether the hosting guide lives in `README.md` or a separate `docs/hosting.md`.
