# Vendored Trystero P2P stack

These files are copied verbatim from npm tarballs so the static site can use
peer-to-peer signalling without npm at build time or a CDN at runtime.

| Package | Version | Licence |
|---|---|---|
| `@trystero-p2p/nostr` | 0.26.0 | MIT |
| `@trystero-p2p/core` | 0.26.0 | MIT |
| `@noble/secp256k1` | 3.2.0 | MIT |

Source tarballs (with verified sha256):

- `https://registry.npmjs.org/@trystero-p2p/nostr/-/nostr-0.26.0.tgz`
  - `8f0cd23847de6a1f29560a61233dc58d3ff73121783ddd31d7fcbca7c4e559a1`
- `https://registry.npmjs.org/@trystero-p2p/core/-/core-0.26.0.tgz`
  - `e74c5cbcd83c63bbfb08418a986fe08b98cb19a3e0002248586a91438c9c47d5`
- `https://registry.npmjs.org/@noble/secp256k1/-/secp256k1-3.2.0.tgz`
  - `2722e0b18b696cf6d3463ab10365f97f617fb651e85a7eeed8f12121a1077018`

The combined work is distributed under GPL-2.0-or-later; the vendored
packages keep their MIT licences in `LICENSE.trystero` and `LICENSE.noble`.

Regenerate with:

```sh
./scripts/vendor-trystero.sh
```
