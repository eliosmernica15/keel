import { NextRequest } from "next/server";
import http from "node:http";
import https from "node:https";
import { Readable } from "node:stream";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

const BRIDGE_URL = process.env.KEEL_BRIDGE_URL ?? "";
const BRIDGE_TOKEN = process.env.KEEL_BRIDGE_TOKEN ?? "";

function bridgeReachable() {
  return Boolean(BRIDGE_URL && BRIDGE_TOKEN);
}

function safePath(segments: string[] | undefined): string | null {
  if (!segments || segments.length === 0) return null;
  // hard-stop path traversal even though Next normalizes segments
  if (segments.some((s) => s.includes(".."))) return null;
  return segments.map((s) => encodeURIComponent(s)).join("/");
}

function sanitizeHeaders(req: NextRequest): Headers {
  const headers = new Headers(req.headers);
  headers.delete("host");
  headers.delete("connection");
  headers.delete("cookie"); // browser cookies are not the bridge's business
  // the browser's Origin refers to THIS app (http://127.0.0.1:3000) but the
  // upstream is the bridge (different port) — forwarding it makes the bridge's
  // same-origin check (correctly) refuse the request. This is a server-to-
  // server hop, so the origin header is meaningless; drop it.
  headers.delete("origin");
  headers.delete("referer");
  headers.set("x-keel-token", BRIDGE_TOKEN);
  return headers;
}

/** SSE via raw node:http — never through global fetch/undici.
 *
 * undici's socket parser throws AssertionError(!this.paused) when a
 * long-lived upstream stream drops (bridge restart, client abort), and it
 * is an *uncaught* exception that kills the NextJS server. Raw http keeps
 * the failure inside our pipe. */
function proxySse(upstream: string): Promise<Response> {
  return new Promise((resolve) => {
    let upstreamUrl: URL;
    try {
      upstreamUrl = new URL(upstream);
    } catch {
      return resolve(Response.json({ error: "bad_upstream_url" }, { status: 500 }));
    }
    const lib = upstreamUrl.protocol === "https:" ? https : http;
    const req = lib.request(
      {
        method: "GET",
        hostname: upstreamUrl.hostname,
        port: upstreamUrl.port || (upstreamUrl.protocol === "https:" ? 443 : 80),
        path: `${upstreamUrl.pathname}${upstreamUrl.search}`,
        headers: {
          "x-keel-token": BRIDGE_TOKEN,
          accept: "text/event-stream",
        },
      },
      (upstreamRes) => {
        if ((upstreamRes.statusCode ?? 502) >= 400) {
          // drain and report — the client needs a status, not a hung pipe
          upstreamRes.resume();
          resolve(Response.json(
            { error: "bridge_refused", detail: `upstream HTTP ${upstreamRes.statusCode}` },
            { status: 502 },
          ));
          return;
        }
        const webStream = Readable.toWeb(upstreamRes) as unknown as ReadableStream<Uint8Array>;
        resolve(new Response(webStream, {
          status: 200,
          headers: {
            "Content-Type": "text/event-stream; charset=utf-8",
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
          },
        }));
      },
    );
    req.on("error", (err) => {
      resolve(Response.json(
        { error: "bridge_unreachable", detail: err.name },
        { status: 504 },
      ));
    });
    // the bridge emits a keep-alive ping every ~10s; 30s of total silence
    // means the upstream is dead, not merely idle
    req.setTimeout(30_000, () => req.destroy(new Error("upstream timeout")));
    req.end();
  });
}

async function proxy(req: NextRequest, path: string): Promise<Response> {
  const incoming = new URL(req.url);
  const base = BRIDGE_URL.replace(/\/$/, "");
  const upstream = `${base}/api/fleet/${path}${incoming.search}`;

  if (path.startsWith("events")) {
    return proxySse(upstream);
  }

  const headers = sanitizeHeaders(req);
  let body: BodyInit | undefined;
  if (req.method !== "GET" && req.method !== "HEAD") {
    body = await req.arrayBuffer();
  }

  const upstreamResp = await fetch(upstream, {
    method: req.method,
    headers,
    body,
    // @ts-expect-error Node fetch requires duplex for streaming bodies
    duplex: body instanceof ArrayBuffer ? "half" : undefined,
    redirect: "manual",
    cache: "no-store",
  });

  const respHeaders = new Headers();
  const ct = upstreamResp.headers.get("content-type");
  if (ct) respHeaders.set("Content-Type", ct);
  const cd = upstreamResp.headers.get("content-disposition");
  if (cd) respHeaders.set("Content-Disposition", cd);
  respHeaders.set("Cache-Control", "no-store");
  respHeaders.set("X-Content-Type-Options", "nosniff");

  const buf = await upstreamResp.arrayBuffer();
  return new Response(buf, { status: upstreamResp.status, headers: respHeaders });
}

async function handle(req: NextRequest, ctx: { params: Promise<{ path?: string[] }> }) {
  const { path: segments } = await ctx.params;
  if (!bridgeReachable()) {
    return Response.json(
      { error: "bridge_unavailable", detail: "KEEL_BRIDGE_URL / KEEL_BRIDGE_TOKEN are not set on the NextJS server." },
      { status: 502 },
    );
  }
  const path = safePath(segments);
  if (!path) {
    return Response.json({ error: "bad_path" }, { status: 400 });
  }
  try {
    return await proxy(req, path);
  } catch (err) {
    // never leak the token or internal urls; just the class of failure
    return Response.json(
      { error: "bridge_unreachable", detail: err instanceof Error ? err.name : "fetch failed" },
      { status: 504 },
    );
  }
}

export const GET = handle;
export const POST = handle;
export const PUT = handle;
export const DELETE = handle;
