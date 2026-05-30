# sparcd-exploration — context for Codex

## What this project is

A workspace for small, single-purpose, mostly-static tools that work
**alongside** [SPARC'd](https://github.com/CulverLab/sparcd-web). SPARC'd is
the system of record; the apps here read from it and add focused views on
top.

## Framing

Use language like *alongside*, *complement*, *focused tool*, *static tool*,
*exploration*. Describe what each tool **is** and **does**, not what it
relates to in other systems.

## How tools are organized

- Each `apps/<name>/` is **one tool that does one thing well**. When a new
  need appears, add a new app — keep each one tight.
- Prefer designs that can ship as a **static bundle** (Pyodide / WASM in the
  browser, prebuilt data files, signed S3 URLs) — no server-side state.
- Per-feature optimization beats shared abstractions. It's fine for two apps
  to duplicate small pieces of logic if it lets each one stay tight.

## Toolchain

- **pnpm 10** + **Turborepo 2** at the root — JS workspaces and task pipeline
- **uv** for any Python app's environment (each app owns its `pyproject.toml`
  + `.venv` under `apps/<name>/`)
- On Windows, use the global `pnpm` and `uv` commands installed with
  `winget`. If a running shell cannot see a newly installed command yet,
  restart the shell so it picks up the updated user `Path`.
- **marimo** for notebook-style exploration apps; pair with the
  [`marimo-pair`](https://github.com/marimo-team/marimo-pair) Codex
  plugin for live-kernel collaboration. Notebooks open with
  `--watch --no-token` so the plugin auto-discovers.

## Working with the SPARC'd backend

- Data lives in **MinIO/S3** (`wildcats.sparcd.arizona.edu`) and a small
  SQLite app-state DB. Object layout is **Camtrap-DP-flavored** CSVs per
  upload: `deployments.csv`, `media.csv`, `observations.csv`, plus image
  files and a `UploadMeta.json`.
- Treat the backend as **read-only**. All operations should be
  `list_buckets`, `list_objects`, `get_object`, `stat_object`, or
  `presigned_get_object` (URL signing).
- Credentials live in `apps/<name>/.env` (gitignored). The endpoint can be a
  bare host or a full URL — the loader normalizes either.

### Access scope

Authorized scope is the **Educational Test collection**
(`sparcd-8dbd9c43-5c3d-411d-8778-617d4693c69b`). Stay within that bucket
unless the user explicitly authorizes a wider read for a specific task —
don't grep, list, or fetch outside it on a hunch.

## Style preferences

- Tight, direct prose. No filler, no trailing summaries when a diff speaks
  for itself.
- For notebooks: each cell should do one thing. Use `mo.md(...)` for
  human-facing context, raw expressions for data displays.
- Don't add fallbacks, validation, or compatibility shims for cases that
  can't happen in practice. Trust data shapes we've already verified.
- Don't write code comments that just restate the code. Reserve comments
  for non-obvious *why*.

## Pointers

- `README.md` — quick start and layout
- `apps/sparcd-explorer/README.md` — the first focused tool (map +
  thumbnails + tags for the Educational Test collection)
- Upstream code: <https://github.com/CulverLab/sparcd-web>
