# SPARC'd PWA — Multi-Volunteer Sync Problem

## The setup

The PWA plan (`architecture-pwa.md`) puts everything in the browser:
- **SQLite-wasm** in OPFS holds all project data (deployments, media rows, observations, taxa…).
- **Optional S3-compatible bucket** (R2, AWS, Backblaze, Minio, etc.) mirrors *media files only*.
- No backend, no accounts, static-site deploy.

## The problem

This is **single-user by construction.** Two volunteers tagging the same project end up with two unrelated SQLite databases on two laptops. There is no merge path short of CSV export/import.

We can't fix it by putting the SQLite file in the bucket — SQLite needs single-writer file locking, and object stores don't provide that.

## Hard constraints

This is open-source and global. Any solution has to grade across:

- **Tier 0** — Volunteer has nothing but a browser. Works offline forever, no sync.
- **Tier 1** — Project has *one* S3-compatible bucket. Nothing else. No funding for workers/servers. **This is the realistic case for most projects.**
- **Tier 2+** — Project has a bucket + something (Worker, VPS, Durable Object). Nice-to-have, can't be required.

So the multi-user mechanism has to work with **just a bucket**.

## Sketch of a fix (to discuss)

Per-author, append-only, **signed** logs. Each volunteer writes only to their own area; everyone reads others' as permitted and merges locally. (Inspired by Secure Scuttlebutt; "git for observation records.")

```
bucket/                                      ← S3 = a permanently-online replication peer (optional)
  media/<sha>.jpg                            (immutable, content-addressed)
  authors/<pubkey>/log/<seq>.changeset       (signed logical changesets)
  authors/<pubkey>/log/<seq>.sig             (Ed25519 detached signature)
  authors/<pubkey>/snapshot/<watermark>.db   (periodic compaction)
  project/manifest/<seq>.json(+.sig)         (signed membership: allowed pubkeys)
```

- Local SQLite stays the source of truth per device. Each write produces a **logical changeset** (SQLite `sqlite3session` extension, or [cr-sqlite](https://github.com/vlcn-io/cr-sqlite) for ready-made CRDT merge), signed with the author's key.
- On pull: verify signature → check author is in the signed project manifest → apply.
- No write collisions — different author prefixes. No server validates anything; trust is the manifest + signatures.
- Offline-first naturally: queue signed changesets locally, flush when reconnected.
- Tier 0 still works (no peer to push to).
- P2P (WebRTC) and a future relay are *transport upgrades only* — same signed-log data model, so nothing migrates.

## Why not Litestream / shipping the WAL

Litestream is a Go server sidecar and ships *physical* WAL page frames — single-writer leader replication, no multi-author merge, and physical pages can't be per-author signed or merged. Don't port it. The right primitive is **logical** changesets (`sqlite3session` / cr-sqlite). For "I dropped my laptop" backup of one person's own DB, a periodic `VACUUM INTO` snapshot upload covers ~90% of the value.

## Identity & signing with no server (the key question)

- Ed25519 keypair generated **in the browser** (`SubtleCrypto`, native in current Chrome/Safari/Firefox). The **public key is the identity** — self-sovereign, exactly like an SSH key or a signed git commit. No server issues or validates it.
- Private key stays in OPFS/IndexedDB, wrapped with a passphrase (PBKDF2 + AES-GCM). Never leaves the device.
- "Auth" = a signed project manifest listing member pubkeys, bootstrapped by the project creator, extended by appending signed membership records. Bucket write-credential is the coarse gate; signatures are the fine gate.
- Recovery: SLIP-39 (Shamir) recovery shares with trusted co-volunteers. Worst case, start a fresh collection.

## Things to figure out together

1. Does our `sqlite-wasm` build include `SQLITE_ENABLE_SESSION`? If not: cr-sqlite, or an app-level op-log.
2. Schema cost: UUID PKs, soft-deletes with tombstones, no `AUTOINCREMENT`. Mostly already planned.
3. Compaction policy — who triggers it, how often, races (`PUT-If-None-Match`).
4. Credential sharing: project owner gives each volunteer a bucket-scoped, prefix-scoped key. Good enough?
5. Sync cadence/UX — poll every 15–30s; surface a "last synced / N peers" indicator.
6. Tier 0 collaboration: Camtrap-DP export/import as the manual fallback.
7. phiresky's range-request SQLite: useful to *lazy-read a peer's snapshot without full download*, but it's read-only, unmaintained (2023), and on old `sql.js` — treat the **technique**, not the library, as the dependency.
8. P2P transport: WebRTC needs signaling. Realistic v1 = S3-as-peer (zero P2P code); QR/bucket SDP rendezvous later. Don't let P2P block the build.
