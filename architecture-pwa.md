# SPARC'd — PWA-First Rewrite, Architecture Brief

A parallel proposal to `architecture.md`. Same goal — drop the Python/Docker server, model Camtrap-DP natively, work offline — but achieved as a **pure progressive web app** with no install, served as a static site, persistent on the user's device via OPFS.

This is the option if "zero install, share a URL" is more valuable than maximum native fidelity.

---

## 1. Why PWA-first

Electron buys native SQLite, native sharp, direct filesystem and S3 access. In 2026 those advantages have shrunk to the point that for SPARC'd's actual workload (10k–50k images per project, single user, single tab) they don't decisively matter. What does matter:

- **Adoption friction.** Open-source research tools live or die on first-use friction. "Click a link, start tagging" beats "download installer, accept Gatekeeper warning, launch."
- **Update velocity.** Static deploy = `git push` ships to all users. No code-signing pipeline, no notarization, no auto-updater.
- **Hosting cost.** Free tier on Cloudflare Pages / Vercel / GitHub Pages. No installer hosting, no CDN budget.
- **Surface area.** One codebase, one build, one runtime to debug.

The trades are real but bounded: Safari/Firefox desktop folder import is uglier; iOS is read-mostly; S3 buckets need a CORS policy. None of these block the core user.

---

## 2. What's actually changed (2026 baseline)

The decisions below are grounded in current browser capabilities, not 2023 assumptions:

- **OPFS** (Origin Private File System) is supported in Chrome 102+, Safari 15.2+, Firefox release. Not Chromium-only.
- **sqlite-wasm with the OPFS-SAH-Pool VFS** is production-ready: 3–4× faster I/O than the regular OPFS VFS, **no COOP/COEP headers required** (huge deployment simplifier), works on databases >1GB. Single-connection only — exactly the constraint we'd impose anyway.
- **Storage quotas** are large: Safari 17+ allows up to ~60% of disk per origin, Chromium similar. `navigator.storage.persist()` provides eviction protection.
- **iOS 26** opens Home Screen sites as web apps by default; push, install, and app-mode display are first-class.

What's still missing on Safari/iOS Safari and shapes the design:

- **No File System Access API** on Safari (any platform) or Firefox. We use Chromium's `showDirectoryPicker()` when available and fall back to `<input webkitdirectory>` elsewhere.
- **No OffscreenCanvas on iOS Safari.** Worker-based thumbnail generation is Chromium/Firefox/Safari-desktop only; iOS falls back to main-thread canvas.
- **No Background Sync** on iOS. S3 mirroring is foreground-only — fine for an interactive app.
- **No WebCodecs on iOS.** Doesn't affect still images; rules out video tagging on iOS.

---

## 3. Platform tiers (intentional, not accidental)

We commit to four explicit tiers with documented capability differences. Ship one codebase; tier-detect at runtime.

| Tier | Browsers | Folder import | Worker thumbs | Editing | Notes |
|---|---|---|---|---|---|
| **Primary** | Chrome / Edge / Brave / Arc on desktop | `showDirectoryPicker` | OffscreenCanvas in Worker | Full | Reference UX; what the design brief targets. |
| **Standard** | Safari / Firefox on desktop | `<input webkitdirectory>` multi-select | OffscreenCanvas in Worker | Full | Slightly worse import UX; everything else identical. |
| **Companion** | Chrome / Safari on Android | Multi-select files (no directory) | OffscreenCanvas | Full but UX-constrained by screen size | Useful for review and light tagging. |
| **Read-mostly** | Safari on iOS | Multi-select photos | Main-thread canvas | Read + light edits | Field lookup, site management, spot-tagging. Not the bulk tagger. |

The tagger UI is designed for desktop tier-1/tier-2; the home/maps/sites surfaces are designed to be useful on tier-3/tier-4.

---

## 4. Repository layout

Same monorepo structure as the Electron proposal, but with `apps/web` instead of `apps/desktop`:

```
sparcd/
├── packages/
│   ├── core/                  # Pure TS, no runtime/browser deps
│   │   ├── camtrap/           #   Camtrap-DP types, JSON Schemas, ajv validators
│   │   ├── domain/            #   Project, Deployment, Media, Observation types
│   │   ├── logic/             #   cluster-into-deployments, query spec, pure helpers
│   │   └── csv/               #   Streaming CSV reader/writer
│   └── db/                    # Drizzle schema + migrations (SQLite dialect)
└── apps/
    └── web/                   # Vite + React, deployed as static site
        ├── src/
        │   ├── workers/       #   db.worker.ts (sqlite-wasm), thumbnail.worker.ts
        │   ├── platform/      #   tier detection, capability shims
        │   ├── pages/
        │   ├── components/
        │   └── service-worker.ts
        └── public/
```

`packages/core` and `packages/db` are usable from a future Electron wrapper, RN app, or CLI tool without modification. Today they're consumed only by `apps/web`.

---

## 5. Data model

**Identical to the Electron proposal — Camtrap-DP is the schema.** SQLite tables mirror the standard 1:1: `deployments`, `media`, `observations`, plus auxiliary `sites`, `taxa`, `projects`, `settings`, `sync_log`. UUIDv7 IDs throughout. EXIF is read-only; corrected timestamps and species tags live in the DB.

The only data-model difference from the Electron version is in `media`:

```
media._localPath        -- Electron only: absolute disk path
media._opfsPath         -- PWA: path within OPFS (e.g., "media/<sha>.jpg")
media._fsHandleId       -- PWA Chromium: ID of a persisted FileSystemFileHandle in IndexedDB
                           (lets us reference user's local file without copying)
media._contentHash      -- sha256, used as S3 key and OPFS filename
media._s3Url            -- nullable; populated when mirrored
media._thumbnailPath    -- OPFS path of cached thumbnail
```

`_opfsPath` and `_fsHandleId` are mutually exclusive per row. On import the user picks one of two strategies (see §7).

---

## 6. Process architecture

```
┌─────────────────────────────────────────────────────────┐
│  Main thread (UI)                                       │
│  - React 19 + TanStack Router/Query                     │
│  - Comlink-wrapped proxies to workers                   │
│  - Service worker registration (Workbox)                │
└─────────────────────────────────────────────────────────┘
              ▲                         ▲
              │ Comlink                  │ Comlink
              ▼                         ▼
┌────────────────────────┐    ┌────────────────────────┐
│  DB Worker             │    │  Thumbnail Worker      │
│  - sqlite-wasm         │    │  - createImageBitmap   │
│  - OPFS-SAH-Pool VFS   │    │  - OffscreenCanvas     │
│  - Drizzle queries     │    │  - WebP encode         │
│  - CSV streaming       │    │  - Writes to OPFS      │
└────────────────────────┘    └────────────────────────┘
              │                         │
              ▼                         ▼
┌─────────────────────────────────────────────────────────┐
│  Origin Private File System                             │
│  /                                                      │
│  ├── projects/                                          │
│  │   └── <projectId>/                                   │
│  │       ├── project.sparcd.db    ← sqlite-wasm DB      │
│  │       ├── media/<sha>.jpg      ← if copy-in mode     │
│  │       └── thumbs/<sha>.webp    ← lazy thumbnails     │
│  └── current-project-pointer                            │
└─────────────────────────────────────────────────────────┘
              │                     │
              │                     │ S3 SDK (in main thread or
              │                     │ a sync worker)
              ▼                     ▼
   IndexedDB (small)         Optional S3 mirror
   - persisted FileSystem-   (any S3-compatible: R2,
     FileHandles for         Backblaze, Wasabi, Minio, AWS)
     "reference originals    CORS configured per bucket
     in place" mode
```

### Why two workers

The DB worker is required: sqlite-wasm + OPFS-SAH-Pool needs a dedicated worker (only one connection per OPFS pool, and we don't want UI blocking on queries). The thumbnail worker keeps image decoding off the main thread on tiers 1–3; on iOS (tier 4) we skip it and call from the main thread.

### IPC across workers

[Comlink](https://github.com/GoogleChromeLabs/comlink) gives us typed RPC over `postMessage`. The DB worker exposes a typed surface that mirrors the Electron `api` proposal — `project.open`, `media.list`, `observations.upsert`, `query.run`, etc. Same shape, different transport. Code calling the API doesn't know whether it's hitting Electron IPC or Comlink.

This is what makes a future Electron wrapper cheap: replace the Comlink transport with `ipcRenderer`, keep the contract.

---

## 7. Image storage strategy

Two modes per project, user picks at import time:

### Mode A — Copy into OPFS (default)

- On import: stream each file → compute sha256 → write to `OPFS:projects/<id>/media/<sha>.jpg`.
- Quota: up to ~60% of disk (huge — a 1TB drive gives 600GB of headroom).
- Pros: completely portable, works offline forever, no dependence on user's filesystem layout, works on every tier.
- Cons: doubles disk use during the import session; full copy of a 100GB SD card means 100GB OPFS + 100GB SD card connected until copy finishes.

### Mode B — Reference originals (Chromium tier 1 only)

- On import (after `showDirectoryPicker` returns a `FileSystemDirectoryHandle`): walk the directory, compute hashes, persist each `FileSystemFileHandle` in IndexedDB keyed by `_fsHandleId`.
- The browser remembers user permission to access these handles across reloads (Chromium-only behavior).
- Pros: zero copy, instant import, ~no disk overhead.
- Cons: if the user moves/deletes the original folder, the project breaks for those rows. Chromium-only. Not portable (a different machine can't reuse those handles).

We default to Mode A. Mode B is offered as "Import in place — faster, but don't move these files" for Chromium users with large libraries.

### Thumbnails

Generated lazily on first view, cached in `OPFS:projects/<id>/thumbs/<sha>.webp`. Worker pipeline on tiers 1–3; main-thread fallback on iOS. Two sizes: ~256px (grid view), ~1024px (tagger).

---

## 8. Persistence and eviction

Three things together keep data safe:

1. **`navigator.storage.persist()`** — request on first project save. Promotes the origin to "persisted," exempting it from eviction. Granted automatically on Chromium when the site is installed; requires notification permission on iOS Safari to be reliable.
2. **`navigator.storage.estimate()`** — surface remaining quota in the UI. Warn the user before they run out.
3. **S3 mirror** — the genuine durability story. If a researcher cares about not losing data, they configure the S3 mirror; OPFS becomes a cache, not the only copy.

We tell users explicitly in onboarding: *unsynced work lives only in your browser's storage. Configure S3 backup if you can't tolerate losing it.*

---

## 9. S3 access from the browser

Direct from the browser using `@aws-sdk/client-s3`. Works against any S3-compatible endpoint (AWS, R2, Backblaze, Wasabi, Minio, DigitalOcean Spaces).

**The CORS tax.** Every bucket needs a one-time CORS policy:

```json
[{
  "AllowedOrigins": ["https://sparcd.example.org"],
  "AllowedMethods": ["GET", "PUT", "POST", "DELETE", "HEAD"],
  "AllowedHeaders": ["*"],
  "ExposeHeaders": ["ETag", "x-amz-version-id"],
  "MaxAgeSeconds": 3000
}]
```

We ship a one-click "Generate CORS policy for this bucket" helper that produces the JSON above for the user's deployed origin. Rough edge, not a blocker.

**Credentials.** Stored encrypted in IndexedDB using the `SubtleCrypto` AES-GCM with a key derived from a user-supplied passphrase (PBKDF2). On every app load, prompt for the passphrase to decrypt. Less convenient than OS keychain, but it's the honest browser-native answer; any "save in plaintext" alternative is unsafe.

**Multipart upload** for files >5 MiB: `@aws-sdk/lib-storage` handles this. Chunked, resumable, abortable.

**Content-hashed keying.** Same as the Electron proposal: `<prefix>/media/<sha256>.<ext>`. Deduplicates across projects.

---

## 10. Auth

**No app-level auth.** The DB belongs to whoever has access to the browser profile. S3 credentials are the only secret, encrypted at rest with a passphrase. No login, no users table, no tokens.

The current Flask backend's entire auth/session/admin layer disappears.

---

## 11. Stack reference

| Layer | Choice |
|---|---|
| Bundler | Vite |
| UI | React 19 + TypeScript |
| Router | TanStack Router |
| Server state | TanStack Query (with Comlink-wrapped DB worker as the "server") |
| UI primitives | Radix Primitives + Tailwind v4 |
| Maps | MapLibre GL |
| DB | sqlite-wasm (OPFS-SAH-Pool VFS) + Drizzle ORM |
| Worker comms | Comlink |
| EXIF | exifr |
| Image processing | `createImageBitmap` + OffscreenCanvas + WebP encode (no library) |
| S3 | @aws-sdk/client-s3, @aws-sdk/lib-storage |
| Schema validation | ajv + Camtrap-DP JSON Schemas |
| CSV | csv-stringify, csv-parse (streaming) |
| Service worker | Workbox |
| Hosting | Cloudflare Pages / Vercel / Netlify / GitHub Pages |

What's specifically *not* needed compared to the Electron proposal: better-sqlite3, sharp, electron-builder, electron-updater, contextBridge, preload scripts, code-signing setup.

---

## 12. Key workflows

### A — Open or create a project

1. Home shows a list of projects discovered in OPFS.
2. "New project" → name + optional S3 config → DB worker creates `OPFS:projects/<uuid>/project.sparcd.db`, runs migrations, returns summary.
3. "Open project" → DB worker mounts the DB, reads `projects` row.

### B — Import images

1. User clicks Import. Tier 1 gets `showDirectoryPicker`; tier 2/3/4 get a multi-file input.
2. Chosen files stream through the thumbnail worker:
   - Read EXIF (exifr).
   - Compute sha256.
   - Either copy bytes to OPFS (Mode A) or persist `FileSystemFileHandle` (Mode B, Chromium only).
   - Generate thumbnail to OPFS.
   - Insert `media` row via DB worker.
3. On completion, run deployment auto-clustering by `(cameraID, gap > 8h)`.

### C — Tag

Identical UX to the Electron proposal. The implementation differs only in transport (Comlink to DB worker vs IPC to main process).

### D — Query

DB worker composes a Drizzle SQL query, returns rows over Comlink. CSV export streams from worker → `WritableStream` → `showSaveFilePicker` (tiers 1–2) or Blob+download anchor (tiers 3–4).

### E — Export Camtrap-DP package

1. DB worker assembles `datapackage.json` + the three CSVs in memory (or streams to OPFS first for huge projects).
2. Validates with ajv against published Camtrap-DP JSON Schemas.
3. User picks destination:
   - Tier 1: `showDirectoryPicker` → write files directly into a folder of their choosing.
   - Tier 2/3/4: bundle into a ZIP (using `client-zip` or similar) → trigger download.

### F — Sync to S3

1. User configures endpoint + bucket + credentials (passphrase-encrypted).
2. `sync.push()` runs in the main thread: query for `media` rows where `_s3Url IS NULL`, upload concurrently (4–8 parallel, configurable), update rows on completion.
3. Foreground only on iOS (no Background Sync); persistent on Chromium via Background Sync API where available.

---

## 13. Deployment

- Static site. Build artifact: `apps/web/dist/`.
- Service worker (Workbox) caches the app shell for offline launch.
- No COOP/COEP headers required (OPFS-SAH-Pool doesn't need them).
- HTTPS required (PWAs and OPFS won't run otherwise) — handled automatically by Cloudflare Pages / Vercel / Netlify.
- Custom domain optional; the app works under any origin.

`git push` to main → CI builds → CDN serves. Update is automatic on the user's next page load (and the service worker can show a "new version available" toast).

---

## 14. PWA vs Electron — decision matrix

Use this doc's plan if:

- Adoption matters more than maximum native polish.
- Realistic dataset stays in the 10k–50k images per project range.
- Users will tolerate one-time S3 CORS configuration.
- Mobile/iOS use cases are read-mostly (lookup, review, light edits).
- "Visit URL → working" is the desired first-run experience.

Use the Electron plan (`architecture.md`) if:

- You need File System Access on Firefox or Safari (genuinely directory-based bulk import on those browsers).
- Single-project datasets routinely exceed ~500k rows or ~100GB and OPFS quota becomes a real concern.
- Avoiding browser CORS configuration on every S3 endpoint is an enterprise requirement.
- You need full Background Sync, deep OS integration (file associations, system tray, dock badges beyond what PWAs offer), or a "real installer" experience for a user base that demands it.

A future Electron wrapper *over the same renderer* is a viable phase-2 addition: replace the Comlink transport with Electron IPC, swap sqlite-wasm for better-sqlite3 behind the same DB worker interface, ship as installer. The renderer code does not change. So choosing PWA-first is not a one-way door.

---

## 15. Phasing

**Phase 0 — Skeleton (1 week)**
- Vite + React + Tailwind + Radix scaffolding.
- DB worker with sqlite-wasm + OPFS-SAH-Pool, running migrations, Drizzle queries from main thread.
- Tier detection (FS Access, OffscreenCanvas, persist).

**Phase 1 — MVP (3–4 weeks)**
- Camtrap-DP schema + migrations.
- Project create/open from OPFS.
- Image import (Mode A — copy into OPFS) with EXIF and thumbnail pipeline.
- Tagging surface per Notebook design tokens.
- Site management, deployment auto-clustering.
- Basic query screen.
- Camtrap-DP export with ajv validation (ZIP download on tier 2+, directory write on tier 1).

**Phase 2 — Sync + polish (2 weeks)**
- S3 mirror (push only initially), passphrase-encrypted credential store.
- Maps screen (MapLibre + sites).
- Camtrap-DP import for round-tripping.
- Mode B "import in place" for Chromium users.

**Phase 3 — PWA hardening**
- Workbox service worker, offline app shell, "update available" UX.
- Quota warnings, persist() onboarding flow.
- Tier-aware UI affordances (hide directory-picker buttons on Safari/iOS).
- Optional: Trusted Web Activity for Play Store presence; PWABuilder pipeline for Microsoft Store.

**Phase 4+ — Optional**
- Electron wrapper over the same renderer if a real user need emerges.
- React Native companion for richer iOS field UX, sharing `packages/core`.
- Sync server for genuine multi-writer collaboration.

---

## 16. Open questions

- **Mode A vs Mode B default for Chromium users.** Copy-in is universal but doubles disk use during import. Reference-in-place is faster but fragile. Lean: ship Mode A as default, expose Mode B as "Advanced: Import in place."
- **Service worker scope vs single-page deploy.** A static SPA with one service worker is straightforward, but route-based code splitting changes the cache strategy. Lean: Workbox precaching of the app shell, runtime caching for any external assets.
- **Bundled species/taxonomy data.** Same question as the Electron proposal — ship a default subset of GBIF backbone, editable per project.
- **Map tile caching.** OSM tiles by default; offer mbtiles import for offline field use? Same answer as Electron.
- **Multi-tab safety.** OPFS-SAH-Pool is single-connection; opening the same project in two tabs needs to be detected and blocked (or the second tab opens read-only). Use `BroadcastChannel` to coordinate.
- **Migration target.** Same as Electron: defer the legacy SPARCd S3 importer until a real user asks. Camtrap-DP-only on day one.
