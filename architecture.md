# SPARC'd — Backend-less Architecture Brief

A from-scratch redesign that drops the Python/Docker server, treats Camtrap-DP as the native data model, and ships as a TypeScript desktop app that works offline.

This doc locks the runtime, data, and storage decisions. A separate visual design brief (the "Notebook" direction — locked tokens, sharp corners, hairline rules) is assumed but lives outside this document.

---

## 1. Why a new approach

Today's `sparcd-web` is a Next.js frontend on top of a Flask backend that does the real work. The Java original (CulverLab/sparcd) is JavaFX talking directly to S3/CyVerse with app-specific JSON.

Both share three structural problems we're choosing to drop:

1. **Always-online assumption.** Tagging is hours-long fieldwork-adjacent work; losing the network shouldn't lose the session.
2. **Platform shell-outs.** The current server invokes `exiftool` and `ExifWriter.jar` as subprocesses to read and write image metadata. That's the most fragile part of the system.
3. **Multi-tenant server with custom auth.** A SQLite + Fernet-encrypted-credentials + S3-per-endpoint model exists only to support shared buckets. Local-first removes the need entirely.

We also gain interoperability: Camtrap-DP is a published TDWG standard with a growing tool ecosystem (camtraptor, Agouti, TRAPPER, GBIF IPT). Producing it natively means SPARC'd data is portable on day one.

---

## 2. What we're building

A desktop application that lets a researcher:

- Open or create a **project** (a folder containing a SQLite database and image files).
- Import camera-trap images from disk; auto-cluster into deployments.
- Tag images with species, location, and corrected timestamps.
- Query the dataset (species × site × time × elevation × interval).
- Export a valid Camtrap-DP package.
- Optionally mirror image blobs to any S3-compatible store for backup or multi-machine use.

The app is offline-first. S3 is a mirror, never the source of truth.

---

## 3. Runtime and distribution

### Decision: Electron, with a browser-portable renderer

| Option | Verdict |
|---|---|
| Electron desktop | **Selected for v1.** Native SQLite (better-sqlite3) and native sharp for thumbnails handle realistic dataset sizes (10–100k+ images per project) without WASM penalties. S3 from the Node main process avoids browser CORS configuration on every endpoint. Filesystem APIs make camera-card import trivial. Distribution as `.dmg` / `.exe` / `.AppImage` matches the desktop UX the Java users came from. |
| Browser-only PWA | Rejected for v1. WASM SQLite is workable but slower at scale. File System Access API is Chromium-only and degrades on Firefox/Safari. iOS PWA storage eviction is a real risk for a tool holding hours of unsynced work. |
| Electron + React Native | Not v1. Domain logic shares; UI does not (the tagger's hotkey rail, zoom-pan, MapLibre, and dense grid all need platform-specific work). RN is the right mobile choice if mobile becomes a v2 requirement, but mobile use cases (field lookup, site checks, light review) are a different surface than the desktop tagger and shouldn't constrain v1. |

**Discipline that keeps options open:** the renderer is a clean Vite + React build with no Electron globals or Node imports leaking into UI code. All native capability flows through a typed IPC contract (see §6). That preserves a future PWA path and a future RN path; both would reuse `packages/core` as-is.

### Mobile, when it comes

If/when mobile demand is concrete: build a **separate read-mostly RN app** (`apps/mobile`) that consumes the S3 mirror or a synced project folder. Field lookups, site management, GPS-aware actions, light review — not the tagger. RN beats PWA here because iOS PWAs still have weak offline tile caching, weak persistence guarantees, and no proper background sync.

---

## 4. Repository layout

A pnpm + Turborepo monorepo:

```
sparcd/
├── packages/
│   ├── core/                  # Pure TS, no runtime deps. Imports allowed in any app.
│   │   ├── camtrap/           #   Camtrap-DP types, JSON Schemas, validators (ajv)
│   │   ├── domain/            #   Project, Deployment, Media, Observation types
│   │   ├── logic/             #   Pure functions: cluster-into-deployments, query spec, EXIF parse helpers
│   │   └── csv/               #   Streaming CSV reader/writer for Camtrap-DP resources
│   ├── db/                    # Drizzle schema + migrations. Imported by main process only.
│   └── ui/                    # Reusable React primitives styled with Notebook tokens (optional v1.5).
└── apps/
    └── desktop/               # Electron app
        ├── main/              #   Node main process: services, IPC server, window management
        ├── preload/           #   contextBridge typed API surface
        └── renderer/          #   Vite + React + TanStack Router/Query, browser-clean
```

Why a monorepo from day one: it costs almost nothing now and removes the only refactor that would otherwise be painful later (extracting domain logic when adding a second app).

---

## 5. Data model

**Camtrap-DP is the schema.** We don't translate between an internal model and the standard; the SQLite tables mirror the standard's resources 1:1.

### Core tables (Camtrap-DP-aligned)

```
deployments
  deploymentID (PK, UUID)
  locationID (FK -> sites)
  locationName, latitude, longitude, coordinateUncertainty
  deploymentStart, deploymentEnd
  cameraID, cameraModel, cameraDelay, cameraHeight, cameraDepth
  cameraTilt, cameraHeading, detectionDistance
  timestampIssues, baitUse, featureType, habitat
  deploymentGroups, deploymentTags, deploymentComments

media
  mediaID (PK, UUID)
  deploymentID (FK)
  captureMethod, timestamp, filePath, filePublic
  fileName, fileMediatype
  exifData (JSON), favorite, mediaComments
  -- local extensions (prefix with `_` to keep export clean)
  _localPath           -- absolute path on this machine
  _contentHash         -- sha256, used as S3 key
  _s3Url               -- nullable; populated when mirrored
  _thumbnailPath       -- cached thumbnail path

observations
  observationID (PK, UUID)
  deploymentID (FK)
  mediaID (FK, nullable for event-level obs)
  eventID, eventStart, eventEnd
  observationLevel ('media' | 'event')
  cameraSetupType
  scientificName, count, lifeStage, sex, behavior
  individualID, classificationMethod, classifiedBy, classificationTimestamp, classificationProbability
  observationTags, observationComments
```

### Auxiliary tables (local only)

```
sites           -- reusable site definitions (name, lat/lon, elevation, notes)
taxa            -- species list with vernacular names, hotkeys, sidebar order
projects        -- single row per DB: project metadata for datapackage.json
settings        -- key/value app preferences for this project
sync_log        -- record of S3 push/pull operations
```

### Identifiers

UUIDv7 throughout. Camtrap-DP allows any string identifier; UUIDv7 gives us time-ordered IDs that work offline without coordination and remain stable across machines.

### Why not embed tags into EXIF

Today's stack writes species and adjusted timestamps back into the JPEG via `ExifWriter.jar`. That's the source of most platform-specific brittleness. We're dropping it. EXIF is **read-only**. The corrected timestamp lives in `media.timestamp`; the original EXIF timestamp stays in `media.exifData.DateTimeOriginal` for audit. Species tags are observations, not file metadata. This is also how the Camtrap-DP standard actually works — the spec keeps tags in `observations.csv`, not in the file.

---

## 6. Process architecture

```
┌─────────────────────────────────────────────────────────┐
│  Renderer (Vite + React, sandboxed, no Node)            │
│  - Pages: Home, Tag, Query, Maps, Collections           │
│  - State: TanStack Query (treat IPC as fetch)           │
│  - Router: TanStack Router (file-less, code-defined)    │
│  - Calls window.api.* exposed by preload                │
└─────────────────────────────────────────────────────────┘
                    ▲ contextBridge IPC
                    │ typed via @sparcd/core types
                    ▼
┌─────────────────────────────────────────────────────────┐
│  Preload (small, audited)                               │
│  - Exposes exactly the procedures defined in api.ts     │
│  - zod-validates renderer→main payloads                 │
└─────────────────────────────────────────────────────────┘
                    │
                    ▼
┌─────────────────────────────────────────────────────────┐
│  Main (Node)                                            │
│  ┌──────────────┐ ┌──────────────┐ ┌─────────────────┐ │
│  │ ProjectSvc   │ │ MediaSvc     │ │ SyncSvc         │ │
│  │ open/create/ │ │ EXIF read,   │ │ S3 push/pull,   │ │
│  │ migrate/     │ │ thumb gen,   │ │ presigned URLs, │ │
│  │ export       │ │ deployment   │ │ creds via       │ │
│  │              │ │ clustering   │ │ safeStorage     │ │
│  └──────────────┘ └──────────────┘ └─────────────────┘ │
│  ┌──────────────┐ ┌──────────────────────────────────┐ │
│  │ DBSvc        │ │ CamtrapSvc                       │ │
│  │ Drizzle on   │ │ Validate (ajv) + import/export   │ │
│  │ better-      │ │ datapackage.json + 3 CSVs        │ │
│  │ sqlite3      │ │                                  │ │
│  └──────────────┘ └──────────────────────────────────┘ │
└─────────────────────────────────────────────────────────┘
                    │
                    ▼
       ┌─────────────────────────────┐
       │  Project folder              │
       │  /Users/.../MaderaCanyon/    │
       │    project.sparcd.db         │
       │    media/<original layout>/  │
       │    .cache/thumbs/<sha>.webp  │
       │    datapackage.json          │  ← regenerated on export
       │    deployments.csv           │
       │    media.csv                 │
       │    observations.csv          │
       └─────────────────────────────┘
```

### IPC contract

Define one `api.ts` shared between preload and renderer. Each procedure is a zod-validated function the renderer invokes through TanStack Query:

```ts
// packages/core/src/api.ts
export const api = {
  project: {
    open: z.function().args(z.string()).returns(z.promise(ProjectSummary)),
    create: z.function().args(NewProjectSpec).returns(z.promise(ProjectSummary)),
    export: z.function().args(z.string()).returns(z.promise(ExportResult)),
  },
  media: {
    list: z.function().args(MediaQuery).returns(z.promise(MediaPage)),
    importFolder: z.function().args(ImportSpec).returns(z.promise(ImportResult)),
    thumbnail: z.function().args(z.string()).returns(z.promise(z.string())), // file:// URL
  },
  observations: {
    upsert: z.function().args(ObservationInput).returns(z.promise(Observation)),
    deleteForMedia: z.function().args(z.string()).returns(z.promise(z.void())),
  },
  query: {
    run: z.function().args(QuerySpec).returns(z.promise(QueryResult)),
    exportCsv: z.function().args(QuerySpec).returns(z.promise(z.string())),
  },
  sync: {
    configure: z.function().args(S3Config).returns(z.promise(z.void())),
    push: z.function().returns(z.promise(SyncReport)),
    status: z.function().returns(z.promise(SyncStatus)),
  },
}
```

This shape gives the renderer a single typed surface and lets us swap the Electron transport for HTTP later if we ever do build a sync server, without touching renderer code.

---

## 7. Storage strategy

### Local is canonical

A project is a folder. The SQLite file is the only source of truth. The CSV/JSON Camtrap-DP files are **regenerated on export**, not edited in place — this avoids dual-write bugs and keeps the DB authoritative.

### S3 mirror (optional, per-project)

When configured:

- Credentials stored via Electron `safeStorage` (OS keychain).
- Endpoint URL + region + bucket + prefix configurable; works with AWS S3, Cloudflare R2, Backblaze B2, Minio, Wasabi.
- **Blobs only.** Image files are uploaded keyed by content hash: `<prefix>/media/<sha256>.<ext>`. Same image in two projects = one blob.
- Metadata never goes to S3. The DB stays local.
- Push is explicit (`SyncSvc.push`) or scheduled. Pull is rare — used to lazy-load a thumbnail or full image when working from a project file someone else's machine populated.

### Multi-machine, no server

The simplest "two laptops sharing a project" path is to put the project folder in iCloud Drive / Dropbox / OneDrive / Syncthing. SQLite handles single-writer-at-a-time fine. We do **not** try to solve concurrent multi-writer conflicts in v1; that's a CRDT problem and out of scope.

For genuine collaboration later, the path is: extract a tiny sync server that brokers SQLite WAL frames or operation logs. Don't design v1 around it.

### CyVerse iRODS

Out of scope. Generic S3 only. If a CyVerse user base needs to be supported later, add an `IRodsAdapter` behind the same `ObjectStore` interface.

---

## 8. Image and EXIF handling

| Concern | Choice | Notes |
|---|---|---|
| EXIF read | `exifr` | Pure JS, fast, handles maker notes. |
| Thumbnail generation | `sharp` in main process | WebP output, ~256px and ~1024px tiers, cached on disk by content hash. |
| Image display in renderer | `file://` URLs returned by IPC | No need to stream bytes through IPC. |
| EXIF write | **None.** | Drop the JAR. Corrected timestamps live in DB. |
| Video | Out of scope for v1. | Camtrap-DP supports video; we add it when there's real demand. |

---

## 9. Auth and security

**No app-level auth.** The DB belongs to whoever has the file. Mirrors Lightroom / Capture One / DaVinci Resolve.

S3 credentials are the only secret; they go in OS keychain via `safeStorage`. Never written to the DB or to disk in plaintext.

This removes from scope: the `users` table, `tokens` table, Fernet-encrypted-credentials column, login screen, idle timeout, admin role, password reset flow. Roughly six Flask blueprints disappear.

---

## 10. Stack reference

| Layer | Choice | Replaces |
|---|---|---|
| Shell | Electron 32+ | (new) |
| Bundler | Vite | Next.js |
| UI framework | React 19 + TypeScript | (kept) |
| Router | TanStack Router | Next App Router |
| Server state | TanStack Query | (new) |
| UI primitives | Radix Primitives + Tailwind v4 | MUI |
| Maps | MapLibre GL | ArcGIS (paid, key-bound) |
| DB | better-sqlite3 + Drizzle ORM | SQLite via Python |
| Migrations | Drizzle Kit | `create_db.py` |
| EXIF | exifr | exiftool subprocess |
| Image processing | sharp | (new — replaces no-op) |
| S3 | @aws-sdk/client-s3, @aws-sdk/s3-request-presigner | minio Python SDK |
| Schema validation | ajv + Camtrap-DP JSON Schemas | (new) |
| CSV | csv-stringify, csv-parse (streaming) | camtrap.v016 Python lib |
| Packaging | electron-builder | Docker compose |
| State | Jotai (UI-local) | (new) |

The MUI → Radix+Tailwind swap is driven by the Notebook visual direction: locked tokens, sharp corners, hairline rules. MUI fights every one of those defaults.

---

## 11. Key workflows

### A — Import images from a folder

1. Renderer calls `media.importFolder({ path, projectId })`.
2. Main walks the directory; for each image, reads EXIF (timestamp, camera ID, GPS if present), computes content hash, copies/links into `<project>/media/`.
3. Auto-cluster into deployments by `(cameraID, gap > 8h)` heuristic. User can adjust.
4. User assigns each cluster to a Site (existing or new).
5. Tagging unlocks.

### B — Tag

1. Renderer requests `media.list({ filter: { untagged: true }, limit: 1, after: cursor })`.
2. Main returns row + `file://` URL to a 1024px thumbnail (generated lazily).
3. User presses hotkey → `observations.upsert({ mediaID, scientificName, count })`.
4. Renderer optimistically advances cursor; TanStack Query handles invalidation.

### C — Query

1. Renderer sends `QuerySpec` (species[], sites[], dateRange, hourRange, etc.).
2. Main composes a Drizzle query joining `observations × media × deployments × sites`.
3. Results stream back; CSV export streams directly from SQLite to disk.

### D — Export Camtrap-DP

1. `project.export(targetPath)`.
2. Main reads from SQLite, writes `datapackage.json` with the Camtrap-DP profile + resource references, plus the three CSVs.
3. Validates with ajv against the published Camtrap-DP JSON Schemas before declaring success.
4. Optionally zips the result.

### E — Sync to S3

1. Configure once: endpoint, bucket, prefix, credentials → `safeStorage`.
2. `sync.push()` diffs `media._s3Url IS NULL` rows, uploads in parallel (configurable concurrency), updates rows.
3. No conflict resolution beyond "skip if blob with same hash already exists" — content-hash keying makes this safe.

---

## 12. What we drop from `sparcd-web`

| Dropped | Reason |
|---|---|
| Flask backend, all 11 blueprints | Not needed in a local-first app. |
| Docker / docker-compose | No services to orchestrate. |
| `ExifWriter.jar` | EXIF is read-only now. |
| `exiftool` subprocess | `exifr` is in-process and faster. |
| Python `camtrap.v016` library | We model Camtrap-DP natively. |
| `users`, `tokens`, password encryption (Fernet) | No app-level auth. |
| Idle timeout, session refresh logic | n/a. |
| Multi-tenant per-S3-endpoint workspaces | Each project is its own workspace. |
| Next.js app router + SSR | Pure SPA in Electron. |
| MUI / @mui/x-data-grid / @mui/x-date-pickers | Replaced by Radix + Tailwind + a custom virtualized grid. |
| ArcGIS / @arcgis/core | Replaced by MapLibre (free, OSM tiles, offline mbtiles support). |
| Disk-cached query results with TTL | Queries are fast against local SQLite; no cache needed. |
| `image_edits` / `collection_edits` audit tables | Not needed for local-first; can add later if researchers want change history. |

---

## 13. Phasing

**Phase 0 — Skeleton (1 week)**
- Electron + Vite + React boots. Single window.
- Open a folder; walk it; show first image with EXIF in a basic viewer.
- Drizzle schema for media table; insert rows on import.

**Phase 1 — MVP single-user (3–4 weeks)**
- Full Camtrap-DP schema in SQLite + migrations.
- Tagging surface (per the Notebook visual direction): species sidebar with hotkeys, image with zoom/pan, prev/next, observation list.
- Site management; deployment auto-clustering.
- Camtrap-DP export with ajv validation.
- Basic query screen (species × site × date).

**Phase 2 — Polish + S3 (2 weeks)**
- S3 sync service with `safeStorage` credentials.
- Maps screen (MapLibre + sites overlay).
- Camtrap-DP **import** for round-tripping.
- Query refinements: interval bucketing, CSV download.

**Phase 3 — Hardening (ongoing)**
- electron-builder code signing + notarization (macOS), MSIX (Windows), AppImage (Linux).
- Auto-update via electron-updater.
- Crash reporting.

**Phase 4+ — Optional**
- RN companion app (`apps/mobile`) for field/review use against the S3 mirror.
- Sync server for true multi-writer collaboration.
- Video support.
- Migration importer from legacy SPARCd S3 layout — only if a real user asks.

---

## 14. Open questions

These don't block writing v1 but should be answered as we build:

- **Bundled species list.** Ship a default global taxonomy (GBIF backbone, ITIS), or start each project empty and let users add? Lean: ship a curated default of N. American mammals + birds, editable per project.
- **Map tiles offline.** OSM raster tiles online by default; offer mbtiles import for field/offline use? Likely yes.
- **Deployment clustering heuristic.** Default gap (8h?) and per-camera vs per-folder grouping? Validate against a real dataset.
- **Conflict policy for `media` rows on import.** Same content hash, different filename/path — merge or duplicate? Lean: merge, surface a "this image was already imported in deployment X" hint.
- **License of the bundled species data.** Whatever we ship needs to be redistributable.
