# sparcd-exploration

A workspace for building small, focused, mostly-static tools that work
alongside [SPARC'd](https://github.com/CulverLab/sparcd-web) — each one
tuned end-to-end for a single feature.

The first such tool is `apps/sparcd-explorer` — a [marimo](https://marimo.io)
notebook that connects to the SPARC'd MinIO backend, bins camera locations
into H3 hexagons, and serves an interactive species-richness report. It also
exports to a static Pyodide bundle that runs entirely in the browser
(see [Static deploy](#static-deploy)).

## Approach

- **Alongside SPARC'd.** SPARC'd is the system of record; the tools here
  read from it and add focused views on top.
- **One tool, one job.** Each app in `apps/` solves a single concrete user
  problem (a specific report, a specific view, a specific export). When a new
  need shows up, we add a new app.
- **Static where possible.** Prefer designs that can ship as a static bundle
  (Pyodide / WASM, prebuilt data files, signed S3 URLs). Each tool stays
  cheap to host, easy to share, and free of server-side state.
- **Optimize per feature.** With a narrow scope per app, we pick the best
  primitives for that job — data model, layout, interactions — without
  compromise for anything else.

## Layout

```
apps/
  sparcd-explorer/   # marimo notebooks for data exploration (Python, uv)
packages/            # shared TS/JS libraries (none yet)
```

## Toolchain

- **Node** ≥ 20 + **pnpm** 10 — workspace + task runner
- **Turborepo** — pipeline orchestration across apps/packages
- **uv** — Python env/deps for any Python-based app (e.g. marimo)

## Quick start

```sh
pnpm install                                  # installs turbo and JS workspaces
pnpm --filter @sparcd/sparcd-explorer install:py   # uv sync for the marimo app
pnpm dev --filter @sparcd/sparcd-explorer     # marimo edit --watch
```

Or run every app's `dev` task at once:

```sh
pnpm dev
```

## Adding a new app

1. `mkdir apps/<name>`
2. Add a `package.json` with `name`, `private: true`, and at least `dev` /
   `build` scripts. Python apps wrap `uv run …` in their npm scripts.
3. `pnpm install` to pick it up via the workspace.
4. Tasks defined in [`turbo.json`](./turbo.json) (`dev`, `build`, `lint`,
   `start`, `check`, `test`) will run across whichever apps implement them.

## Static deploy

`.github/workflows/pages.yml` builds the marimo notebook into a static
Pyodide bundle and publishes it via GitHub Pages on every push that touches
`apps/sparcd-explorer/**`. Live at:

<https://smalusa.github.io/sparcd-exploration/>

The deployed page runs Python entirely in the visitor's browser. SPARC'd
credentials are entered in the form — there is no server-side secret. The
MinIO endpoint must permit CORS from the Pages origin for data fetches to
succeed.

## Background notes

`architecture.md`, `architecture-pwa.md`, `codex-brief.md`,
`multi-user-question.md`, and `plan-p2p-no-s3.md` are early exploration
notes kept for reference. The current direction is the "Approach" section
above.
