import { chmod, cp, lstat, readdir, rm } from "node:fs/promises";
import { spawnSync } from "node:child_process";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const appRoot = join(here, "..");
const src = join(appRoot, "pages");
const dest = join(appRoot, "dist");

async function makeWritable(path) {
  const info = await lstat(path).catch(() => null);
  if (!info) {
    return;
  }

  try {
    await chmod(path, info.isDirectory() ? 0o777 : 0o666);
  } catch {
    return;
  }

  const entries = await readdir(path, { withFileTypes: true }).catch(() => []);
  for (const entry of entries) {
    await makeWritable(join(path, entry.name));
  }
}

await makeWritable(dest);
if (process.platform === "win32") {
  spawnSync("attrib", ["-R", `${dest}\\*`, "/S", "/D"], { stdio: "ignore" });
}
await rm(dest, { recursive: true, force: true, maxRetries: 3, retryDelay: 100 });
await cp(src, dest, { recursive: true });
