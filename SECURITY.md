# Security policy

## Supported versions

Security fixes target the latest tagged release and `main`. Older tags are kept
for provenance but are not actively patched.

| Version | Supported |
|---|---|
| 0.4.x | yes |
| ≤ 0.3.x | no |

## Reporting a vulnerability

Please **do not open a public issue** for a suspected vulnerability. Once the
repository is public, use GitHub's private security advisory
("Report a vulnerability" on the Security tab) or contact the maintainer listed
in the repository profile. Include:

- the affected version or commit and build target,
- browser and OS,
- steps to reproduce, and whether the host or a guest page is involved,
- impact (data exposure, code execution, denial of service, player impersonation),
- any logs or a minimal HTML/JS proof of concept.

There is no bug bounty. Reports are handled on a best-effort basis; expect an
initial acknowledgement within a week.

## What is in scope

xblast-web has no backend and no accounts. Relevant areas:

- **Cross-site scripting** in room codes, player names, chat, or any value that
  reaches the DOM in `web/index.html` / `web/net.js`.
- **Malicious peer input**: a room peer sends crafted control/action data, level
  names, or chat; memory-safety issues in the C engine, or a crash that can be
  triggered remotely.
- **Transport and signalling**: peer impersonation, room takeover, bypassing the
  host's slot/stage checks, credential or SDP handling in `web/net.js`,
  `web/turn.js` and the vendored Trystero code.
- **Build and supply chain**: the build script, vendored JavaScript, or the
  release artifact containing unintended files (`turn.json`, local config,
  credentials).

Out of scope: cheating in a casual peer-to-peer match where the host is
authoritative by design; denial of service caused by a player deliberately
backgrounding the host tab; public Nostr relay outages; and the absence of TURN
(NAT traversal is a deployment choice, documented in `docs/hosting.md`).

## Secrets and credentials

- The repository must contain no TURN credentials, tokens or private keys.
  `web/turn.json` is gitignored and local; a static `turn.json` credential is by
  nature public to every player and must be quota-limited and rotated.
- Player-supplied TURN credentials live in `sessionStorage` only and are never
  broadcast. A build must not include a deployer's real `turn.json`.
- Do not paste real credentials into issues, pull requests or logs.
