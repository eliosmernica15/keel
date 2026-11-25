/* Node tests for desktop-app/renderer-policy.js — no Electron, no deps.
   Run with node --test over this directory from the worktree root.
*/
import test from "node:test";
import assert from "node:assert/strict";
import { join } from "node:path";
import {
  resolveRenderer,
  RENDERER_MODES,
  ENV_KEYS,
  DEFAULT_RENDERER,
} from "../renderer-policy.js";

const RES = join("C:", "fake", "resources");
const UNIFIED_ROOT = join(RES, "fleet-next");
const UNIFIED_DEV_ROOT = join(RES, "fleet-next", ".next", "standalone");
const CUSTOM_UNIFIED = join("C:", "prepared", "standalone");
const LEGACY_ROOT = join(RES, "desktop", "ui");
const OLD_UI_ROOT = join(RES, "ui");
const SITE_ROOT = join(RES, "site");
const CUSTOM_UI = join("C:", "custom", "ui");

function fakeFs(files = []) {
  const present = new Set(files);
  return (p) => present.has(p);
}

function unifiedFiles(root) {
  return [
    join(root, "server.js"),
    join(root, ".next", "static"),
    join(root, "public"),
  ];
}

const UNIFIED = unifiedFiles(UNIFIED_ROOT);
const UNIFIED_DEV = unifiedFiles(UNIFIED_DEV_ROOT);
const CUSTOM_UNIFIED_FILES = unifiedFiles(CUSTOM_UNIFIED);
const LEGACY_FILE = join(LEGACY_ROOT, "index.html");
const OLD_UI_FILE = join(OLD_UI_ROOT, "index.html");
const MIRROR_FILE = join(SITE_ROOT, "app.html");
const MIRROR_INDEX_FILE = join(SITE_ROOT, "index.html");
const CUSTOM_UI_FILE = join(CUSTOM_UI, "index.html");

function resolve(files, env = {}) {
  return resolveRenderer({
    resourcesPath: RES,
    env,
    exists: fakeFs(files),
  });
}

function assertShape(result) {
  assert.deepEqual(Object.keys(result).sort(), ["mode", "reason", "uiDir"]);
  assert.ok(
    Object.values(RENDERER_MODES).includes(result.mode),
    `unexpected mode: ${result.mode}`,
  );
  assert.ok(
    result.uiDir === null || typeof result.uiDir === "string",
    "uiDir must be a string or null",
  );
  assert.equal(typeof result.reason, "string");
  assert.ok(result.reason.length > 0, "reason must not be empty");
}

// ---------------------------------------------------------------------------
// Defaults
// ---------------------------------------------------------------------------

test("default is unified when G1-G6-passed runtime is present", () => {
  assert.equal(DEFAULT_RENDERER, "unified");
  const result = resolve([...UNIFIED, LEGACY_FILE, MIRROR_FILE]);
  assertShape(result);
  assert.equal(result.mode, "unified");
  assert.equal(result.uiDir, UNIFIED_ROOT);
  assert.match(result.reason, /unified-default/);
  assert.doesNotMatch(result.reason, /site/i);
});

test("unified can still be selected explicitly", () => {
  const result = resolve([...UNIFIED, LEGACY_FILE], {
    [ENV_KEYS.RENDERER]: "unified",
  });
  assertShape(result);
  assert.equal(result.mode, "unified");
  assert.equal(result.uiDir, UNIFIED_ROOT);
  assert.match(result.reason, /unified-selected/);
});

test("default degrades to legacy when the unified runtime is absent", () => {
  const result = resolve([OLD_UI_FILE]);
  assertShape(result);
  assert.equal(result.mode, "legacy");
  assert.equal(result.uiDir, OLD_UI_ROOT);
  assert.match(result.reason, /legacy-default: unified runtime not present/);
});

test("explicit KEEL_RENDERER=legacy is the packaged rollback", () => {
  const result = resolve([...UNIFIED, LEGACY_FILE], {
    [ENV_KEYS.RENDERER]: "legacy",
  });
  assertShape(result);
  assert.equal(result.mode, "legacy");
  assert.equal(result.uiDir, LEGACY_ROOT);
  assert.match(result.reason, /legacy-selected|rollback/i);
});

test("standalone dev layout at fleet-next/.next/standalone counts as unified", () => {
  const result = resolve([...UNIFIED_DEV, LEGACY_FILE], {
    [ENV_KEYS.RENDERER]: "unified",
  });
  assertShape(result);
  assert.equal(result.mode, "unified");
  assert.equal(result.uiDir, UNIFIED_DEV_ROOT);
});

test("no assets at all means sidecar-bundled legacy, never mirror", () => {
  const result = resolve([]);
  assertShape(result);
  assert.equal(result.mode, "legacy");
  assert.equal(result.uiDir, null);
  assert.match(result.reason, /sidecar-bundled/);
  assert.notEqual(result.mode, "mirror");
});

// ---------------------------------------------------------------------------
// Explicit KEEL_RENDERER
// ---------------------------------------------------------------------------

test("KEEL_RENDERER=legacy explicitly selects desktop/ui", () => {
  const result = resolve([...UNIFIED, LEGACY_FILE], {
    [ENV_KEYS.RENDERER]: "legacy",
  });
  assertShape(result);
  assert.equal(result.mode, "legacy");
  assert.equal(result.uiDir, LEGACY_ROOT);
  assert.match(result.reason, /KEEL_RENDERER=legacy/);
});

test("KEEL_RENDERER=legacy with no static root uses sidecar-bundled UI", () => {
  const result = resolve([...UNIFIED], {
    [ENV_KEYS.RENDERER]: "legacy",
  });
  assertShape(result);
  assert.equal(result.mode, "legacy");
  assert.equal(result.uiDir, null);
  assert.match(result.reason, /sidecar-bundled/);
});

test("KEEL_RENDERER=unified selects the unified runtime when complete", () => {
  const result = resolve([...UNIFIED, LEGACY_FILE], {
    [ENV_KEYS.RENDERER]: "unified",
  });
  assertShape(result);
  assert.equal(result.mode, "unified");
  assert.equal(result.uiDir, UNIFIED_ROOT);
  assert.match(result.reason, /KEEL_RENDERER=unified/);
});

test("an incomplete unified runtime is not silently replaced by legacy", () => {
  const result = resolve([join(UNIFIED_ROOT, "server.js"), LEGACY_FILE], {
    [ENV_KEYS.RENDERER]: "unified",
  });
  assertShape(result);
  assert.equal(result.mode, "unified");
  assert.equal(result.uiDir, null, "host must show a failure, not start legacy");
  assert.match(result.reason, /unified-missing|unified-incomplete/);
  assert.match(result.reason, /no silent fallback/);
  assert.match(result.reason, /KEEL_RENDERER=legacy/);
});

test("missing unified assets with KEEL_UI_DIR set still fail (no static substitute)", () => {
  const result = resolve([LEGACY_FILE, CUSTOM_UI_FILE], {
    [ENV_KEYS.RENDERER]: "unified",
    [ENV_KEYS.UI_DIR]: CUSTOM_UI,
  });
  assertShape(result);
  assert.equal(result.mode, "unified");
  assert.equal(result.uiDir, null);
  assert.match(result.reason, /unified-missing/);
  assert.match(result.reason, /no silent fallback/);
});

test("rollback is an explicit KEEL_RENDERER=legacy selection, not an implicit fallback", () => {
  const result = resolve([LEGACY_FILE], {
    [ENV_KEYS.RENDERER]: "legacy",
  });
  assertShape(result);
  assert.equal(result.mode, "legacy");
  assert.equal(result.uiDir, LEGACY_ROOT);
  assert.match(result.reason, /legacy-selected/);
});

test("unsupported KEEL_RENDERER value falls back safely to legacy without echoing it", () => {
  const result = resolve([LEGACY_FILE], {
    [ENV_KEYS.RENDERER]: "totally-bogus-value",
  });
  assertShape(result);
  assert.equal(result.mode, "legacy");
  assert.equal(result.uiDir, LEGACY_ROOT);
  assert.match(result.reason, /invalid-renderer-selection/);
  assert.doesNotMatch(result.reason, /totally-bogus-value/);
});

test("KEEL_RENDERER values are trimmed and case-insensitive", () => {
  const result = resolve([LEGACY_FILE], {
    [ENV_KEYS.RENDERER]: "  LeGaCy  ",
  });
  assertShape(result);
  assert.equal(result.mode, "legacy");
  assert.equal(result.uiDir, LEGACY_ROOT);
});

// ---------------------------------------------------------------------------
// Mirror: explicit-only, never automatic
// ---------------------------------------------------------------------------

test("KEEL_UI_PROFILE=mirror selects the site diagnostic root", () => {
  const result = resolve([...UNIFIED, LEGACY_FILE, MIRROR_FILE], {
    [ENV_KEYS.UI_PROFILE]: "mirror",
  });
  assertShape(result);
  assert.equal(result.mode, "mirror");
  assert.equal(result.uiDir, SITE_ROOT);
  assert.match(result.reason, /KEEL_UI_PROFILE=mirror/);
});

test("site assets present without KEEL_UI_PROFILE never select mirror", () => {
  for (const files of [
    [MIRROR_FILE],
    [MIRROR_FILE, LEGACY_FILE],
    [MIRROR_FILE, ...UNIFIED, LEGACY_FILE],
  ]) {
    const result = resolve(files);
    assertShape(result);
    assert.notEqual(result.mode, "mirror", "mirror must never be automatic");
  }
});

test("KEEL_RENDERER=mirror alone is refused and does not enable mirror", () => {
  const result = resolve([MIRROR_FILE, LEGACY_FILE], {
    [ENV_KEYS.RENDERER]: "mirror",
  });
  assertShape(result);
  assert.equal(result.uiDir, null);
  assert.match(result.reason, /KEEL_UI_PROFILE=mirror/);
});

test("mirror requested with no site assets fails instead of falling back", () => {
  const result = resolve([...UNIFIED, LEGACY_FILE], {
    [ENV_KEYS.UI_PROFILE]: "mirror",
  });
  assertShape(result);
  assert.equal(result.mode, "mirror");
  assert.equal(result.uiDir, null);
  assert.match(result.reason, /mirror-missing/);
});

test("site/index.html alone is enough for the mirror diagnostic root", () => {
  const result = resolve([MIRROR_INDEX_FILE], {
    [ENV_KEYS.UI_PROFILE]: "mirror",
  });
  assertShape(result);
  assert.equal(result.mode, "mirror");
  assert.equal(result.uiDir, SITE_ROOT);
  assert.match(result.reason, /site\/index\.html/);
});

test("KEEL_UI_PROFILE value is case-insensitive and trimmed", () => {
  const result = resolve([MIRROR_FILE], {
    [ENV_KEYS.UI_PROFILE]: "  MIRROR ",
  });
  assertShape(result);
  assert.equal(result.mode, "mirror");
});

// ---------------------------------------------------------------------------
// Explicit static/unified dir overrides (old paths preserved)
// ---------------------------------------------------------------------------

test("KEEL_UI_DIR overrides legacy static root", () => {
  const result = resolve([LEGACY_FILE, CUSTOM_UI_FILE], {
    [ENV_KEYS.RENDERER]: "legacy",
    [ENV_KEYS.UI_DIR]: CUSTOM_UI,
  });
  assertShape(result);
  assert.equal(result.mode, "legacy");
  assert.equal(result.uiDir, CUSTOM_UI);
  assert.match(result.reason, /explicit-ui-dir|KEEL_UI_DIR override/);
});

test("invalid KEEL_UI_DIR is ignored and normal selection continues", () => {
  const bogus = join("C:", "bogus", "no-index-here");
  const result = resolve([LEGACY_FILE], {
    [ENV_KEYS.UI_DIR]: bogus,
  });
  assertShape(result);
  assert.equal(result.mode, "legacy");
  assert.equal(result.uiDir, LEGACY_ROOT);
  assert.doesNotMatch(result.reason, /bogus/);
});

test("KEEL_UI_DIR is honoured for the mirror diagnostic root", () => {
  const result = resolve([MIRROR_FILE, CUSTOM_UI_FILE], {
    [ENV_KEYS.UI_DIR]: CUSTOM_UI,
    [ENV_KEYS.UI_PROFILE]: "mirror",
  });
  assertShape(result);
  assert.equal(result.mode, "mirror");
  assert.equal(result.uiDir, CUSTOM_UI);
});

test("explicit KEEL_RENDERER=unified wins over KEEL_UI_DIR and the mirror profile", () => {
  const result = resolve([...UNIFIED, CUSTOM_UI_FILE, MIRROR_FILE], {
    [ENV_KEYS.RENDERER]: "unified",
    [ENV_KEYS.UI_DIR]: CUSTOM_UI,
    [ENV_KEYS.UI_PROFILE]: "mirror",
  });
  assertShape(result);
  assert.equal(result.mode, "unified");
  assert.equal(result.uiDir, UNIFIED_ROOT);
  assert.match(result.reason, /KEEL_UI_PROFILE=mirror ignored/);
});

test("explicit KEEL_RENDERER=legacy wins over the mirror profile", () => {
  const result = resolve([LEGACY_FILE, MIRROR_FILE], {
    [ENV_KEYS.RENDERER]: "legacy",
    [ENV_KEYS.UI_PROFILE]: "mirror",
  });
  assertShape(result);
  assert.equal(result.mode, "legacy");
  assert.equal(result.uiDir, LEGACY_ROOT);
  assert.match(result.reason, /KEEL_UI_PROFILE=mirror ignored/);
});

test("KEEL_RENDERER_UNIFIED_DIR selects a prepared standalone root", () => {
  const result = resolve([...UNIFIED, ...CUSTOM_UNIFIED_FILES, LEGACY_FILE], {
    [ENV_KEYS.RENDERER]: "unified",
    [ENV_KEYS.UNIFIED_DIR]: CUSTOM_UNIFIED,
  });
  assertShape(result);
  assert.equal(result.mode, "unified");
  assert.equal(result.uiDir, CUSTOM_UNIFIED);
});

test("incomplete KEEL_RENDERER_UNIFIED_DIR fails without echoing the path", () => {
  const secretDir = join("C:", "TOP-SECRET-UI", "standalone");
  const result = resolve([LEGACY_FILE], {
    [ENV_KEYS.UNIFIED_DIR]: secretDir,
    [ENV_KEYS.RENDERER]: "unified",
  });
  assertShape(result);
  assert.equal(result.uiDir, null);
  assert.match(result.reason, /unified-incomplete/);
  assert.doesNotMatch(result.reason, /TOP-SECRET-UI/);
});

// ---------------------------------------------------------------------------
// Reason hygiene and input robustness
// ---------------------------------------------------------------------------

test("reason strings never contain credentials, env values or absolute paths", () => {
  const secretResources = join("C:", "secret-user", "TOP-SECRET-RESOURCE");
  const secretDir = join("C:", "secret-user", "TOP-SECRET-UI");
  const cases = [
    { env: {}, files: UNIFIED },
    { env: {}, files: [LEGACY_FILE] },
    { env: {}, files: [] },
    { env: { [ENV_KEYS.UI_PROFILE]: "mirror" }, files: [MIRROR_FILE] },
    { env: { [ENV_KEYS.UI_PROFILE]: "mirror" }, files: [] },
    { env: { [ENV_KEYS.RENDERER]: "unified" }, files: [LEGACY_FILE] },
    { env: { [ENV_KEYS.RENDERER]: "WRONG-VALUE" }, files: [LEGACY_FILE] },
    { env: { [ENV_KEYS.RENDERER]: "mirror" }, files: [MIRROR_FILE] },
    {
      env: {
        [ENV_KEYS.RENDERER]: "legacy",
        [ENV_KEYS.UI_PROFILE]: "mirror",
      },
      files: [LEGACY_FILE, MIRROR_FILE],
    },
  ];

  for (const { env, files } of cases) {
    const withSecrets = {
      ...env,
      KEEL_TOKEN: "SUPER-SECRET-BRIDGE-TOKEN",
      KEEL_API_KEY: "SUPER-SECRET-API-KEY",
      KEEL_UI_DIR: secretDir,
    };
    const result = resolveRenderer({
      resourcesPath: secretResources,
      env: withSecrets,
      exists: fakeFs(files),
    });
    assertShape(result);
    for (const needle of [
      "SUPER-SECRET-BRIDGE-TOKEN",
      "SUPER-SECRET-API-KEY",
      "TOP-SECRET-RESOURCE",
      "TOP-SECRET-UI",
      "secret-user",
      "?",
      "t=",
    ]) {
      assert.ok(
        !result.reason.includes(needle),
        `reason leaked ${needle}: ${result.reason}`,
      );
    }
  }
});

test("missing resourcesPath produces a clear failure reason", () => {
  const result = resolveRenderer({
    resourcesPath: "",
    env: { [ENV_KEYS.RENDERER]: "unified" },
    exists: fakeFs([]),
  });
  assertShape(result);
  assert.equal(result.uiDir, null);
  assert.match(result.reason, /resourcesPath not provided/);
});

test("all three modes are reachable and the shape is stable", () => {
  const modes = new Set();
  const scenarios = [
    [...UNIFIED, LEGACY_FILE, MIRROR_FILE],
    [LEGACY_FILE],
    [MIRROR_FILE],
    [],
  ];
  const envs = [
    {},
    { [ENV_KEYS.RENDERER]: "unified" },
    { [ENV_KEYS.RENDERER]: "legacy" },
    { [ENV_KEYS.UI_PROFILE]: "mirror" },
  ];
  for (const files of scenarios) {
    for (const env of envs) {
      modes.add(resolve(files, env).mode);
    }
  }
  assert.deepEqual([...modes].sort(), ["legacy", "mirror", "unified"]);
});
