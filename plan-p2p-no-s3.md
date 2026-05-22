# SPARC'd — Pure P2P Sync Plan (no S3, Trystero + Nostr)

**This is attempt #1: zero infrastructure.** No server, no bucket, no account — two browsers find each other and sync directly. If this fails its go/no-go criteria (§8), the documented fallback is the **S3-mandatory design** in `multi-user-question.md`, where an S3-compatible bucket acts as a dumb, always-online, trusted peer.

The two plans share one data model on purpose: **signed CRDT changesets**. Only the transport differs. Falling back changes the pipe, not the schema — nothing migrates.

---

## 1. Goal

Two volunteers, each running the static PWA in a browser, sync their project databases peer-to-peer with:

- no server the project operates,
- end-to-end encryption *and* authenticated identity (not just encryption),
- offline-first local work, opportunistic sync when both are online.

Hosted as a pure static site on Cloudflare Pages (HTTPS automatic — required for WebRTC, OPFS, secure context).

## 2. Hard constraints

- Static hosting only. No Workers, no Functions, no backend.
- "No server *you* run" — we may use public third-party rendezvous infra (Nostr relays) whose uptime we do not control.
- Safe between 2 untrusted-network clients: confidentiality + integrity + peer authentication.
- Must degrade without data loss when P2P cannot connect (it often won't — see §6).

## 3. Stack

| Concern | Choice | Notes |
|---|---|---|
| Local DB | `@sqlite.org/sqlite-wasm`, OPFS-SAHPool VFS | No COOP/COEP headers needed — clean static deploy. Single-connection (one DB worker). |
| CRDT / change capture | `cr-sqlite` (vlcn) | Real SQL CRDT changesets. **Risk:** last release v0.16.3 (Jan 2024), networking-agnostic, maintenance appears stalled. PoC may use **Yjs** (more active) to de-risk, with cr-sqlite as the target. |
| Discovery + signaling | **Trystero**, Nostr strategy | v0.24.0 (~Apr 2026), actively maintained. Use `@trystero-p2p/nostr` (the `trystero/<strategy>` path is deprecated). Hundreds of public Nostr relays; default and most reliable strategy. |
| Transport | WebRTC data channel (via Trystero) | DTLS-encrypted by default. |
| Identity / crypto | `@noble/curves` + `@noble/hashes` | Ed25519 identity, X25519, HKDF, SAS. SubtleCrypto Ed25519 is native in Chrome 137+/Safari 17+/Firefox 129+ (~84.5% global) but `@noble` gives uniform behaviour and older-browser coverage. |
| In-person pairing (optional) | QWBP-style QR | magarcia.io, Jan 2026 — compresses SDP to a single scannable QR, binds DTLS fingerprint. Promising, single-author, not battle-tested. |

## 4. Architecture

```
Volunteer A (browser)                         Volunteer B (browser)
┌───────────────────────┐                     ┌───────────────────────┐
│ sqlite-wasm + cr-sqlite│                     │ sqlite-wasm + cr-sqlite│
│ Ed25519 identity key   │                     │ Ed25519 identity key   │
└──────────┬─────────────┘                     └─────────────┬─────────┘
           │ local changeset, signed                          │
           ▼                                                  ▼
   Trystero room (joined by shared project code/secret)
           │                                                  │
           │  ── discovery + SDP/ICE via public Nostr relays ──│
           ▼                                                  ▼
        ┌──────────────── WebRTC data channel ────────────────┐
        │  DTLS-encrypted; carries SIGNED cr-sqlite changesets │
        └──────────────────────────────────────────────────────┘
                  ▲ SAS check on first connect (anti-MITM) ▲
```

### Flow

1. **Identity.** First launch generates an Ed25519 keypair in-browser; private key stays in OPFS, passphrase-wrapped. Public key = the volunteer's identity.
2. **Room join.** Both peers join a Trystero room keyed by a shared project code/secret. Discovery + SDP/ICE exchange ride public Nostr relays — no server we run.
3. **Anti-MITM pairing (mandatory on first connect).** A public relay operator can splice the DTLS session. Defeat it: derive a ZRTP-style **Short Authentication String** (≥~20–25 bits, emoji/word list) from a hash of both DTLS fingerprints + the DH transcript; the two volunteers compare it out-of-band (read it aloud / in person / scan QWBP QR). Pin each other's Ed25519 public key on success (trust-on-first-use).
4. **Sync.** Each local edit produces a cr-sqlite changeset, **signed** with the author's key. Changesets stream over the WebRTC data channel. On receive: verify signature → check author is in the signed project manifest → apply via cr-sqlite merge.
5. **Offline.** No peer connected = pure local work. Changesets queue and flush when a peer is next reachable.

### Why signing even though the channel is encrypted

DTLS gives confidentiality, not authenticated identity, and the rendezvous is untrusted public infra. Signed changesets mean a spliced or hostile relay can drop/observe but **cannot forge** a volunteer's records. Signing is also what makes the S3 fallback a drop-in: same signed payload, different transport.

## 5. Build phases

- **Phase 0 — PoC (~1 day, ~300 LOC).** Two browser tabs, `sqlite-wasm` + Yjs, Trystero/Nostr room by shared code. No crypto. Goal: prove end-to-end CRDT sync, zero server. Throwaway.
- **Phase 1 — Signed sync (~1–2 weeks).** Ed25519 identities; SAS pairing + QWBP QR option; swap Yjs → cr-sqlite for real SQL changesets; signed-changeset verify/apply against a signed project manifest.
- **Phase 2 — Hardening.** Reconnect/resume, multi-peer (>2) in one room, relay-failover across multiple Nostr relays, screen-sleep mitigation (§6), conflict-aware merge UI, persistent device keyring + SLIP-39 recovery.

## 6. Known failure modes we are explicitly testing against

These are not bugs to fix — they decide whether attempt #1 survives §8.

1. **No serverless TURN.** ~15–30% of real-world peer pairs (especially mobile/cellular/CGNAT) cannot establish a direct WebRTC link, and TURN is a server by definition. Trystero solves discovery, *not* NAT traversal. There is no serverless workaround.
2. **Public Nostr relay liveness.** Rendezvous depends on relays we do not control. Mitigate with multi-relay fan-out; accept residual risk.
3. **Backgrounding / screen sleep (the TangoShare lesson).** A backgrounded tab or sleeping device suspends WebRTC and JS — the connection drops. Both peers must be awake *and* foregrounded *simultaneously*. For a field-tagging workflow where volunteers work alone and asynchronously, simultaneous live presence is the exception, not the norm. **This is the single biggest threat to attempt #1.**
4. **cr-sqlite maintenance risk.** Stale since Jan 2024; we own the sync loop and accept the staleness/abandonment risk, or fall back to Yjs-modelled state.
5. **OPFS single-connection.** One DB worker; coordinate tabs with `BroadcastChannel`.

## 7. Cloudflare Pages notes

- HTTPS automatic — satisfies WebRTC/OPFS secure-context requirement.
- OPFS-SAHPool VFS needs **no** COOP/COEP headers — preferred.
- A static `_headers` file is available if cross-origin isolation is ever needed; not needed with SAHPool.

## 8. Go / No-Go: when we fall back to the S3-mandatory plan

Attempt #1 is declared **insufficient as the primary collaboration path** and we adopt the S3-mandatory design (`multi-user-question.md`) if, after Phase 1, any of the following hold on realistic testing:

- Direct-connect success rate across representative network pairs (incl. one mobile/CGNAT peer) is below ~70%, **and** the degraded UX (same-network hint, retry) does not make the failures tolerable for real volunteers.
- The backgrounding/screen-sleep constraint (§6.3) makes routine asynchronous tagging-then-sync unworkable for typical field usage.
- Public Nostr relay reliability causes frequent rendezvous failure that multi-relay fan-out does not resolve.

Falling back is cheap by design: the S3 plan carries the **same signed CRDT changesets**, just written/read as bucket objects under per-author prefixes instead of streamed over WebRTC. P2P then survives as a *latency optimization* on top of the S3 path rather than the foundation. Schema, identity, and merge logic are unchanged.

---

## 9. One-line summary

Try zero-infra pure P2P (Trystero + Nostr + signed cr-sqlite changesets over WebRTC) first; keep it only if it connects and stays connected often enough for real volunteers; otherwise demote it to an optimization above the S3-mandatory peer, with no data-model change either way.
