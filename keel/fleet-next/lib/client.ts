// Browser-side helper. Everything goes through the same-origin BFF proxy;
// the Keel token never exists in the browser.

export interface ApiRequestError extends Error {
  status?: number;
}

const RETRYABLE_STATUS = new Set([502, 504]); // BFF proxy gateway failures
const MAX_READ_ATTEMPTS = 2;
const RETRY_DELAY_MS = 300;

/**
 * Perform a bridge request through the same-origin BFF.
 *
 * Only idempotent reads are retried, at most once, and only for gateway-level
 * failures (502/504) or a dropped network connection. Writes (POST/PUT/DELETE)
 * are never retried automatically: an approval, trust decision, upload or
 * mutation must not be silently duplicated.
 */
export async function api<T = any>(
  path: string,
  opts: RequestInit = {},
): Promise<T> {
  const method = (opts.method ?? "GET").toUpperCase();
  const idempotent = method === "GET" || method === "HEAD";
  const attempts = idempotent ? MAX_READ_ATTEMPTS : 1;
  const url = `/api/bridge/${path.replace(/^\//, "")}`;
  let lastError: ApiRequestError | null = null;

  for (let attempt = 0; attempt < attempts; attempt++) {
    try {
      const resp = await fetch(url, {
        ...opts,
        headers: {
          ...(opts.body ? { "Content-Type": "application/json" } : {}),
          ...(opts.headers ?? {}),
        },
        cache: "no-store",
      });
      const text = await resp.text();
      let body: any = null;
      try {
        body = text ? JSON.parse(text) : null;
      } catch {
        body = { raw: text };
      }
      if (!resp.ok) {
        const detail = body?.detail ?? body?.error ?? body?.refused ?? `http ${resp.status}`;
        const error = new Error(detail) as ApiRequestError;
        error.status = resp.status;
        lastError = error;
        if (attempt < attempts - 1 && RETRYABLE_STATUS.has(resp.status)) {
          await new Promise((resolve) => setTimeout(resolve, RETRY_DELAY_MS * (attempt + 1)));
          continue;
        }
        throw error;
      }
      return body as T;
    } catch (err) {
      // A dropped connection is retryable for reads; for writes it must be
      // surfaced immediately so the user can decide whether to retry.
      if (err instanceof TypeError && idempotent && attempt < attempts - 1) {
        lastError = err as ApiRequestError;
        await new Promise((resolve) => setTimeout(resolve, RETRY_DELAY_MS * (attempt + 1)));
        continue;
      }
      throw err;
    }
  }
  throw lastError ?? new Error("request failed");
}
