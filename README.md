# sparcd-rewrite

Turborepo monorepo for the SPARC'd rewrite. Multiple apps and shared packages
live side by side and are orchestrated by [Turborepo](https://turborepo.com).

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

## Architecture notes

See `architecture.md`, `architecture-pwa.md`, `codex-brief.md`,
`multi-user-question.md`, and `plan-p2p-no-s3.md` at the repo root.
