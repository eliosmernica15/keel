// Typed bridge client. Every call goes through the same-origin BFF proxy
// (`/api/bridge/*`) which injects the Keel token server-side. No secrets ever
// reach the browser. The Python bridge remains authoritative for execution,
// permissions, trust and secrets; this module only describes the contract.

import { api, type ApiRequestError } from "./client";
import type {
  ApiErrorShape,
  Bot,
  BotRow,
  CatalogResponse,
  Connector,
  FleetTask,
  FileNode,
  FileRead,
  LibraryItem,
  Provider,
  ReviewData,
  Routine,
  ShellHandle,
  Skill,
  SlashCommand,
  UsageResponse,
} from "./types";

export { api };

/** Normalise whatever the bridge returns into a readable error.
 *  The BFF's stable `error` code is preferred over a free-form `detail`, which
 *  for upstream failures can be just an exception name ("TypeError"). */
export function errMessage(err: unknown): string {
  if (err instanceof Error) {
    const e = err as ApiRequestError;
    const detail = e.message;
    // Prefer a human-readable `detail`, but fall back to the stable BFF code
    // when the detail is absent or generic (e.g. an upstream "TypeError").
    if (detail && detail !== e.code && !/^(typeerror|error|fetch failed|failed to fetch|network error)$/i.test(detail)) return detail;
    if (e.code) return e.code;
    if (e.status === 502 || e.status === 504) return `http ${e.status}`;
    return detail || "Request failed";
  }
  const e = err as ApiErrorShape;
  return e?.detail || e?.error || e?.refused || e?.raw || "Request failed";
}

/** True when the BFF reports that the local bridge is not configured/running. */
export function isBridgeUnavailable(err: unknown): boolean {
  if (err instanceof Error) {
    const e = err as ApiRequestError;
    if (e.status === 502 || e.status === 504) return true;
    if (e.code?.startsWith("bridge_")) return true;
  }
  const msg = errMessage(err).toLowerCase();
  return msg.includes("bridge_unavailable") || msg.includes("bridge_unreachable") ||
    msg.includes("bridge_refused") || msg.includes("http 502") || msg.includes("http 504");
}

export const bridge = {
  /* agents */
  listBots: () => api<Bot[] | { bots?: Bot[] }>("bots"),
  botRows: (id: string) => api<BotRow[] | { rows?: BotRow[] }>(`bots/${id}/rows`),
  createBot: (payload: unknown) => api<Bot>("bots", { method: "POST", body: JSON.stringify(payload) }),
  updateBot: (id: string, patch: unknown) => api<Bot>(`bots/${id}/update`, { method: "POST", body: JSON.stringify(patch) }),
  deleteBot: (id: string) => api(`bots/${id}/delete`, { method: "POST", body: "{}" }),
  forkBot: (id: string, payload?: unknown) => api<Bot>(`bots/${id}/fork`, { method: "POST", body: JSON.stringify(payload ?? {}) }),
  sendMessage: (id: string, payload: unknown) => api(`bots/${id}/messages`, { method: "POST", body: JSON.stringify(payload) }),
  cancel: (id: string) => api(`bots/${id}/cancel`, { method: "POST", body: "{}" }),
  // The bridge accepts exactly: once | always | never
  decideApproval: (id: string, approvalId: string, decision: "once" | "always" | "never") =>
    api(`bots/${id}/approvals/${approvalId}/decide`, { method: "POST", body: JSON.stringify({ decision }) }),
  answerAsk: (id: string, askId: string, answer: unknown) =>
    api(`bots/${id}/asks/${askId}/answer`, { method: "POST", body: JSON.stringify({ answer }) }),
  rewind: (id: string, payload?: unknown) => api(`bots/${id}/rewind`, { method: "POST", body: JSON.stringify(payload ?? {}) }),
  restore: (id: string, payload?: unknown) => api(`bots/${id}/restore`, { method: "POST", body: JSON.stringify(payload ?? {}) }),
  botPolicies: (id: string) => api(`bots/${id}/policies`),
  botAudit: (id: string, limit = 50) => api(`bots/${id}/audit?limit=${limit}`),
  revokePolicy: (id: string, toolName: string) =>
    api(`bots/${id}/policies/revoke`, { method: "POST", body: JSON.stringify({ tool_name: toolName }) }),

  /* groups — fully supported by the bridge */
  groups: () => api("groups"),
  createGroup: (payload: unknown) => api("groups", { method: "POST", body: JSON.stringify(payload) }),
  group: (id: string) => api(`groups/${id}`),
  groupRows: (id: string) => api(`groups/${id}/rows`),
  groupMessage: (id: string, content: string) =>
    api(`groups/${id}/messages`, { method: "POST", body: JSON.stringify({ content }) }),
  deleteGroup: (id: string) => api(`groups/${id}/delete`, { method: "POST", body: "{}" }),

  /* providers */
  providers: () => api<Provider[] | { providers?: Provider[] }>("providers"),
  catalog: (payload?: unknown) => api<CatalogResponse>("providers/catalog", { method: "POST", body: JSON.stringify(payload ?? {}) }),
  setCredential: (payload: unknown) => api("providers/credential", { method: "POST", body: JSON.stringify(payload) }),
  clearCredential: (payload: unknown) => api("providers/credential/clear", { method: "POST", body: JSON.stringify(payload) }),
  saveProvider: (payload: unknown) => api("providers/save", { method: "POST", body: JSON.stringify(payload) }),
  removeProvider: (payload: unknown) => api("providers/remove", { method: "POST", body: JSON.stringify(payload) }),

  /* projects / code */
  projects: () => api<unknown[] | { projects?: unknown[] }>("projects"),
  addProject: (payload: unknown) => api("projects", { method: "POST", body: JSON.stringify(payload) }),
  trustProject: (id: string, trusted: boolean) => api(`projects/${id}/trust`, { method: "POST", body: JSON.stringify({ trusted }) }),
  removeProject: (id: string) => api(`projects/${id}/remove`, { method: "POST", body: "{}" }),
  openProject: (id: string) => api(`projects/${id}/open`, { method: "POST", body: "{}" }),
  startChat: (id: string) => api(`projects/${id}/chat`, { method: "POST", body: "{}" }),
  projectTree: (id: string) => api<FileNode[] | { tree?: FileNode[] }>(`projects/${id}/tree`),
  readFile: (id: string, path: string) => api<FileRead>(`projects/${id}/file/read?path=${encodeURIComponent(path)}`),
  writeFile: (id: string, path: string, content: string) =>
    api(`projects/${id}/file/write`, { method: "POST", body: JSON.stringify({ path, content }) }),
  review: (id: string) => api<ReviewData>(`projects/${id}/review`),
  terminalExec: (id: string, command: string) =>
    api<ShellHandle>(`projects/${id}/terminal/exec`, { method: "POST", body: JSON.stringify({ command }) }),
  setProjectModel: (id: string, model: string) =>
    api(`projects/${id}/model`, { method: "POST", body: JSON.stringify({ model }) }),

  /* shells */
  shells: () => api<ShellHandle[] | { shells?: ShellHandle[] }>("shells"),
  shellOutput: (handle: string) => api<ShellHandle>(`shells/${handle}/output`),
  killShell: (handle: string) => api(`shells/${handle}/kill`, { method: "POST", body: "{}" }),
  // The bridge exposes this as a GET route (routes.py:528); POST falls through.
  clearFinishedShells: () => api("shells/clear/finished"),

  /* tasks / routines / library */
  tasks: () => api<FleetTask[] | { tasks?: FleetTask[] }>("tasks"),
  createTask: (payload: unknown) => api<FleetTask>("tasks", { method: "POST", body: JSON.stringify(payload) }),
  updateTask: (id: string, patch: unknown) => api(`tasks/${id}/update`, { method: "POST", body: JSON.stringify(patch) }),
  undoTask: (id: string) => api(`tasks/${id}/undo`, { method: "POST", body: "{}" }),
  deleteTask: (id: string) => api(`tasks/${id}/delete`, { method: "POST", body: "{}" }),
  reorderTasks: (payload: unknown) => api("tasks/reorder", { method: "POST", body: JSON.stringify(payload) }),
  routines: () => api<Routine[] | { routines?: Routine[] }>("routines"),
  createRoutine: (payload: unknown) => api<Routine>("routines", { method: "POST", body: JSON.stringify(payload) }),
  routine: (id: string) => api(`routines/${id}`),
  routineRuns: (id: string) => api(`routines/${id}/runs`),
  routineAction: (id: string, action: "update" | "enable" | "disable" | "pause" | "resume" | "run" | "delete", payload?: unknown) =>
    api(`routines/${id}/${action}`, { method: "POST", body: JSON.stringify(payload ?? {}) }),
  runRoutine: (id: string) => api(`routines/${id}/run`, { method: "POST", body: "{}" }),
  taskEvents: (id: string) => api(`tasks/${id}/events`),
  library: () => api<LibraryItem[] | { files?: LibraryItem[] }>("library"),
  uploadLibrary: (payload: unknown) => api("library", { method: "POST", body: JSON.stringify(payload) }),
  deleteLibrary: (id: string) => api(`library/${id}/delete`, { method: "POST", body: "{}" }),

  /* capabilities — all backed by real bridge routes */
  skills: () => api<Skill[] | { skills?: Skill[] }>("skills"),
  skillsManage: () => api("skills/manage"),
  installSkill: (payload: unknown) => api("skills/install", { method: "POST", body: JSON.stringify(payload) }),
  removeSkill: (payload: unknown) => api("skills/remove", { method: "POST", body: JSON.stringify(payload) }),
  enableSkill: (payload: unknown) => api("skills/enable", { method: "POST", body: JSON.stringify(payload) }),
  commands: () => api("commands"),
  executeCommand: (payload: unknown) => api("commands/execute", { method: "POST", body: JSON.stringify(payload) }),
  workflows: () => api("workflows"),
  executeWorkflow: (payload: unknown) => api("workflows/execute", { method: "POST", body: JSON.stringify(payload) }),
  mcpServers: () => api("mcp/servers"),
  mcpHealth: () => api("mcp/health", { method: "POST", body: "{}" }),
  connectors: () => api<Connector[] | { connectors?: Connector[] }>("connectors"),
  addConnector: (payload: unknown) => api("connectors/add", { method: "POST", body: JSON.stringify(payload) }),
  removeConnector: (payload: unknown) => api("connectors/remove", { method: "POST", body: JSON.stringify(payload) }),
  testConnector: (payload: unknown) => api("connectors/test", { method: "POST", body: JSON.stringify(payload) }),

  /* system */
  usage: () => api<UsageResponse>("usage"),
  keepAwake: (enabled?: boolean) =>
    enabled === undefined
      ? api<boolean>("keep-awake")
      : api<boolean>("keep-awake", { method: "POST", body: JSON.stringify({ on: enabled }) }),

  exportUrl: (botId: string) => `/api/bridge/bots/${botId}/export.md`,
  downloadUrl: (id: string) => `/api/bridge/library/${id}/download`,
  previewUrl: (id: string) => `/api/bridge/library/${id}/preview`,
};

/** Subscribe to the bridge SSE stream. Returns an unsubscribe function.
 *  The bridge emits named `event: row` frames (routes.py:1748); those do NOT
 *  reach `onmessage`, so both the named listener and the generic handler are
 *  required. Each frame is delivered exactly once. */
export function subscribeEvents(onEvent: (event: MessageEvent) => void, onError?: () => void, onOpen?: () => void): () => void {
  const es = new EventSource("/api/bridge/events");
  if (onOpen) es.onopen = onOpen;
  const onRow = (e: Event) => {
    try { onEvent(e as MessageEvent); } catch { /* consumer owns its errors */ }
  };
  es.addEventListener("row", onRow);
  es.onmessage = (e) => {
    try { onEvent(e); } catch { /* consumer owns its errors */ }
  };
  es.onerror = () => { onError?.(); };
  return () => { es.removeEventListener("row", onRow); es.close(); };
}

/** A typed slash-command catalogue — descriptions only, no fabricated execution. */
export const SLASH_COMMANDS: SlashCommand[] = [
  { name: "context", description: "Show what Keel knows about this workspace", usage: "/context" },
  { name: "model", description: "Inspect or switch the active model", usage: "/model <name>" },
  { name: "shell", description: "Run a guarded shell command", usage: "/shell <command>" },
  { name: "review", description: "Review current file changes", usage: "/review" },
  { name: "open", description: "Open a file in the workspace", usage: "/open <path>" },
  { name: "help", description: "List available slash commands", usage: "/help" },
];
