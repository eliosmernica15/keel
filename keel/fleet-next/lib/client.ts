// Browser-side helper. Everything goes through the same-origin BFF proxy;
// the Keel token never exists in the browser.

export async function api<T = any>(
  path: string,
  opts: RequestInit = {},
): Promise<T> {
  const resp = await fetch(`/api/bridge/${path.replace(/^\//, "")}`, {
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
    throw new Error(detail);
  }
  return body as T;
}
