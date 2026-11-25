/* Keel Desktop — renderer selection policy.

   Pure, dependency-free decision module used by the Electron host. It answers
   one question only: which renderer root should the host use, given a
   resourcesPath and an env object? It never starts a server, never reads a
   credential, and never mutates process state.

   Contract (parent assignment):
     resolveRenderer({ resourcesPath, env }) ->
       { mode: "unified" | "legacy" | "mirror",
         uiDir: string | null,
         reason: string }

   Invariants:
   - DEFAULT_RENDERER is "unified" after gates G1-G6 passed with a real
     packaged EXE (2026-11-25). Rollback is explicit KEEL_RENDERER=legacy; if
     the unified runtime is absent, default degrades to legacy with a reason.
   - "legacy" (desktop/ui, then old ui/) stays intact and is explicitly
     selectable with KEEL_RENDERER=legacy. A null uiDir in legacy mode means
     "let the frozen sidecar serve its bundled desktop/ui" (Agent A §4.1).
   - "mirror" (browser-only site/) is reachable ONLY via the explicit
     diagnostic switch KEEL_UI_PROFILE=mirror. It is never an automatic
     default and never implied by KEEL_RENDERER=mirror.
   - No silent fallback: when unified is explicitly requested and its assets
     are missing, uiDir is null (host must show a clear failure). The operator
     explicitly selects KEEL_RENDERER=legacy to roll back; there is no
     hidden fallback variable.
   - reason strings never contain env values, absolute paths or credentials.
     They use fixed labels and resource-relative asset markers only.

   The optional `exists` input is an injected predicate (path -> boolean) so
   the whole decision is testable in plain Node. With no injection it uses
   fs.existsSync. Callers may also pass only { resourcesPath, env }.
*/
import { existsSync } from "node:fs";
import { join } from "node:path";

export const RENDERER_MODES = Object.freeze({
  UNIFIED: "unified",
  LEGACY: "legacy",
  MIRROR: "mirror",
});

/* Cutover 2026-11-25: G1-G6 passed with a real packaged EXE, so the single
   default constant is now UNIFIED. KEEL_RENDERER=legacy remains the rollback. */
export const DEFAULT_RENDERER = RENDERER_MODES.UNIFIED;

export const ENV_KEYS = Object.freeze({
  RENDERER: "KEEL_RENDERER",
  UI_PROFILE: "KEEL_UI_PROFILE",
  UI_DIR: "KEEL_UI_DIR",
  UNIFIED_DIR: "KEEL_RENDERER_UNIFIED_DIR",
});

// Resource-relative roots. uiDir is a DIRECTORY, never a marker file.
// No absolute path is ever put into a reason string.
export const ASSET_MARKERS = Object.freeze({
  unifiedRoots: Object.freeze([
    "fleet-next",
    "fleet-next/.next/standalone",
    "unified",
  ]),
  unifiedFiles: Object.freeze(["server.js", ".next/static", "public"]),
  legacyRoots: Object.freeze(["desktop/ui", "ui"]),
  legacyFile: "index.html",
  mirrorRoot: "site",
  mirrorFiles: Object.freeze(["app.html", "index.html"]),
});

function safeExists(path) {
  try {
    return existsSync(path);
  } catch {
    return false;
  }
}

function readEnv(env) {
  const source = env && typeof env === "object" ? env : {};
  const lowered = (key) => {
    const value = source[key];
    if (value === undefined || value === null) return "";
    return String(value).trim().toLowerCase();
  };
  return {
    renderer: lowered(ENV_KEYS.RENDERER),
    uiProfile: lowered(ENV_KEYS.UI_PROFILE),
    // Kept only for filesystem lookup; never echoed into a reason.
    uiDir: typeof source[ENV_KEYS.UI_DIR] === "string"
      ? source[ENV_KEYS.UI_DIR]
      : "",
    unifiedDir: typeof source[ENV_KEYS.UNIFIED_DIR] === "string"
      ? source[ENV_KEYS.UNIFIED_DIR]
      : "",
  };
}

function decision(mode, uiDir, reason) {
  return { mode, uiDir: uiDir || null, reason };
}

function failure(mode, reason) {
  return decision(mode, null, reason);
}

function validStaticOverride(dir, exists) {
  return dir && exists(join(dir, ASSET_MARKERS.legacyFile)) ? dir : null;
}

function findUnified(resourcesPath, e, exists) {
  const dirs = e.unifiedDir
    ? [e.unifiedDir]
    : ASSET_MARKERS.unifiedRoots.map((root) => join(resourcesPath, root));
  for (const dir of dirs) {
    if (!dir) continue;
    const complete = ASSET_MARKERS.unifiedFiles.every((marker) =>
      exists(join(dir, marker)));
    if (complete) return dir;
  }
  return null;
}

function findLegacy(resourcesPath, exists, override) {
  if (override) return { uiDir: override, label: "KEEL_UI_DIR override" };
  if (!resourcesPath) return null;
  for (const root of ASSET_MARKERS.legacyRoots) {
    const uiDir = join(resourcesPath, root);
    if (exists(join(uiDir, ASSET_MARKERS.legacyFile))) {
      return { uiDir, label: `${root}/${ASSET_MARKERS.legacyFile}` };
    }
  }
  return null;
}

function findMirror(resourcesPath, exists, override) {
  if (override) return { uiDir: override, label: "KEEL_UI_DIR override" };
  if (!resourcesPath) return null;
  const root = ASSET_MARKERS.mirrorRoot;
  for (const marker of ASSET_MARKERS.mirrorFiles) {
    if (exists(join(resourcesPath, root, marker))) {
      return { uiDir: join(resourcesPath, root), label: `${root}/${marker}` };
    }
  }
  return null;
}

function legacyResult(root, reasonPrefix) {
  if (!root) {
    return decision(
      RENDERER_MODES.LEGACY,
      null,
      `${reasonPrefix}: no ${ASSET_MARKERS.legacyRoots.join("/index.html or ")}/index.html under resourcesPath; sidecar-bundled UI will be used`,
    );
  }
  return decision(
    RENDERER_MODES.LEGACY,
    root.uiDir,
    `${reasonPrefix}; using ${root.label}`,
  );
}

/**
 * Resolve the renderer root for the packaged Electron host.
 *
 * @param {object} input
 * @param {string} input.resourcesPath  Electron process.resourcesPath.
 * @param {object} [input.env]          Env object (defaults to process.env).
 * @param {(path:string)=>boolean} [input.exists]  Injected fs predicate.
 * @returns {{mode: "unified"|"legacy"|"mirror", uiDir: string|null, reason: string}}
 */
export function resolveRenderer(input = {}) {
  const resourcesPath = typeof input.resourcesPath === "string"
    ? input.resourcesPath
    : "";
  const env = input.env === undefined ? process.env : input.env;
  const exists = typeof input.exists === "function" ? input.exists : safeExists;
  const e = readEnv(env);
  const noRes = resourcesPath ? "" : "; resourcesPath not provided";
  const override = validStaticOverride(e.uiDir, exists);
  const unifiedMissingReason = e.unifiedDir
    ? "unified-incomplete: KEEL_RENDERER_UNIFIED_DIR is not a complete standalone runtime (server.js, .next/static, public required); no silent fallback"
    : `unified-missing: ${ASSET_MARKERS.unifiedFiles.join(", ")} not all found under fleet-next; no silent fallback (explicitly set KEEL_RENDERER=legacy to roll back)`;
  // Explicit KEEL_RENDERER always wins over the mirror diagnostic alias.
  const explicitNote = e.uiProfile === "mirror"
    ? "; KEEL_UI_PROFILE=mirror ignored (explicit KEEL_RENDERER wins)"
    : "";

  // 1. Explicit KEEL_RENDERER. Mirror is the exception: the contract permits
  //    mirror ONLY via KEEL_UI_PROFILE=mirror.
  if (e.renderer) {
    if (e.renderer === "mirror") {
      return failure(
        RENDERER_MODES.MIRROR,
        `mirror-requires-explicit-profile: mirror mode requires KEEL_UI_PROFILE=mirror${noRes}`,
      );
    }

    if (e.renderer === "legacy") {
      return legacyResult(
        findLegacy(resourcesPath, exists, override),
        `legacy-selected: KEEL_RENDERER=legacy${explicitNote}`,
      );
    }

    if (e.renderer === "unified") {
      // KEEL_UI_DIR is deliberately ignored here: a static legacy dir must
      // never silently replace an explicitly requested unified renderer.
      const uiDir = findUnified(resourcesPath, e, exists);
      if (uiDir) {
        return decision(
          RENDERER_MODES.UNIFIED,
          uiDir,
          `unified-selected: KEEL_RENDERER=unified; complete standalone runtime found${explicitNote}`,
        );
      }
      return failure(
        RENDERER_MODES.UNIFIED,
        unifiedMissingReason + explicitNote + noRes,
      );
    }

    // Invalid value: safe legacy (Agent A §4.2), reason never echoes the value.
    return legacyResult(
      findLegacy(resourcesPath, exists, override),
      `invalid-renderer-selection: KEEL_RENDERER must be unified or legacy; using legacy${explicitNote}`,
    );
  }

  // 2. Explicit mirror diagnostic alias.
  if (e.uiProfile === "mirror") {
    const mirror = findMirror(resourcesPath, exists, override);
    if (!mirror) {
      return failure(
        RENDERER_MODES.MIRROR,
        `mirror-missing: ${ASSET_MARKERS.mirrorFiles.join(" or ")} not found under site${noRes}`,
      );
    }
    return decision(
      RENDERER_MODES.MIRROR,
      mirror.uiDir,
      `mirror-selected: KEEL_UI_PROFILE=mirror; using ${mirror.label}`,
    );
  }

  // 3. Automatic default. A static KEEL_UI_DIR cannot silently replace the
  //    unified runtime (Agent A §4.2: override ignored for unified).
  if (DEFAULT_RENDERER === RENDERER_MODES.UNIFIED) {
    const uiDir = findUnified(resourcesPath, e, exists);
    if (uiDir) {
      return decision(
        RENDERER_MODES.UNIFIED,
        uiDir,
        "unified-default: complete standalone runtime found",
      );
    }
    return legacyResult(
      findLegacy(resourcesPath, exists, override),
      "legacy-default: unified runtime not present under resourcesPath",
    );
  }

  return legacyResult(
    findLegacy(resourcesPath, exists, override),
    `default-renderer: ${DEFAULT_RENDERER}; set KEEL_RENDERER=unified to opt in`,
  );
}

export default resolveRenderer;
