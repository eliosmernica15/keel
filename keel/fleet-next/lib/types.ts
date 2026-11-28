// Shared domain types for the unified Keel frontend.
// These describe the shapes returned by the Python bridge (/api/fleet/*).
// Nothing here is fabricated: fields are optional where the backend may omit them.

export type Surface = "cowork" | "code" | "duet" | "fleet";
export type Theme = "dark" | "light" | "system";
export type CapabilityState = "available" | "unconfigured" | "requires-setup" | "blocked" | "unsupported";

export interface ApiErrorShape {
  error?: string;
  detail?: string;
  refused?: string;
  raw?: string;
}

/* ---------- Providers / models ---------- */
export interface Provider {
  id: string;
  name?: string;
  configured?: boolean;
  connected?: boolean;
  models?: ModelInfo[];
  error?: string;
}

export interface ModelInfo {
  id: string;
  name?: string;
  provider?: string;
  context_window?: number;
  max_tokens?: number;
  capabilities?: string[];
}

export interface CatalogResponse {
  providers?: Provider[];
  models?: ModelInfo[];
  [key: string]: unknown;
}

/* ---------- Bots / agents ---------- */
export interface Bot {
  id: string;
  name?: string;
  role?: string;
  provider?: string;
  model?: string;
  state?: string;
  status?: string;
  last_activity?: string;
  task_count?: number;
  notes?: string;
  engine?: Record<string, unknown>;
  permissions?: Record<string, unknown>;
  [key: string]: unknown;
}

export interface BotRow {
  id?: string;
  role?: string;
  body?: Record<string, unknown>;
  ts?: string | number;
  [key: string]: unknown;
}

/* ---------- Events / work log ---------- */
export interface FleetEvent {
  type?: string;
  kind?: string;
  bot_id?: string;
  session_id?: string;
  ts?: string | number;
  body?: Record<string, unknown>;
  text?: string;
  [key: string]: unknown;
}

export interface ApprovalRequest {
  approval_id: string;
  operation?: string;
  scope?: string;
  description?: string;
  tool?: string;
  args?: Record<string, unknown>;
  [key: string]: unknown;
}

export interface AskRequest {
  ask_id?: string;
  id?: string;
  question?: string;
  text?: string;
  options?: string[];
  [key: string]: unknown;
}

/* ---------- Tasks / routines / library ---------- */
export interface FleetTask {
  id: string;
  title?: string;
  status?: string;
  priority?: string;
  assignee?: string;
  progress?: number;
  created?: string;
  due?: string;
  [key: string]: unknown;
}

export interface Routine {
  id: string;
  name?: string;
  schedule?: string;
  timezone?: string;
  next_run?: string;
  last_run?: string;
  enabled?: boolean;
  [key: string]: unknown;
}

export interface LibraryItem {
  id: string;
  name?: string;
  type?: string;
  size?: number;
  bot_id?: string;
  task_id?: string;
  created?: string;
  [key: string]: unknown;
}

/* ---------- Projects / filesystem ---------- */
export interface Project {
  id: string;
  name?: string;
  path?: string;
  trusted?: boolean;
  [key: string]: unknown;
}

export interface FileNode {
  name: string;
  path: string;
  type?: "file" | "dir" | "folder" | string;
  children?: FileNode[];
  [key: string]: unknown;
}

export interface FileRead {
  path?: string;
  content?: string;
  encoding?: string;
  size?: number;
  [key: string]: unknown;
}

export interface ReviewData {
  status?: Array<{ path?: string; state?: string; additions?: number; deletions?: number }>;
  branch?: string;
  log?: unknown[];
  diff?: string;
  [key: string]: unknown;
}

export interface ShellHandle {
  handle?: string;
  id?: string;
  command?: string;
  status?: string;
  exit_code?: number;
  output?: string;
  cwd?: string;
  [key: string]: unknown;
}

/* ---------- Capabilities ---------- */
export interface Skill {
  id: string;
  name?: string;
  description?: string;
  scope?: string;
  enabled?: boolean;
  source?: string;
  injections?: number;
  [key: string]: unknown;
}

export interface Connector {
  id: string;
  name?: string;
  type?: string;
  enabled?: boolean;
  state?: string;
  tools?: unknown[];
  [key: string]: unknown;
}

export interface ToolDescriptor {
  name: string;
  description?: string;
  permission?: string;
  available?: boolean;
  [key: string]: unknown;
}

export interface SlashCommand {
  name: string;
  description?: string;
  usage?: string;
  source?: string;
  [key: string]: unknown;
}

export interface Workflow {
  id: string;
  name?: string;
  steps?: unknown[];
  last_run?: string;
  [key: string]: unknown;
}

export interface Usage {
  input_tokens?: number;
  output_tokens?: number;
  cache_read_input_tokens?: number;
  cache_creation_input_tokens?: number;
  tokens?: number;
  cost?: number;
  requests?: number;
}

export interface UsageResponse {
  usage?: Usage;
}

/* ---------- UI ---------- */
export interface Notice {
  id: string;
  kind: "info" | "success" | "warning" | "error";
  message: string;
  ts: number;
}

export interface CommandAction {
  id: string;
  label: string;
  group?: string;
  hint?: string;
  run: () => void;
}
