# sparcd-explorer

A focused, mostly-static exploration tool that reads from the SPARC'd MinIO
backend and renders interactive views of camera-trap data. One of the
single-purpose tools under `sparcd-exploration`.

## Setup

```sh
# from repo root
pnpm install                  # installs turbo
cd apps/sparcd-explorer
pnpm install:py               # → uv sync (creates .venv with marimo + deps)
```

## Run

From the repo root:

```sh
pnpm dev --filter @sparcd/sparcd-explorer    # marimo edit --watch
pnpm start --filter @sparcd/sparcd-explorer  # marimo run (read-only app mode)
pnpm build --filter @sparcd/sparcd-explorer  # export static WASM app to dist/
```

Or from this directory:

```sh
pnpm dev      # marimo edit notebooks/hello.py --watch
pnpm start    # marimo run notebooks/hello.py
```

## Static deployment

GitHub Pages deploys the WASM export from `notebooks/hello.py`. The notebook
keeps its browser dependencies in the PEP 723 header at the top of the file,
so local `pnpm build` and the Pages workflow export the same source notebook.
Serve `dist/` over HTTP to preview the static bundle.

## Agent workflow

Use the [marimo-pair](https://github.com/marimo-team/marimo-pair) Claude Code
plugin for live, two-way pairing — the agent runs cells in the active kernel
and sees results, instead of just editing files on disk.

Install once in Claude Code:

```
/plugin marketplace add marimo-team/marimo-pair
/plugin install marimo-pair@marimo-pair
```

The `--no-token` flag in the `dev` / `start` scripts lets marimo-pair
auto-discover the running server.

`--watch` is still on, so file-based edits (any tool writing to
`notebooks/*.py`) also reload in the browser.

See: <https://marimo.io/blog/claude-code>

## Notebooks

- `notebooks/hello.py` — starter / template
- `notebooks/sparcd_preview.py` — connect to the SPARC'd MinIO/S3 + (optional)
  SQLite backends and preview buckets, objects, and tables

## Connecting to SPARC'd data

The SPARC'd backend ([CulverLab/sparcd-web](https://github.com/CulverLab/sparcd-web))
stores data in two places: a MinIO/S3 object store (image collections, uploads)
and a SQLite app-state DB. Credentials go in a local `.env`:

```sh
cp .env.example .env
$EDITOR .env   # fill in SPARCD_S3_ENDPOINT, access/secret keys, etc.
```

Then run the preview notebook:

```sh
pnpm preview                                         # from this dir
pnpm preview --filter @sparcd/sparcd-explorer        # from repo root
```

`.env` is gitignored. You can also override values in the marimo form at the
top of the notebook for ad-hoc connections.
