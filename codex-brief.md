# SPARC'd — Problem Brief

## Background

SPARC'd is an open-source camera-trap wildlife tagging tool used by researchers (originally at the University of Arizona's Jaguar and Ocelot Monitoring Project) to tag images with species, location, and timestamp metadata, then query the dataset for population/behavior analysis.

Two existing implementations:

- **Original Java desktop app**: https://github.com/CulverLab/sparcd — JavaFX, talks to S3-compatible storage (with legacy CyVerse iRODS support). Uses app-specific JSON for metadata; no standard format.
- **Current web port** (`sparcd-web`): Next.js 16 + React 19 frontend on top of a Flask Python backend. The backend does the real work — SQLite metadata DB, S3 (Minio SDK) access, EXIF reading via `exiftool` subprocess, EXIF *writing* via a bundled `ExifWriter.jar` subprocess, custom CamTrap CSV layer via `camtrap.v016` Python lib, multi-tenant auth (users table + Fernet-encrypted credentials + per-S3-endpoint workspaces). Roughly 11 Flask blueprints, ~1500-line monolithic `app/page.js`, MUI v7 + ArcGIS for maps, Docker compose for deploy.

## Core Workflow to Preserve

1. Researcher imports a batch of camera-trap images (often thousands per deployment).
2. Tags each image with species (from a 50–200 species sidebar with hotkeys), location/site, corrected timestamp.
3. Tagging sessions are hours long; the tagger is the surface users live in.
4. Queries the dataset by species, location, elevation, date, hour, day-of-week, activity-grouping interval, collection.
5. Exports results (CSV, image archives) for downstream population/behavior analysis.

## Problems With the Current Stack

1. **Always-online assumption.** Tagging is hours-long fieldwork-adjacent work; losing the network shouldn't lose the session. Both existing implementations require live S3 connectivity.
2. **Platform shell-outs.** The Python backend invokes `exiftool` and `ExifWriter.jar` as subprocesses to read/write image EXIF. Most fragile part of the system.
3. **Multi-tenant server with custom auth.** SQLite + Fernet-encrypted credentials + S3-per-endpoint exists only to support shared buckets. Adds significant complexity.
4. **Python/Docker dependency.** The web version requires running a Python Flask server in Docker. Operationally heavy for a tool that should be researcher-installable.
5. **No standard data format.** App-specific JSON locks researchers into SPARC'd; no interop with the broader camera-trap tooling ecosystem.

## Goal

A backend-less, TypeScript-based approach that:

- Drops the Python server and Docker entirely.
- Works offline (local-first); S3 becomes optional, used only for image-blob mirroring/backup.
- Uses **Camtrap-DP** (Camera Trap Data Package, a TDWG-maintained Frictionless Data standard) as the native data format, giving interop with the existing camera-trap ecosystem (camtraptor, Agouti, TRAPPER, GBIF IPT).
- Modern stack, single-language, distributable without server infrastructure.

## Key References

- Original Java app: https://github.com/CulverLab/sparcd
- Camtrap-DP standard: https://camtrap-dp.tdwg.org/
- Camtrap-DP example package: https://camtrap-dp.tdwg.org/example/00a2c20d/
- Frictionless Data spec: https://specs.frictionlessdata.io/

## Open Architectural Questions

1. **Runtime target** — pure PWA (zero-install, static-site deploy, sqlite-wasm + OPFS), Electron desktop, Tauri 2 (desktop + mobile via system WebView), or something else?
2. **Mobile** — is mobile support a v1 requirement, a future companion app, or out of scope? Camera-trap tagging is desktop-bound (hotkey-heavy, large image with zoom/pan, hours-long); mobile would be read-mostly (field lookup, site management, light review) at best.
3. **Image storage** — OPFS (sandboxed, ~60% of disk on modern browsers), persisted `FileSystemFileHandle` references (Chromium-only, zero-copy), or filesystem (Electron/Tauri)?
4. **Data model** — Camtrap-DP schema as the SQLite tables 1:1, or an internal model with Camtrap-DP as an export format?
5. **Multi-machine collaboration** — out of scope for v1, or solve via cloud-synced project folders (Dropbox/iCloud), or something else?
6. **Migration from existing SPARC'd S3 layout** — out of scope; treat as a fresh tool that produces Camtrap-DP from day one.

## Scope Decisions Already Made

- **Generic S3-compatible only.** No CyVerse iRODS in v1.
- **No migration importer.** Fresh tool. Existing users export from the old system if they want their data.
- **Offline-first.** Local persistence is canonical; S3 is a mirror.
- **Camtrap-DP is the data exchange format.**

## Constraints

- Single contributor working via fork (no upstream write access).
- Researcher audience — tool needs to be installable/usable by non-engineers.
- Open source; should be deployable without paid services (no API-key-bound maps, no required cloud backends).
