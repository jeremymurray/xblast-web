# Security

xblast-web is a **fun side project**, not a supported product. There is no
security team, no bounty and no promise that a report will be fixed. Reports are
read on a best-effort basis.

**Please do not post exploit details in a public issue or discussion.** If the
repository has GitHub private security advisories enabled, use
**Security → Report a vulnerability**; otherwise contact the maintainer through
the address on the repository profile.

Useful reports include the version or commit, browser and OS, build target, steps
to reproduce, whether the host or a guest page is involved, and the impact.

## What matters

There is no backend and no accounts. Relevant areas:

- **Cross-site scripting** in room codes, player names, chat, or any peer-supplied
  value that reaches the DOM in `web/index.html` / `web/net.js`.
- **Malicious peer input**: crafted control/action data, level names or chat;
  memory-safety problems in the C engine; a remotely triggerable crash.
- **Transport and signalling**: peer impersonation, room takeover, bypassing the
  host's slot/stage checks, or credential handling in `web/net.js`, `web/turn.js`
  and the vendored Trystero code.
- **Supply chain**: the build script, vendored JavaScript, or an artifact that
  contains unintended files or credentials.

Cheating in a casual match (the host is authoritative by design), a host tab
deliberately left in the background, public Nostr relay outages, and missing TURN
are not security issues; they are documented behaviour or deployment choices.

## Secrets

The repository must contain no TURN credentials, tokens or private keys.
`web/turn.json` is gitignored and local; a static credential in it is public to
every player and must be quota-limited and rotated. Player-supplied TURN
credentials live in `sessionStorage` only and are never broadcast. Do not paste
real credentials into reports, commits or logs.
