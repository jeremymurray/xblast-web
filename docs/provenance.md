# Asset and source provenance

Audit date: 2026-11-01. Auditor: the port's maintainer, with AI assistance.
Scope: everything shipped in this repository and in the browser build (`engine/`,
`data/`, `web/vendor/`).

Every file in `data/` was compared byte-for-byte (SHA-256) against the Debian
binary package payload **and**, except for the font, against the upstream source
tarball named in the Debian `.dsc`. No file differs; no file was added or edited.
Reproduce with the commands at the end of this document.

## Versions and checksums

Debian pool: <https://deb.debian.org/debian/pool/main/x/> and
<https://deb.debian.org/debian/pool/main/t/ttf-bitstream-vera/>.

| Component | Debian version | Upstream source archive (SHA-256) | Debian binary `.deb` (SHA-256) |
|---|---|---|---|
| engine | `xblast-tnt` 2.10.4-6 | `xblast-tnt_2.10.4.orig.tar.gz`<br>`93cd7c47ff83e00655605fcbec6a031f75d170d7eb467b85bcbe6c1733bcc213` | `xblast-tnt_2.10.4-6_amd64.deb`<br>`19b3a8ba31cb48e4e3bfc91a771746352c20bdd2c373d5e4de414f456cdf205d` |
| images | `xblast-tnt-images` 20050106-5 | `xblast-tnt-images_20050106.orig.tar.gz`<br>`24b627af1d4884fa39cbfb4ad2d953661aa5283f96ee678137ba554b67423542` | `xblast-tnt-images_20050106-5_all.deb`<br>`997c98650a1d45a5dc1ba7e6f328a4450062a3fe9db9bd5812d61c9642139578` |
| levels | `xblast-tnt-levels` 20050106+repack-3 | `xblast-tnt-levels_20050106+repack.orig.tar.xz`<br>`86a60c9319b481e788b9f2c5040a7319e405b72f580b2210fadb96690c4f08d8` | `xblast-tnt-levels_20050106+repack-3_all.deb`<br>`99ae34deb0033897afb836339cee280b82e64ffde0d2c0a7e9d9b8a75d92991c` |
| sounds | `xblast-tnt-sounds` 20040429-5 | `xblast-tnt-sounds_20040429.orig.tar.gz`<br>`310c89592139df617e6e981ab5bf3bfca84a7778d5191334bda8eb069c924b61` | `xblast-tnt-sounds_20040429-5_all.deb`<br>`4028dcd2b8a9771b6801fb1a2610b70e71dd3a16dc4526420f5df11bd5e2525d` |
| models (sprites) | `xblast-tnt-models` 20050106-6 | `xblast-tnt-models_20050106.orig.tar.gz`<br>`daed0d50c0371afe187159c7692d7d26d124e80e9c3208043d83a5b6ca610f77` | `xblast-tnt-models_20050106-6_all.deb`<br>`1af1b9c226cd40b3f7b94937ed64a74df9ae7905bd3d2f1a61742838088b35b3` |
| music | `xblast-tnt-musics` 20050106-5 | `xblast-tnt-musics_20050106.orig.tar.gz`<br>`42a45b074925755d7d2a0effb9a59e9e3874f92a7aa9e10bb90f98eeb11cbc61` | `xblast-tnt-musics_20050106-5_all.deb`<br>`028a97d8fc6ced9fdd7153b75d55cc59199112d02ac452904224f14685e96140` |
| Vera font | `ttf-bitstream-vera` 1.10-11 | (font package; no separate source archive used) | `ttf-bitstream-vera_1.10-11_all.deb`<br>`83b93d840399322bb190bb2207f529648aaba4e90dc5c6629217584805c48473` |

Debian source-package control files (`.dsc`) were checked too; their
`Checksums-Sha256` entries match the downloaded archives above. Only the
following archive hashes are listed for completeness:

| Debian source control/tarball | SHA-256 |
|---|---|
| `xblast-tnt_2.10.4-6.debian.tar.xz` | `85d0d55bb0cd359201d63ef9fe1419aa9e7af3631c79fec97c3e91a391d5bc81` |
| `xblast-tnt_2.10.4-6.dsc` | `3bbe8727f043ea15d275b94d7bd025ddf865c26514c525f3570bd40263d047e8` |
| `xblast-tnt-images_20050106-5.debian.tar.xz` | `ddc6347b26ec935eacc464838efd5d9be0031add3148dd129a794ebbad336515` |
| `xblast-tnt-levels_20050106+repack-3.debian.tar.xz` | `e4549e81af5c48dc621bb561f54d7362cbd80096cbb62555ee03647ffa84f8d8` |
| `xblast-tnt-sounds_20040429-5.debian.tar.xz` | `f2ee9965cf45c07618c5561e819c7b584014dcd6b3ce4f6b2905032c8538ee60` |
| `xblast-tnt-models_20050106-6.debian.tar.xz` | `e5d23a205db664d15f60e6495240f7c2543ad7538b96f050b4453e560e91d961` |
| `xblast-tnt-musics_20050106-5.debian.tar.xz` | `8c831f65d6f0e16de6b78d6935f4645c8fed22e43547194f259b22ffcd80887d` |

## What is shipped

| Repository path | Files | Bytes (disk) | Source package | Licence |
|---|---:|---:|---|---|
| `data/image/{misc,score,explosion,block}` | 343 | 12 MB (with sprites) | `xblast-tnt-images` | GPL-2+ |
| `data/image/sprite` (`.epm` + `.pbm`) | 1,252 | (included above) | `xblast-tnt-models` | GPL-2+ |
| `data/level/*.xal` | 1,188 | 4.6 MB | `xblast-tnt-levels` | GPL-2+ |
| `data/sounds/*.raw` (effects) | 50 | 2.6 MB | `xblast-tnt-sounds` | GPL-2+ |
| `data/sounds/xbsng{1..6}.raw` (music) | 6 | 8.2 MB | `xblast-tnt-musics` | GPL-2+ |
| `data/Vera.ttf` | 1 | 68 KB | `ttf-bitstream-vera` | Bitstream Vera licence |

Per-package notes:

- **Engine.** `engine/` is `xblast-tnt_2.10.4.orig.tar.gz` plus the four Debian
  2.10.4-6 patches (`fix-manpage`, `020_fix-ftbfs-with-gcc-10.patch`,
  `more_manpage_fixes.patch`,
  `0004-Try-harder-to-make-xbsndsrv.pid.-Don-t-segfault-if-c.patch`), then the web
  port's own changes on top (tracked in git). Upstream and Debian copyrights are
  reproduced in `LICENSE/data/xblast-tnt_2.10.4-6_amd64.copyright`.
- **Images and models.** `data/image/{misc,score,explosion,block}` match the
  images package; `data/image/sprite` matches the models package, including the
  `.epm` model sprites. The models copyright also names the sprite authors
  (Mark Weyer for golem/insect/sticky/tutorial, Oliver Vogel for felix/epmtools).
  `expl.pos` and `sprite.pos` from the source archives are editor/atlas metadata,
  are not read by the game, and are the only upstream files deliberately omitted.
- **Levels.** The Debian source is a repack (`+repack`) made to avoid a non-UTF-8
  filename; the shipped set is byte-identical to the repacked source archive. No
  level was edited. 1,188 `.xal` files, all ASCII names.
- **Sounds and music.** All 50 sound effects match the sounds package. The six
  music tracks match both the Debian package and upstream
  `musics-2005-01-06.tar.gz` (see the music audit below). No Debian patches
  touch either package (`debian/patches` is empty for both).
- **Font.** `data/Vera.ttf` is byte-identical to `Vera.ttf` in
  `ttf-bitstream-vera_1.10-11`. The Bitstream Vera licence requires that
  modified fonts be renamed; this copy is unmodified, so the name is kept. The
  full notice is in `LICENSE/data/ttf-bitstream-vera.copyright` and
  `LICENSE/Bitstream-Vera.txt`.
- **No other media.** There is no video, no external music directory, and no
  downloaded asset outside `data/`. `.downloads/` (ignored) holds only the Debian
  packages and source archives used for this audit.

## Music audit (six tracks)

The repository ships six background tracks. The per-track result:

| File | Bytes | Matches Debian 20050106-5 payload | Matches upstream `musics-2005-01-06` |
|---|---:|:--:|:--:|
| `xbsng1.raw` | 2,429,308 | yes | yes |
| `xbsng2.raw` | 848,352 | yes | yes |
| `xbsng3.raw` | 865,242 | yes | yes |
| `xbsng4.raw` | 1,192,278 | yes | yes |
| `xbsng5.raw` | 1,965,972 | yes | yes |
| `xbsng6.raw` | 1,275,232 | yes | yes |

Findings:

- The files are unsigned 8-bit PCM `.raw` (the music entries are marked stereo,
  the effect entries mono), loaded by
  `engine/sdl_sound.c` as `SND_SNG1`–`SND_SNG6` and selectable as **Song1**–**Song6**
  in the game setup menu. They are a real feature, not stray leftovers.
- `debian/copyright` for `xblast-tnt-musics` covers `Files: *` as **GPL-2+**,
  copyright 2004 Oliver Vogel & others, Fernando Benites and Rhonda D'Vine.
  The source package has no patches; `debian/install` copies `*.raw` verbatim.
- **No per-track authorship record exists.** Neither the upstream tarball (six
  bare `.raw` files), the Debian package, nor the upstream web site names a
  composer or a licence per track. The audit therefore establishes provenance
  and the package-level GPL-2+ grant by exact hash, not an individual credit
  line per track. This limitation is recorded here and in `THIRD_PARTY.md`; it
  must not be presented as a per-track attribution.
- The upstream source is still published by the XBlast project
  (`musics-2005-01-06.tar.gz`, version 20050106) and Debian's `debian/watch`
  tracks it. Nothing suggests a non-free track was mixed into the package.

## Verification recipe

With the Debian packages and source archives in `.downloads/` (ignored):

```sh
# 1. Compare every shipped asset with the binary package payload
dpkg-deb -x .downloads/xblast-tnt-images_20050106-5_all.deb /tmp/xb-images
# ... repeat for levels, sounds, models, musics, ttf ...
# 2. Compare the upstream source archive
tar -xzf .downloads/xblast-tnt-images_20050106.orig.tar.gz -C /tmp/xb-src
# 3. Hash both sides; every asset must match, with only Imakefile and the two
#    .pos metadata files excluded.
```

The audit used `sha256sum`/`shasum -a 256` over every file, not spot checks.
Records of the exact commands are kept in the M4 working notes; the hashes above
are the durable record.

## If provenance changes

Adding, replacing or editing an asset invalidates its row above. Re-run the
comparison, update this file and `THIRD_PARTY.md`, and do not publish until the
new file has a known, compatible licence. Music must stay out of any future
"no music" build claim: if a variant drops `data/sounds`, say so explicitly.
