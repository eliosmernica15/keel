// FIXTURE ONLY — tiny deterministic stand-in for the Python bridge.
//
// It exists solely so the packaged-compat suite can drive the REAL NextJS BFF
// (`/api/bridge/*`) on a non-3000 loopback port. It never executes tools, never
// reads user data and stores no credentials. Every response is a fixed,
// contract-shaped fixture. The expected bridge token is passed in by the test
// config; this server only records whether the BFF injected it correctly.

import http from "node:http";

const PORT = Number(process.env.KEEL_COMPAT_BRIDGE_PORT ?? 3472);
const TOKEN = process.env.KEEL_BRIDGE_TOKEN ?? "local-packaged-compat-token";

const BOT = {
  id: "bot-1",
  name: "Compat task",
  role: "General assistant",
  engine: "echo",
  provider: "auto",
  model: "",
  state: "idle",
  avatar_hue: 210,
};

const ROWS = [
  { id: "r1", bot_id: BOT.id, seq: 1, kind: "user", role: "user", body: { text: "fixture one" }, created_at: "2026-11-25T09:00:00Z" },
  { id: "r2", bot_id: BOT.id, seq: 2, kind: "agent", role: "agent", body: { text: "fixture two" }, created_at: "2026-11-25T09:01:00Z" },
  { id: "r3", bot_id: BOT.id, seq: 3, kind: "user", role: "user", body: { text: "fixture three" }, created_at: "2026-11-25T09:02:00Z" },
];

const TASK = { id: "t1", title: "QA undo target", status: "open", priority: "normal", progress: 0 };

const MARKDOWN = "# Compat task\n\nfixture transcript bytes\n";

/** Everything the suite needs to observe, without ever exposing a token value. */
const observations = {
  calls: [],
  tokenSeen: 0,
  tokenMatchesExpected: 0,
  tokenHeaderNames: [],
};

function sendJson(res, status, body) {
  const payload = JSON.stringify(body);
  res.writeHead(status, {
    "content-type": "application/json; charset=utf-8",
    "content-length": Buffer.byteLength(payload),
    "cache-control": "no-store",
  });
  res.end(payload);
}

function sendText(res, status, text, contentType = "text/plain; charset=utf-8", extra = {}) {
  res.writeHead(status, {
    "content-type": contentType,
    "content-length": Buffer.byteLength(text),
    "cache-control": "no-store",
    ...extra,
  });
  res.end(text);
}

function readBody(req) {
  return new Promise((resolve) => {
    const chunks = [];
    req.on("data", (c) => chunks.push(c));
    req.on("end", () => {
      const raw = Buffer.concat(chunks).toString("utf8");
      try { resolve(raw ? JSON.parse(raw) : null); } catch { resolve(raw); }
    });
    req.on("error", () => resolve(null));
  });
}

function fixtureResponse(method, path, body, query) {
  if (path === "providers") return { providers: [] };
  if (path === "bots" && method === "GET") return { bots: [BOT] };
  if (path === "bots" && method === "POST") return { bot: BOT };
  if (path === "tasks" && method === "GET") return { tasks: [TASK] };
  if (path === "groups") return { groups: [] };
  if (path === "routines") return { routines: [] };
  if (path === "library") return { files: [], usage_bytes: 0 };
  if (path === "projects") return { projects: [] };
  if (path === "shells") return { shells: [] };
  if (path === "skills") return { skills: [] };
  if (path === "skills/manage") return { managed: [] };
  if (path === "commands") return { commands: [] };
  if (path === "workflows") return { workflows: [] };
  if (path === "mcp/servers") return { servers: [] };
  if (path === "connectors") return { connectors: [] };
  if (path === "usage") return { usage: { input_tokens: 12, output_tokens: 7 } };
  if (path === "keep-awake") return true;
  if (path === "providers/catalog") return { ok: true, source: "offline", models: ["fixture-model"] };

  const rows = /^bots\/([^/]+)\/rows$/.exec(path);
  if (rows && method === "GET") return { bot_id: rows[1], rows: ROWS };

  const audit = /^bots\/([^/]+)\/audit$/.exec(path);
  if (audit && method === "GET") return { audit: [] };

  const policies = /^bots\/([^/]+)\/policies$/.exec(path);
  if (policies && method === "GET") return { policies: [] };

  const rewind = /^bots\/([^/]+)\/rewind$/.exec(path);
  if (rewind && method === "POST") {
    const from = Number(body?.from_seq);
    const rows = ROWS.filter((r) => r.seq >= from);
    return { rows, deleted: rows.length };
  }

  const restore = /^bots\/([^/]+)\/restore$/.exec(path);
  if (restore && method === "POST") return { restored: Array.isArray(body?.rows) ? body.rows.length : 0 };

  if (/^bots\/[^/]+\/(messages|update|fork|cancel|rewind|restore|delete)$/.test(path) && method === "POST") {
    return { ok: true, queued: true, seq: 900, bot: BOT };
  }

  if (/^tasks\/[^/]+\/(delete|undo|update)$/.test(path) && method === "POST") return { ok: true, task: TASK };
  if (/^tasks\/[^/]+\/events$/.test(path)) return { events: [] };

  // Unknown bridge routes must still answer honestly-shaped JSON rather than
  // a bare 404, which would add browser console noise unrelated to the test.
  void query;
  return { ok: true };
}

const server = http.createServer(async (req, res) => {
  const url = new URL(req.url ?? "/", `http://127.0.0.1:${PORT}`);

  if (url.pathname === "/__fixture/observations") {
    sendJson(res, 200, observations);
    return;
  }
  if (url.pathname === "/__fixture/reset" && req.method === "POST") {
    observations.calls = [];
    observations.tokenSeen = 0;
    observations.tokenMatchesExpected = 0;
    observations.tokenHeaderNames = [];
    sendJson(res, 200, { ok: true });
    return;
  }

  const tokenHeader = Object.keys(req.headers).find((h) => h.toLowerCase() === "x-keel-token");
  if (tokenHeader) {
    observations.tokenSeen += 1;
    if (req.headers[tokenHeader] === TOKEN) observations.tokenMatchesExpected += 1;
    if (!observations.tokenHeaderNames.includes(tokenHeader)) observations.tokenHeaderNames.push(tokenHeader);
  }

  const path = url.pathname.replace(/^\/api\/fleet\/?/, "");
  const method = req.method ?? "GET";
  const body = method === "GET" || method === "HEAD" ? null : await readBody(req);
  observations.calls.push({ method, path: `${path}${url.search}`, body, tokenSeen: Boolean(tokenHeader) });

  if (path === "events") {
    res.writeHead(200, {
      "content-type": "text/event-stream; charset=utf-8",
      "cache-control": "no-cache",
      "x-accel-buffering": "no",
    });
    res.write(": fixture ping\n\n");
    const timer = setInterval(() => {
      if (!res.destroyed) res.write(": fixture ping\n\n");
    }, 5000);
    req.on("close", () => clearInterval(timer));
    return;
  }

  if (/^bots\/[^/]+\/export\.md$/.test(path) && method === "GET") {
    sendText(res, 200, MARKDOWN, "text/markdown; charset=utf-8", {
      "content-disposition": 'attachment; filename="Compat-task.md"',
    });
    return;
  }
  if (/^library\/[^/]+\/(download|preview)$/.test(path) && method === "GET") {
    sendText(res, 200, "fixture library bytes\n");
    return;
  }

  sendJson(res, 200, fixtureResponse(method, path, body, url.search));
});

server.listen(PORT, "127.0.0.1", () => {
  process.stdout.write(`fixture bridge listening on http://127.0.0.1:${PORT}/\n`);
});
