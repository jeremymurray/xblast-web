# Hosting XBlast TNT

The game is a static bundle. Hosting the game itself never requires a game server:
publish `web/dist/` over HTTPS and players connect browser-to-browser with WebRTC.
Signalling uses public Nostr relays.

TURN is a separate, optional relay. It is needed only when a host/guest pair cannot
connect directly because of symmetric NAT, carrier-grade NAT or a restrictive firewall.
A TURN server forwards encrypted WebRTC packets; it does not run game logic, see game
state, or replace the host.

The project's own deployment runs **no TURN** and **no credential service**. The profiles
below are for people hosting their own copy or supplying their own relay.

## Profile 0 — no TURN (default)

1. Build and publish the static files:

   ```sh
   ./scripts/build-web.sh
   # publish web/dist/ to GitHub Pages, Cloudflare Pages, Netlify, S3, or any HTTPS host
   ```

2. Do not add `turn.json`.

Most home networks connect. A player behind a restrictive NAT may not; the options are
to host a copy with TURN (Profiles 1-2) or to use the player-supplied TURN panel
(Profile 3).

## Profile 1 — a static TURN credential

Use this when you run or rent a TURN relay and accept that the credential is visible to
every player. It is suitable for friends and small trusted groups. Use a dedicated
credential with quotas and rotate it.

Put `turn.json` next to `index.html` in the published bundle:

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

`web/turn.example.json` is a copy of this shape. If you build from this repository, put
the real file at `web/turn.json` before running `scripts/build-web.sh`; the build copies
it into `web/dist/`. The real file is gitignored.

Multiple transports can share one credential:

```json
{
  "urls": [
    "turn:turn.example.org:3478?transport=udp",
    "turn:turn.example.org:3478?transport=tcp",
    "turns:turn.example.org:5349?transport=tcp"
  ],
  "username": "xblast",
  "credential": "replace-me"
}
```

### Managed TURN

Create a TURN app/credential in the provider's dashboard, apply a bandwidth quota, and
copy the URL and credential into `turn.json`. Some providers only issue short-lived
credentials through an API; use Profile 2 for those.

### coturn

A small VPS is enough. Checklist:

- Public IPv4 address and DNS, e.g. `turn.example.org`.
- Open ports: `3478/udp`, `3478/tcp`, `5349/udp`, `5349/tcp`, the UDP relay range
  (for example `49160-49200/udp`), and `80/tcp` for ACME certificate issuance.
- TLS certificate for `turn.example.org`; use `turns:` on 5349 so restrictive networks
  can fall back to TLS.
- A coturn config covering `realm`, `external-ip`, `fingerprint`, `lt-cred-mech`, the
  relay port range, quotas and private-range denials.

Example static-user configuration (choose either `user=` or the REST settings below,
not both):

```ini
listening-port=3478
tls-listening-port=5349
fingerprint
lt-cred-mech
realm=turn.example.org
server-name=turn.example.org
external-ip=203.0.113.10

min-port=49160
max-port=49200
no-cli
no-multicast-peers
denied-peer-ip=10.0.0.0-10.255.255.255
denied-peer-ip=172.16.0.0-172.31.255.255
denied-peer-ip=192.168.0.0-192.168.255.255
denied-peer-ip=127.0.0.0-127.255.255.255
denied-peer-ip=::1

# static credential mode
user=xblast:replace-me

# or REST credential mode (Profile 2)
# use-auth-secret
# static-auth-secret=replace-with-a-long-random-secret

cert=/etc/letsencrypt/live/turn.example.org/fullchain.pem
pkey=/etc/letsencrypt/live/turn.example.org/privkey.pem

# optional abuse limits
user-quota=12
total-quota=1200
max-bps=1000000
```

Keep coturn patched, monitor allocations and bandwidth, and do not run an open relay.

## Profile 2 — a public TURN credential endpoint

This is the public-friendly shape. The TURN shared secret stays on a small credential
service; the browser receives a short-lived credential.

`turn.json` points at the service:

```json
{
  "credentialsUrl": "https://turn.example.com/credentials"
}
```

The endpoint returns the same shape as the file (a single ICE-server object is also
accepted):

```json
{
  "turnConfig": [
    {
      "urls": ["turns:turn.example.org:5349?transport=tcp"],
      "username": "1750000000:xblast",
      "credential": "base64-hmac"
    }
  ]
}
```

### coturn REST credentials

With `use-auth-secret`, coturn expects a TURN REST credential:

```text
username   = "<unix-expiry>:<id>"
credential = base64(HMAC-SHA1(shared-secret, username))
```

Use a TTL that covers a whole match. This slice does not refresh credentials mid-match;
a ten-minute credential can expire during a long game. Four hours is a reasonable bound
for a session. The endpoint should also rate-limit requests and allow only your game
origin via CORS.

A minimal Cloudflare Worker shape:

```js
export default {
  async fetch(request, env) {
    if (request.headers.get('Origin') !== env.ALLOWED_ORIGIN) {
      return new Response('', { status: 403 });
    }
    const username = `${Math.floor(Date.now() / 1000) + 4 * 60 * 60}:xblast`;
    const key = await crypto.subtle.importKey(
      'raw', new TextEncoder().encode(env.TURN_SECRET),
      { name: 'HMAC', hash: 'SHA-1' }, false, ['sign']);
    const signature = await crypto.subtle.sign(
      'HMAC', key, new TextEncoder().encode(username));
    const credential = btoa(String.fromCharCode(...new Uint8Array(signature)));
    return Response.json({
      turnConfig: [{
        urls: ['turns:turn.example.org:5349?transport=tcp'],
        username,
        credential,
      }],
    }, {
      headers: { 'Access-Control-Allow-Origin': env.ALLOWED_ORIGIN },
    });
  },
};
```

Store `TURN_SECRET` and `ALLOWED_ORIGIN` as worker secrets/environment variables, never
in the static site. CORS and an origin check discourage casual misuse; they do not stop
non-browser clients. The real limits are short-lived credentials, quotas and rate limits.

## Profile 3 — player-supplied TURN

Any player can open **Advanced: TURN** in the lobby and enter a TURN URL, username and
credential before clicking Host or Join. This works on the project's static deployment
too.

- The values are stored in `sessionStorage` for that tab and are never sent to the host,
  another guest, the room, or the logs.
- They apply only to that player's WebRTC connections.
- A valid override replaces the deployer's TURN list for that browser; the default STUN
  servers remain.
- One side using a relay can rescue a connection where the other side is restricted. If
  both sides are badly restricted, both may need TURN.
- Use a relay you trust. A relay operator can see the IP addresses and traffic volume of
  the peers on that connection, though DTLS protects the game data itself.

## Verify a relay

In Chrome, open `chrome://webrtc-internals` during a match and inspect the selected
candidate pair. A relayed connection reports `localCandidateType` or
`remoteCandidateType` as `relay`.

For coturn, a direct check:

```sh
turnutils_uclient -u xblast -w replace-me turn.example.org
```

Check the credential endpoint separately:

```sh
curl -i -H 'Origin: https://your.game.origin' https://turn.example.com/credentials
```

The response must be JSON, carry CORS headers for your game origin, and contain a
`turnConfig` array.

## Caveats

- TURN bandwidth is paid for by the relay operator. Game traffic is small, but an open
  relay can be abused; use quotas and short-lived credentials.
- A static `turn.json` credential is public. Rotate it and cap its quotas.
- A missing `turn.json` is normal; the client proceeds with STUN only.
- The project does not run a TURN service or a credential endpoint for its own deployment.
