import { execFileSync } from "node:child_process";
import path from "node:path";
import { expect, test } from "@playwright/test";

/**
 * Marketing-page integrity. The frontend finalization allowlist permits
 * distribution/PWA files and test scaffolding under keel/site to change; every
 * other tracked site file must stay byte-identical to origin/main 35fb2b8.
 * Comparison is at the git-blob level (filters applied), which is the
 * repository's definition of byte-identical.
 */
const BASELINE = process.env.KEEL_BASELINE ?? "35fb2b8abfd784393b2b252e2b9e2927aba817dd";
const ROOT = path.resolve(__dirname, "../../../..");

const ALLOWED_EXACT = new Set([
  "keel/site/download.html",
  "keel/site/download.json",
  "keel/site/manifest.webmanifest",
  "keel/site/sw.js",
  "keel/site/vercel.json",
  "keel/site/app.html", // contextual download-link line only
  "keel/site/api/download-manifest.js",
  "keel/site/ui/download.js",
  "keel/site/ui/download-ux.css",
]);
const ALLOWED_PREFIX = ["keel/site/tests/"];

function git(args: string[]): string {
  return execFileSync("git", args, { cwd: ROOT, encoding: "utf8" });
}

function isAllowed(file: string): boolean {
  return ALLOWED_EXACT.has(file) || ALLOWED_PREFIX.some((p) => file.startsWith(p));
}

test("no site file outside the frontend allowlist changed versus baseline", () => {
  const changed = git(["diff", "--name-only", BASELINE, "--", "keel/site"])
    .split("\n").map((s) => s.trim()).filter(Boolean);
  const offenders = changed.filter((f) => !isAllowed(f));
  expect(offenders, `marketing/asset drift: ${JSON.stringify(offenders)}`).toEqual([]);
});

test("every protected site file is byte-identical to the baseline blob", () => {
  const baselineFiles = git(["ls-tree", "-r", "--name-only", BASELINE, "--", "keel/site"])
    .split("\n").map((s) => s.trim()).filter(Boolean).filter((f) => !isAllowed(f));

  const drift: string[] = [];
  for (const file of baselineFiles) {
    const baselineHash = git(["rev-parse", `${BASELINE}:${file}`]).trim();
    let currentHash: string;
    try {
      currentHash = git(["hash-object", "--path", file, path.join(ROOT, file)]).trim();
    } catch {
      drift.push(`${file}: missing in worktree`);
      continue;
    }
    if (currentHash !== baselineHash) drift.push(`${file}: ${baselineHash} -> ${currentHash}`);
  }
  expect(drift, `protected files differ from ${BASELINE.slice(0, 7)}: ${JSON.stringify(drift)}`).toEqual([]);
  // Guard against an empty scan silently passing.
  expect(baselineFiles.length).toBeGreaterThan(20);
});

test("no untracked marketing page was added under keel/site", () => {
  const untracked = git(["ls-files", "--others", "--exclude-standard", "--", "keel/site"])
    .split("\n").map((s) => s.trim()).filter(Boolean);
  const marketing = untracked.filter((f) => /\.html?$/i.test(f) && !isAllowed(f));
  expect(marketing, `untracked marketing pages: ${JSON.stringify(marketing)}`).toEqual([]);
});
