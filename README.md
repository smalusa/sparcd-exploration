# sparcd-exploration

Turborepo monorepo for SPARC'd data exploration. Multiple apps and shared
packages live side by side and are orchestrated by
[Turborepo](https://turborepo.com).

The flagship app is `apps/sparcd-explorer` — a [marimo](https://marimo.io)
notebook that connects to the SPARC'd MinIO backend, bins camera locations
into H3 hexagons, and serves an interactive species-richness report. It also
exports to a static Pyodide bundle that runs entirely in the browser
(see [Static deploy](#static-deploy)).

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

<https://juli4ng.github.io/sparcd-exploration/>

The deployed page runs Python entirely in the visitor's browser. SPARC'd
credentials are entered in the form — there is no server-side secret. The
MinIO endpoint must permit CORS from the Pages origin for data fetches to
succeed.

## Background notes

See `architecture.md`, `architecture-pwa.md`, `codex-brief.md`,
`multi-user-question.md`, and `plan-p2p-no-s3.md` at the repo root.
