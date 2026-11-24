import { test as base, expect, type Page } from "@playwright/test";

/**
 * Onboarding fixtures.
 *
 * Every `/api/bridge/*` call is intercepted and answered with a REAL-SHAPED
 * payload copied from the verified backend routes in
 * `keel/src/keel/fleet/routes.py`. No real provider key, account or paid
 * service is used. The strict console gate and the hydration-warning gate
 * fail the test at teardown — no silent browser noise is tolerated.
 */

export const TEST_KEY = "sk-ant-not-a-real-key-7Qw9";
export const TEST_PATH = "C:\\Work\\app";
export const TEST_PROVIDER = "anthropic";
export const MASKED_HINT = "a1b2";

export interface BridgeCall {
  method: string;
  path: string;
  body: unknown;
}

export interface BridgeOptions {
  credential: "success" | "failure";
  save: "success" | "failure";
  projects: Array<{ id: string; name: string; path: string; trusted: boolean }>;
}

export interface BridgeFixture {
  calls: BridgeCall[];
  options: BridgeOptions;
  setOptions: (patch: Partial<BridgeOptions>) => void;
  callsMatching: (method: string, path: string) => BridgeCall[];
}

const PROVIDERS = [
  {
    name: TEST_PROVIDER, configured: false, key_source: null, key_hint: null,
    default_model: "claude-sonnet-4-5", base_url: "https://api.anthropic.com",
    opt_in: true, notes: "AnthropicMessages", session: false,
  },
  {
    name: "openai", configured: false, key_source: null, key_hint: null,
    default_model: "gpt-4o-mini", base_url: "https://api.openai.com/v1",
    opt_in: false, notes: "OpenAIChat", session: false,
  },
];

const MODELS = ["claude-sonnet-4-5", "claude-opus-4-1", "claude-haiku-4-5"];

const SKILLS = [
  {
    name: "keel-bundled-review", description: "Bundled code review helper",
    scope: "bundled", trusted: true, injection_suspects: 0,
  },
  {
    name: "user-notes", description: "Personal note-taking instructions",
    scope: "user", trusted: false, injection_suspects: 0,
  },
];

const SERVERS = [
  {
    id: "github", name: "github", transport: "stdio", scope: "user",
    command: "npx -y @modelcontextprotocol/server-github",
  },
];

const DEFAULTS: BridgeOptions = {
  credential: "success",
  save: "success",
  projects: [],
};

export { expect };

export const test = base.extend<{
  consoleErrors: string[];
  hydrationWarnings: string[];
  bridge: BridgeFixture;
}>({
  consoleErrors: async ({ page, bridge }, use) => {
    const errors: string[] = [];
    page.on("pageerror", (error) => errors.push(`pageerror: ${error.message}\n${error.stack ?? ""}`));
    page.on("console", (message) => {
      if (message.type() === "error") {
        const loc = message.location();
        const text = message.text();
        // A deliberately rejected key is answered with HTTP 400 by the real
        // bridge, and Chromium logs that network status as one resource error.
        // It is the single expected console line in the failure scenario; every
        // other console error still fails the test.
        if (bridge.options.credential === "failure" &&
            /status of 400/.test(text) && /providers\/credential/.test(loc.url)) return;
        errors.push(`console.error: ${text} @ ${loc.url}:${loc.lineNumber + 1}:${loc.columnNumber + 1}`);
      }
    });
    await use(errors);
    expect(errors, `The browser reported errors:\n${errors.join("\n") || "(none)"}`).toEqual([]);
  },

  hydrationWarnings: async ({ page }, use) => {
    const warnings: string[] = [];
    const hydration = /hydrat|did not match|server rendered html|text content does not match|server.*client/i;
    page.on("console", (message) => {
      const text = message.text();
      if (hydration.test(text)) {
        const loc = message.location();
        warnings.push(`${message.type()}: ${text} @ ${loc.url}:${loc.lineNumber + 1}`);
      }
    });
    page.on("pageerror", (error) => {
      if (hydration.test(error.message)) warnings.push(`pageerror: ${error.message}`);
    });
    await use(warnings);
    expect(warnings, `Hydration warnings:\n${warnings.join("\n") || "(none)"}`).toEqual([]);
  },

  bridge: async ({ page }, use) => {
    const fixture: BridgeFixture = {
      calls: [],
      options: { ...DEFAULTS },
      setOptions: (patch) => { fixture.options = { ...fixture.options, ...patch }; },
      callsMatching: (method, path) => fixture.calls.filter(
        (c) => c.method === method && c.path === path,
      ),
    };

    await page.route("**/api/bridge/**", async (route) => {
      const request = route.request();
      const url = new URL(request.url());
      const path = url.pathname.replace(/^\/api\/bridge\/?/, "");
      const method = request.method();
      let body: unknown = null;
      const raw = request.postData();
      if (raw) { try { body = JSON.parse(raw); } catch { body = raw; } }
      fixture.calls.push({ method, path, body });

      const json = (data: unknown, status = 200) =>
        route.fulfill({ status, contentType: "application/json", body: JSON.stringify(data) });

      // Cowork mounts underneath the overlay and opens the live SSE stream.
      // Answer it as a real, finite event-stream response (no ERR_FAILED noise).
      if (path === "events") {
        await route.fulfill({
          status: 200,
          headers: {
            "content-type": "text/event-stream; charset=utf-8",
            "cache-control": "no-cache",
          },
          body: ": ping\n\n",
        });
        return;
      }

      if (method === "GET" && path === "providers") {
        return json({ providers: PROVIDERS, session_keys: [] });
      }
      if (method === "GET" && path === "projects") {
        return json({ projects: fixture.options.projects });
      }
      if (method === "POST" && path === "providers/catalog") {
        const name = String((body as { name?: unknown } | null)?.name ?? TEST_PROVIDER);
        return json({
          ok: true, provider: name, source: "offline", catalog_version: "2026-11-24",
          models: MODELS, model_count: MODELS.length,
        });
      }
      if (method === "POST" && path === "providers/credential") {
        if (fixture.options.credential === "failure") {
          return json({
            ok: false, error: "invalid_key",
            detail: "Key rejected by provider: invalid x-api-key",
          }, 400);
        }
        return json({
          ok: true, provider: TEST_PROVIDER, models: MODELS, model_count: MODELS.length,
          models_meta: [], key_source: "session",
          note: "held for this process only; nothing was written to disk. Restart the bridge to forget.",
        });
      }
      if (method === "POST" && path === "providers/save") {
        if (fixture.options.save === "failure") {
          return json({ ok: false, error: "not_saved", detail: "Local save was refused" }, 400);
        }
        return json({
          ok: true, provider: TEST_PROVIDER, models: MODELS, model_count: MODELS.length,
          models_meta: [], hint: MASKED_HINT,
          note: "saved to ~/.keel/settings.json (this machine only) and applied to this bridge process. Shell env vars still take precedence.",
        });
      }
      if (method === "POST" && path === "projects") {
        const p = (body as { path?: unknown } | null)?.path ?? TEST_PATH;
        const project = { id: "p1", name: "app", path: String(p), trusted: false };
        fixture.options.projects = [project, ...fixture.options.projects];
        return json({ project }, 201);
      }
      if (method === "POST" && /^projects\/[^/]+\/trust$/.test(path)) {
        const trusted = Boolean((body as { trusted?: unknown } | null)?.trusted);
        const project = { id: "p1", name: "app", path: TEST_PATH, trusted };
        fixture.options.projects = fixture.options.projects.map((p) => p.id === "p1" ? project : p);
        return json({ project });
      }
      if (method === "GET" && path === "skills") return json({ skills: SKILLS });
      if (method === "GET" && path === "mcp/servers") return json({ servers: SERVERS });
      if (method === "GET" && path === "bots") return json({ bots: [] });
      if (method === "GET" && path === "usage") return json({ usage: {} });
      if (method === "GET" && path === "library") return json({ files: [] });
      if (method === "GET" && /^bots\/[^/]+\/rows$/.test(path)) {
        return json({ bot_id: path.split("/")[1], rows: [] });
      }
      // Anything else the shell probes is answered with the envelope it expects.
      return json({});
    });

    await use(fixture);
  },
});

/** Open a clean first-run wizard. The sentinel preserves progress across reloads. */
export async function openWizard(page: Page): Promise<void> {
  await page.addInitScript(() => {
    if (!sessionStorage.getItem("keel-onboarding-test-init")) {
      localStorage.setItem("keel-onboarding-done", "false");
      localStorage.removeItem("keel-onboarding:step");
      localStorage.removeItem("keel-onboarding:checklist");
      localStorage.removeItem("keel-mode");
      sessionStorage.setItem("keel-onboarding-test-init", "1");
    }
  });
  await page.goto("/");
  await expect(page.getByRole("dialog", { name: "Welcome to Keel" })).toBeVisible();
}

export function wizard(page: Page) {
  return page.getByRole("dialog");
}

export async function advance(page: Page, label = "Continue"): Promise<void> {
  await wizard(page).getByRole("button", { name: label, exact: true }).click();
}

export async function readChecklist(page: Page): Promise<Record<string, string>> {
  return page.evaluate(() => {
    try {
      return JSON.parse(localStorage.getItem("keel-onboarding:checklist") ?? "{}");
    } catch {
      return {};
    }
  });
}
