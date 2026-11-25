"use client";

// Shared, evidence-only workspace pieces used by both Code and Duet.
// Every value shown here comes from a real bridge call. Where the bridge does
// not report a fact (permission mode, branch, model, token counts, preview
// URLs, file-level diffs) the UI says so instead of inventing one.

import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { bridge, errMessage, isBridgeUnavailable } from "@/lib/api";
import type { FileRead, Project, ReviewData, ShellHandle } from "@/lib/types";
import { Badge, Button, Dialog, EmptyState, IconButton, SectionTitle, Spinner } from "@/components/ui";
import { Icon } from "@/components/icons";
import s from "./workspace.module.css";

/* ------------------------------------------------------------------ */
/* normalisers                                                         */
/* ------------------------------------------------------------------ */

export function asArray<T>(value: unknown, keys: string[] = []): T[] {
  if (Array.isArray(value)) return value as T[];
  if (value && typeof value === "object") {
    const o = value as Record<string, unknown>;
    for (const key of [...keys, "items", "data", "list"]) {
      if (Array.isArray(o[key])) return o[key] as T[];
    }
  }
  return [];
}

function normalizeProject(value: unknown): Project | null {
  if (typeof value === "string") return { id: value, path: value };
  if (!value || typeof value !== "object") return null;
  const o = value as Record<string, unknown>;
  const id = String(o.id ?? o.path ?? "").trim();
  if (!id) return null;
  return {
    ...o,
    id,
    path: typeof o.path === "string" ? o.path : undefined,
    name: typeof o.name === "string" ? o.name : undefined,
    trusted: o.trusted === true || o.trusted === 1,
  };
}

/** Match a media query without touching the DOM during SSR. */
export function useNarrow(maxWidth = 900): boolean {
  const [narrow, setNarrow] = useState(() =>
    typeof window !== "undefined" && typeof window.matchMedia === "function"
      ? window.matchMedia(`(max-width:${maxWidth}px)`).matches
      : false);
  useEffect(() => {
    if (typeof window === "undefined" || typeof window.matchMedia !== "function") return;
    const mq = window.matchMedia(`(max-width:${maxWidth}px)`);
    const onChange = () => setNarrow(mq.matches);
    onChange();
    mq.addEventListener("change", onChange);
    return () => mq.removeEventListener("change", onChange);
  }, [maxWidth]);
  return narrow;
}

export function formatBytes(n: number): string {
  if (!Number.isFinite(n) || n < 0) return "";
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / (1024 * 1024)).toFixed(1)} MB`;
}

export function fileLanguage(path: string): string {
  const ext = path.split(".").pop()?.toLowerCase() ?? "";
  const map: Record<string, string> = {
    ts: "js", tsx: "js", js: "js", jsx: "js", mjs: "js", cjs: "js", json: "json",
    css: "css", scss: "css", less: "css", html: "html", htm: "html", xml: "html", svg: "html",
    py: "py", md: "md", markdown: "md", sh: "sh", bash: "sh", ps1: "sh", bat: "sh",
    yml: "yaml", yaml: "yaml", toml: "ini", ini: "ini", sql: "sql", rs: "js", go: "js",
  };
  return map[ext] ?? "plain";
}

/* ------------------------------------------------------------------ */
/* project + tree state                                                */
/* ------------------------------------------------------------------ */

export interface ProjectsController {
  projects: Project[];
  loading: boolean;
  error: string | null;
  bridgeDown: boolean;
  selectedId: string | null;
  selected: Project | null;
  select: (id: string | null) => void;
  refresh: () => void;
  add: (path: string, name?: string) => Promise<void>;
  trust: (id: string, trusted: boolean) => Promise<void>;
  remove: (id: string) => Promise<void>;
  open: (id: string) => Promise<void>;
}

export function useProjects(storageKey: string): ProjectsController {
  const [projects, setProjects] = useState<Project[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [bridgeDown, setBridgeDown] = useState(false);
  const [tick, setTick] = useState(0);
  const requestId = useRef(0);
  const [selectedId, setSelectedIdState] = useState<string | null>(() => {
    try { return localStorage.getItem(storageKey); } catch { return null; }
  });

  useEffect(() => {
    // StrictMode and rapid trust/refresh actions can leave two GETs in flight.
    // Without a sequence guard a slower, older response can land last and
    // overwrite the newer trust state (a real parallel-load race).
    const id = ++requestId.current;
    let alive = true;
    const current = () => alive && id === requestId.current;
    setLoading(true);
    setError(null);
    setBridgeDown(false);
    bridge.projects()
      .then((res) => {
        if (!current()) return;
        const list = asArray<unknown>(res, ["projects"])
          .map(normalizeProject)
          .filter((p): p is Project => p !== null);
        setProjects(list);
      })
      .catch((err) => {
        if (!current()) return;
        setError(errMessage(err));
        setBridgeDown(isBridgeUnavailable(err));
        setProjects([]);
      })
      .finally(() => { if (current()) setLoading(false); });
    return () => { alive = false; };
  }, [tick]);

  useEffect(() => {
    if (loading || !projects.length) return;
    if (!projects.some((p) => p.id === selectedId)) setSelectedIdState(projects[0].id);
  }, [loading, projects, selectedId]);

  useEffect(() => {
    if (!loading && !projects.length && selectedId) setSelectedIdState(null);
  }, [loading, projects.length, selectedId]);

  const select = useCallback((id: string | null) => {
    setSelectedIdState(id);
    try {
      if (id) localStorage.setItem(storageKey, id);
      else localStorage.removeItem(storageKey);
    } catch { /* storage may be unavailable */ }
  }, [storageKey]);

  const refresh = useCallback(() => setTick((t) => t + 1), []);

  const add = useCallback(async (path: string, name?: string) => {
    await bridge.addProject({ path, ...(name ? { name } : {}) });
    refresh();
  }, [refresh]);

  const trust = useCallback(async (id: string, trusted: boolean) => {
    await bridge.trustProject(id, trusted);
    refresh();
  }, [refresh]);

  const remove = useCallback(async (id: string) => {
    await bridge.removeProject(id);
    if (selectedId === id) select(null);
    refresh();
  }, [refresh, selectedId, select]);

  const open = useCallback(async (id: string) => {
    await bridge.openProject(id);
    refresh();
  }, [refresh]);

  const selected = useMemo(
    () => projects.find((p) => p.id === selectedId) ?? null,
    [projects, selectedId],
  );

  return { projects, loading, error, bridgeDown, selectedId, selected, select, refresh, add, trust, remove, open };
}

/* ------------------------------------------------------------------ */
/* file tree                                                           */
/* ------------------------------------------------------------------ */

export interface TreeNode {
  name: string;
  path: string;
  kind: "file" | "dir";
  size?: number;
  children: TreeNode[];
}

function mapNested(item: Record<string, unknown>, parent: string): TreeNode {
  const name = String(item.name ?? "");
  const path = String(item.path ?? (parent ? `${parent}/${name}` : name));
  const type = String(item.type ?? item.kind ?? "").toLowerCase();
  const kind: "file" | "dir" = type === "dir" || type === "folder" || Array.isArray(item.children) ? "dir" : "file";
  const size = typeof item.size === "number" ? item.size : undefined;
  return {
    name: name || path.split("/").pop() || path,
    path,
    kind,
    size,
    children: asArray<Record<string, unknown>>(item.children).map((c) => mapNested(c, path)),
  };
}

/** The bridge returns a flat list of files with a `dir` field; older payloads
 *  may be nested. Both are supported without inventing paths. */
export function buildTree(raw: unknown): TreeNode[] {
  const items = asArray<Record<string, unknown>>(raw, ["entries", "tree", "files"]);
  if (!items.length) return [];
  if (items.some((i) => Array.isArray(i.children))) return items.map((i) => mapNested(i, ""));

  const byPath = new Map<string, TreeNode>();
  const ensureDir = (path: string): TreeNode => {
    const key = path.replace(/^\/+|\/+$/g, "");
    const existing = byPath.get(key);
    if (existing && existing.kind === "dir") return existing;
    const node: TreeNode = {
      name: key ? key.split("/").pop() ?? key : "",
      path: key,
      kind: "dir",
      children: [],
    };
    byPath.set(key, node);
    if (key) {
      const parent = key.includes("/") ? key.slice(0, key.lastIndexOf("/")) : "";
      ensureDir(parent).children.push(node);
    }
    return node;
  };
  ensureDir("");

  for (const item of items) {
    const path = String(item.path ?? item.name ?? "").trim().replace(/^\/+/, "");
    if (!path) continue;
    const type = String(item.type ?? item.kind ?? "").toLowerCase();
    const isDir = type === "dir" || type === "folder" || item.dir === true || item.is_dir === true;
    if (isDir) { ensureDir(path); continue; }
    const parent = typeof item.dir === "string"
      ? item.dir.replace(/^\/+|\/+$/g, "")
      : path.includes("/") ? path.slice(0, path.lastIndexOf("/")) : "";
    const parentNode = ensureDir(parent);
    const node: TreeNode = {
      name: String(item.name ?? path.split("/").pop() ?? path),
      path,
      kind: "file",
      size: typeof item.size === "number" ? item.size : undefined,
      children: [],
    };
    byPath.set(path, node);
    parentNode.children.push(node);
  }
  const sortNodes = (nodes: TreeNode[]) => {
    nodes.sort((a, b) => {
      if (a.kind !== b.kind) return a.kind === "dir" ? -1 : 1;
      return a.name.localeCompare(b.name);
    });
    nodes.forEach((n) => sortNodes(n.children));
  };
  const roots = byPath.get("")?.children ?? [];
  sortNodes(roots);
  return roots;
}

export function flattenTree(nodes: TreeNode[]): TreeNode[] {
  const out: TreeNode[] = [];
  const walk = (list: TreeNode[]) => list.forEach((n) => { out.push(n); if (n.children.length) walk(n.children); });
  walk(nodes);
  return out;
}

export function useTree(projectId: string | null, enabled: boolean) {
  const [nodes, setNodes] = useState<TreeNode[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [bridgeDown, setBridgeDown] = useState(false);
  const [tick, setTick] = useState(0);
  const requestId = useRef(0);

  useEffect(() => {
    // Invalidate any in-flight read when the pane is disabled or the project
    // changes, so an older tree can never land after the newer empty state.
    if (!projectId || !enabled) {
      requestId.current += 1;
      setNodes([]); setError(null);
      return;
    }
    // Same stale-response guard as useProjects: a slow older tree read must
    // never overwrite a newer project's (or newer refresh's) file list.
    const id = ++requestId.current;
    let alive = true;
    const current = () => alive && id === requestId.current;
    setLoading(true);
    setError(null);
    setBridgeDown(false);
    bridge.projectTree(projectId)
      .then((res) => { if (current()) setNodes(buildTree(res)); })
      .catch((err) => {
        if (!current()) return;
        setError(errMessage(err));
        setBridgeDown(isBridgeUnavailable(err));
        setNodes([]);
      })
      .finally(() => { if (current()) setLoading(false); });
    return () => { alive = false; };
  }, [projectId, enabled, tick]);

  const files = useMemo(() => flattenTree(nodes).filter((n) => n.kind === "file"), [nodes]);
  return {
    nodes, files, loading, error, bridgeDown,
    refresh: useCallback(() => setTick((t) => t + 1), []),
  };
}

export function TreeView({ nodes, activePath, onOpen, filter = "", label = "Project files" }: {
  nodes: TreeNode[];
  activePath?: string | null;
  onOpen: (path: string) => void;
  filter?: string;
  label?: string;
}) {
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set());
  const [focusPath, setFocusPath] = useState<string | null>(null);
  const container = useRef<HTMLDivElement>(null);
  const all = useMemo(() => flattenTree(nodes), [nodes]);
  const query = filter.trim().toLowerCase();
  const matches = useMemo(() => {
    if (!query) return [];
    return all
      .filter((n) => n.kind === "file" && (n.path.toLowerCase().includes(query) || n.name.toLowerCase().includes(query)))
      .slice(0, 200);
  }, [all, query]);

  const toggle = (path: string) => setCollapsed((prev) => {
    const next = new Set(prev);
    if (next.has(path)) next.delete(path); else next.add(path);
    return next;
  });

  const onRowKey = (e: React.KeyboardEvent<HTMLButtonElement>, path: string, kind: "file" | "dir") => {
    const rows = Array.from(container.current?.querySelectorAll<HTMLElement>("[data-tree-row]") ?? []);
    const idx = rows.findIndex((r) => r.dataset.treeRow === path);
    if (e.key === "ArrowDown") {
      e.preventDefault();
      const next = rows[Math.min(idx + 1, rows.length - 1)];
      if (next) { setFocusPath(next.dataset.treeRow ?? null); next.focus(); }
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      const prev = rows[Math.max(idx - 1, 0)];
      if (prev) { setFocusPath(prev.dataset.treeRow ?? null); prev.focus(); }
    } else if (kind === "dir" && e.key === "ArrowRight") {
      e.preventDefault(); setCollapsed((v) => { const n = new Set(v); n.delete(path); return n; });
    } else if (kind === "dir" && e.key === "ArrowLeft") {
      e.preventDefault(); setCollapsed((v) => new Set(v).add(path));
    }
  };

  const firstPath = focusPath ?? all[0]?.path ?? null;

  const Row = ({ node, depth }: { node: TreeNode; depth: number }) => {
    const isDir = node.kind === "dir";
    const isCollapsed = collapsed.has(node.path);
    return (
      <React.Fragment key={node.path}>
        <button
          type="button"
          role="treeitem"
          aria-expanded={isDir ? !isCollapsed : undefined}
          aria-selected={!isDir && activePath === node.path}
          data-tree-row={node.path}
          tabIndex={node.path === firstPath ? 0 : -1}
          className={`${s.treeRow} ${!isDir && activePath === node.path ? s.treeRowActive : ""}`}
          style={{ paddingLeft: 6 + depth * 14 }}
          title={node.path}
          onClick={() => { if (isDir) toggle(node.path); else onOpen(node.path); }}
          onKeyDown={(e) => onRowKey(e, node.path, node.kind)}
        >
          <span className={s.treeLeading} aria-hidden="true">
            {isDir
              ? <Icon name="chevron" size={13} className={isCollapsed ? "" : s.chevronOpen} />
              : <Icon name="file" size={14} />}
          </span>
          <span className={s.treeName}>{node.name}</span>
          {!isDir && typeof node.size === "number" && <span className={s.treeSize}>{formatBytes(node.size)}</span>}
        </button>
        {isDir && !isCollapsed && node.children.map((child) => <Row key={child.path} node={child} depth={depth + 1} />)}
      </React.Fragment>
    );
  };

  return (
    <div className={s.tree} ref={container}>
      {query ? (
        matches.length ? (
          <div role="list" aria-label={`${label} matching “${filter}”`}>
            {matches.map((n) => (
              <button
                type="button"
                key={n.path}
                role="listitem"
                className={`${s.treeRow} ${activePath === n.path ? s.treeRowActive : ""}`}
                onClick={() => onOpen(n.path)}
                title={n.path}
              >
                <span className={s.treeLeading}><Icon name="file" size={14} /></span>
                <span className={s.treeName}>{n.path}</span>
              </button>
            ))}
          </div>
        ) : (
          <p className={s.hint}>No files match this filter.</p>
        )
      ) : nodes.length ? (
        <div role="tree" aria-label={label}>{nodes.map((n) => <Row key={n.path} node={n} depth={0} />)}</div>
      ) : (
        <p className={s.hint}>No files were found in this project.</p>
      )}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* syntax highlighting (small, dependency-free, no HTML injection)      */
/* ------------------------------------------------------------------ */

type TokenKind = "plain" | "comment" | "string" | "keyword" | "number" | "punct";
interface Token { text: string; kind: TokenKind }

const KEYWORDS = new Set([
  "const", "let", "var", "function", "return", "if", "else", "for", "while", "do", "switch",
  "case", "break", "continue", "class", "extends", "new", "this", "super", "import", "from",
  "export", "default", "async", "await", "try", "catch", "finally", "throw", "typeof",
  "interface", "type", "enum", "implements", "public", "private", "protected", "readonly",
  "def", "elif", "pass", "with", "as", "lambda", "yield", "raise", "except", "in", "is",
  "not", "and", "or", "None", "True", "False", "true", "false", "null", "undefined",
  "struct", "fn", "mut", "match", "use", "pub", "package", "func", "go", "defer",
]);

const TOKEN_RE = /(\/\/[^\n]*|\/\*[\s\S]*?\*\/|#[^\n]*)|("(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'|`(?:\\.|[^`\\])*`)|(\b\d+(?:\.\d+)?\b)|([A-Za-z_$][\w$]*)|([{}()[\].,;:+\-*/=<>!?&|~%^]+)/g;

function tokenize(line: string, lang: string): Token[] {
  const out: Token[] = [];
  let last = 0;
  const hashComments = lang === "py" || lang === "sh" || lang === "yaml" || lang === "ini";
  TOKEN_RE.lastIndex = 0;
  let m: RegExpExecArray | null;
  while ((m = TOKEN_RE.exec(line)) !== null) {
    if (m.index > last) out.push({ text: line.slice(last, m.index), kind: "plain" });
    const text = m[0];
    if (m[1]) out.push({ text, kind: text.startsWith("#") && !hashComments ? "plain" : "comment" });
    else if (m[2]) out.push({ text, kind: "string" });
    else if (m[3]) out.push({ text, kind: "number" });
    else if (m[4]) out.push({ text, kind: KEYWORDS.has(text) ? "keyword" : "plain" });
    else out.push({ text, kind: "punct" });
    last = m.index + text.length;
  }
  if (last < line.length) out.push({ text: line.slice(last), kind: "plain" });
  return out;
}

const MAX_LINES = 2000;

export function CodeView({ content, language }: { content: string; language: string }) {
  const lines = useMemo(() => content.replace(/\r\n/g, "\n").split("\n"), [content]);
  const shown = lines.slice(0, MAX_LINES);
  return (
    <div className={s.codeView}>
      <pre className={s.pre} tabIndex={0} aria-label={`Read-only ${language || "text"} source`}>
        <code>
          {shown.map((line, i) => (
            <span className={s.codeLine} key={i}>
              <span className={s.lineNo} aria-hidden="true">{i + 1}</span>
              <span className={s.lineText}>
                {tokenize(line, language).map((tok, j) => (
                  <span key={j} className={tok.kind === "plain" ? undefined : s[`tok_${tok.kind}`]}>{tok.text}</span>
                )) || "\u00a0"}
              </span>
            </span>
          ))}
        </code>
      </pre>
      {lines.length > MAX_LINES && (
        <p className={s.note}>Rendering the first {MAX_LINES.toLocaleString()} of {lines.length.toLocaleString()} lines. The full text is available while editing.</p>
      )}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* file viewer                                                         */
/* ------------------------------------------------------------------ */

export function FileView({ projectId, path, onDirtyChange }: {
  projectId: string;
  path: string;
  onDirtyChange?: (dirty: boolean) => void;
}) {
  const [data, setData] = useState<FileRead | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [bridgeDown, setBridgeDown] = useState(false);
  const [buffer, setBuffer] = useState("");
  const [dirty, setDirty] = useState(false);
  const [editing, setEditing] = useState(false);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const [reload, setReload] = useState(0);
  const readRequestId = useRef(0);
  const dirtyCb = useRef(onDirtyChange);
  const areaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => { dirtyCb.current = onDirtyChange; }, [onDirtyChange]);

  useEffect(() => {
    // A slow read for an older path/reload must never replace a newer file.
    const id = ++readRequestId.current;
    let alive = true;
    const current = () => alive && id === readRequestId.current;
    setLoading(true);
    setError(null);
    setSaveError(null);
    setBridgeDown(false);
    setEditing(false);
    setDirty(false);
    dirtyCb.current?.(false);
    bridge.readFile(projectId, path)
      .then((res) => { if (current()) { setData(res); setBuffer(typeof res?.content === "string" ? res.content : ""); } })
      .catch((err) => {
        if (!current()) return;
        setError(errMessage(err));
        setBridgeDown(isBridgeUnavailable(err));
        setData(null);
      })
      .finally(() => { if (current()) setLoading(false); });
    return () => { alive = false; };
  }, [projectId, path, reload]);

  const binary = Boolean(data?.binary) || String(data?.encoding ?? "").toLowerCase().includes("base64");
  const truncated = Boolean(data?.truncated);
  const language = fileLanguage(path);
  const original = typeof data?.content === "string" ? data.content : "";

  const markDirty = (v: string) => {
    setBuffer(v);
    const nowDirty = v !== original;
    setDirty(nowDirty);
    dirtyCb.current?.(nowDirty);
  };

  const requestSave = () => {
    if (!dirty || !data || binary || truncated || saving) return;
    setConfirmOpen(true);
  };

  const doSave = async () => {
    if (!data) return;
    setSaving(true);
    setError(null);
    try {
      await bridge.writeFile(projectId, path, buffer);
      setConfirmOpen(false);
      setEditing(false);
      setDirty(false);
      dirtyCb.current?.(false);
      setReload((n) => n + 1);
    } catch (err) {
      // Keep the failure distinct from a read failure. No write is retried
      // automatically: the operator must explicitly confirm another save.
      setSaveError(errMessage(err));
      setConfirmOpen(false);
    } finally { setSaving(false); }
  };

  const revert = () => {
    setBuffer(original);
    setDirty(false);
    dirtyCb.current?.(false);
    setEditing(false);
  };

  if (loading) return <div className={s.centered}><Spinner label="Reading file" /><p>Reading {path}…</p></div>;

  if (bridgeDown) return (
    <EmptyState
      icon={<Icon name="warning" size={26} />}
      title="The local bridge is unavailable"
      description={error ?? "The bridge could not be reached."}
      action={<Button onClick={() => setReload((n) => n + 1)} variant="primary"><Icon name="refresh" size={15} /> Retry</Button>}
    />
  );

  if (error) return (
    <EmptyState
      icon={<Icon name="error" size={26} />}
      title="Could not read this file"
      description={error}
      action={<Button onClick={() => setReload((n) => n + 1)}><Icon name="refresh" size={15} /> Retry</Button>}
    />
  );

  // A failed write is NOT a failed read. Never relabel it, and never let a
  // "Retry" affordance silently repeat a non-idempotent POST.
  if (saveError) return (
    <EmptyState
      icon={<Icon name="error" size={26} />}
      title="Could not save this file"
      description={`${saveError} The edited buffer is unchanged; no write was retried automatically. Return to the editor to confirm another save.`}
      action={<Button variant="primary" onClick={() => setSaveError(null)}>Return to editor</Button>}
    />
  );

  if (!data) return <EmptyState icon={<Icon name="file" size={26} />} title="No file selected" description="Choose a file from the project explorer." />;

  if (binary) return (
    <EmptyState
      icon={<Icon name="file" size={26} />}
      title="Binary file — no inline preview"
      description="The bridge reports this file is not UTF-8 text. Keel does not expose a project-file download endpoint, so no copy or preview is offered here."
    />
  );

  return (
    <div className={s.fileView} onKeyDown={(e) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "s") { e.preventDefault(); requestSave(); }
    }}>
      <header className={s.fileHead}>
        <div className={s.fileMeta}>
          <span className={s.mono}>{path}</span>
          {typeof data.size === "number" && <Badge>{formatBytes(data.size)}</Badge>}
          {truncated && <Badge tone="warning">Truncated by bridge read limit</Badge>}
          {dirty && <Badge tone="warning" dot>Unsaved</Badge>}
          <Badge tone="info">Read-only by default</Badge>
        </div>
        <div className={s.rowGap}>
          {!editing ? (
            <Button size="sm" disabled={truncated} onClick={() => { setEditing(true); window.setTimeout(() => areaRef.current?.focus(), 0); }}>
              <Icon name="edit" size={14} /> Edit
            </Button>
          ) : (
            <>
              <Button size="sm" variant="ghost" onClick={revert}>Revert</Button>
              <Button size="sm" variant="primary" disabled={!dirty || saving} onClick={requestSave}>
                <Icon name="check" size={14} /> Save…
              </Button>
            </>
          )}
          <IconButton
            label="Reload file from disk"
            onClick={() => {
              // Prevent silent data loss: reloading discards the in-memory buffer.
              if (dirty && !window.confirm("This file has unsaved edits. Reload from disk and discard them?")) return;
              setReload((n) => n + 1);
            }}
          >
            <Icon name="refresh" size={15} />
          </IconButton>
        </div>
      </header>
      {truncated && <p className={s.note}>The bridge capped this read. Only the returned prefix is shown; editing and writing are disabled to avoid truncating the file on disk.</p>}
      {editing ? (
        <textarea
          ref={areaRef}
          className={s.editorArea}
          value={buffer}
          onChange={(e) => markDirty(e.target.value)}
          aria-label={`Editing ${path}`}
          spellCheck={false}
        />
      ) : (
        <CodeView content={original} language={language} />
      )}
      <Dialog
        open={confirmOpen}
        onClose={() => setConfirmOpen(false)}
        title="Confirm file save"
        footer={<>
          <Button variant="ghost" onClick={() => setConfirmOpen(false)}>Cancel</Button>
          <Button variant="primary" loading={saving} onClick={() => void doSave()}>Write to disk</Button>
        </>}
      >
        <p>Write the edited buffer for <code className={s.mono}>{path}</code> to disk?</p>
        <p className={s.muted}>Original: {formatBytes(original.length)} · New: {formatBytes(buffer.length)}. This uses the guarded <code>bridge.writeFile</code> call and stays inside the trusted project root.</p>
      </Dialog>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* review (read-only)                                                   */
/* ------------------------------------------------------------------ */

interface StatusRow { path: string; state: string; additions?: number; deletions?: number }

function normalizeStatus(value: unknown): StatusRow[] {
  const out: StatusRow[] = [];
  if (Array.isArray(value)) {
    for (const v of value) {
      if (!v || typeof v !== "object") continue;
      const o = v as Record<string, unknown>;
      const p = String(o.path ?? o.file ?? "");
      if (!p) continue;
      const row: StatusRow = {
        path: p,
        state: String(o.state ?? o.status ?? "?"),
      };
      if (typeof o.additions === "number") row.additions = o.additions;
      if (typeof o.deletions === "number") row.deletions = o.deletions;
      out.push(row);
    }
    return out;
  }
  if (typeof value === "string") {
    for (const line of value.split(/\r?\n/)) {
      // `git status --porcelain` uses a two-column XY code. A worktree-only
      // modification is " M path" (leading space) and an index-only change is
      // "M  path"; both must be captured. Renames carry "old -> new".
      const m = line.match(/^([ \t]?[A-Za-z?!][A-Za-z?!]?)[ \t]+(.+)$/);
      if (!m) continue;
      out.push({ path: m[2].trim(), state: m[1].trim() });
    }
  }
  return out;
}

function textBlock(value: unknown): string {
  if (typeof value === "string") return value;
  if (Array.isArray(value)) return value.map((v) => String(v)).join("\n");
  if (value && typeof value === "object") return JSON.stringify(value, null, 2);
  return "";
}

export function ReviewView({ projectId }: { projectId: string }) {
  const [data, setData] = useState<ReviewData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [bridgeDown, setBridgeDown] = useState(false);
  const [tick, setTick] = useState(0);
  const requestId = useRef(0);

  useEffect(() => {
    // Refresh while a read is still pending must win: a slow older review
    // response can otherwise overwrite the newer Git state.
    const id = ++requestId.current;
    let alive = true;
    const current = () => alive && id === requestId.current;
    setLoading(true); setError(null); setBridgeDown(false);
    bridge.review(projectId)
      .then((res) => { if (current()) setData(res); })
      .catch((err) => {
        if (!current()) return;
        setError(errMessage(err)); setBridgeDown(isBridgeUnavailable(err)); setData(null);
      })
      .finally(() => { if (current()) setLoading(false); });
    return () => { alive = false; };
  }, [projectId, tick]);

  const refresh = () => setTick((t) => t + 1);
  const reportedBranch = data && typeof (data as Record<string, unknown>).branch === "string"
    ? (data as Record<string, unknown>).branch as string : "";
  const head = (
    <div className={s.panelHead}>
      <div>
        <h3>Review</h3>
        <p className={s.muted}>{reportedBranch ? `Branch: ${reportedBranch}` : "Branch not reported by bridge"}</p>
      </div>
      <div className={s.rowGap}>
        <Badge tone="info">Read-only</Badge>
        <IconButton label="Refresh review" onClick={refresh}><Icon name="refresh" size={15} /></IconButton>
      </div>
    </div>
  );

  if (loading) return (
    <div className={s.panelBody}>{head}
      <div className={s.centered}><Spinner label="Reading review" /><p>Reading Git state…</p></div>
    </div>
  );
  if (bridgeDown) return (
    <div className={s.panelBody}>{head}
      <EmptyState icon={<Icon name="warning" size={26} />} title="Bridge unavailable"
        description={error ?? "The bridge could not be reached."}
        action={<Button variant="primary" onClick={refresh}>Retry</Button>} />
    </div>
  );
  if (error) return (
    <div className={s.panelBody}>{head}
      <EmptyState icon={<Icon name="error" size={26} />} title="Review failed" description={error}
        action={<Button onClick={refresh}>Retry</Button>} />
    </div>
  );
  if (!data) return (
    <div className={s.panelBody}>{head}
      <EmptyState icon={<Icon name="info" size={26} />} title="No review data" description="The bridge returned no review payload." />
    </div>
  );

  const raw = data as ReviewData & Record<string, unknown>;
  const bridgeError = textBlock(raw.error);
  const isGit = raw.is_git === true || (raw.is_git === undefined && (Boolean(raw.status) || Boolean(raw.diff_stat)));
  const statusRows = normalizeStatus(raw.status);
  const diffStat = textBlock(raw.diff_stat ?? raw.diffstat);
  const log = textBlock(raw.log);
  const diff = textBlock(raw.diff);

  return (
    <div className={s.panelBody}>
      {head}
      {bridgeError && <p className={s.errorBox} role="alert">{bridgeError}</p>}
      {!isGit ? (
        <EmptyState icon={<Icon name="info" size={24} />} title="No Git work tree reported"
          description="The bridge reports this project is not inside a Git work tree, so there is no status or diff to show." />
      ) : (
        <>
          <SectionTitle action={statusRows.length ? <Badge>{statusRows.length} changed</Badge> : undefined}>Working tree</SectionTitle>
          {statusRows.length ? (
            <ul className={s.statusList}>
              {statusRows.map((r) => (
                <li key={r.path} className={s.statusRow}>
                  <code className={s.statusCode}>{r.state}</code>
                  <span className={s.statusPath} title={r.path}>{r.path}</span>
                  {(typeof r.additions === "number" || typeof r.deletions === "number") && (
                    <span className={s.statusNums}>
                      {typeof r.additions === "number" && <span className={s.add}>+{r.additions}</span>}
                      {typeof r.deletions === "number" && <span className={s.del}>−{r.deletions}</span>}
                    </span>
                  )}
                </li>
              ))}
            </ul>
          ) : <p className={s.hint}>No working-tree changes reported.</p>}

          <SectionTitle>Raw git status</SectionTitle>
          {textBlock(raw.status) ? <pre className={s.output}>{textBlock(raw.status)}</pre> : <p className={s.hint}>The bridge reported an empty working tree.</p>}

          <SectionTitle>Diffstat</SectionTitle>
          {diffStat ? <pre className={s.output}>{diffStat}</pre> : <p className={s.hint}>The bridge did not report a diffstat.</p>}

          <SectionTitle>Recent log</SectionTitle>
          {log ? <pre className={s.output}>{log}</pre> : <p className={s.hint}>The bridge did not report a commit log.</p>}

          <SectionTitle>File diffs</SectionTitle>
          {diff ? <pre className={s.output}>{diff}</pre> : (
            <p className={s.hint}>File-level diffs are not reported by this bridge endpoint; only porcelain status and diffstat are available. Apply / revert actions are intentionally not offered.</p>
          )}
        </>
      )}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* terminal                                                            */
/* ------------------------------------------------------------------ */

interface TerminalSession {
  handle: string;
  command: string;
  cwd: string | null;
  running: boolean;
  exitCode: number | null;
  output: string;
  error: string | null;
  truncated: boolean;
}

export interface TerminalState { running: number; total: number }

export function TerminalView({ projectId, cwd, onStateChange }: {
  projectId: string;
  cwd?: string | null;
  onStateChange?: (state: TerminalState) => void;
}) {
  const [sessions, setSessions] = useState<TerminalSession[]>([]);
  const [command, setCommand] = useState("");
  const [starting, setStarting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState<string | null>(null);
  const [killing, setKilling] = useState<string | null>(null);
  const outRef = useRef<HTMLDivElement>(null);
  const stateCb = useRef(onStateChange);
  useEffect(() => { stateCb.current = onStateChange; }, [onStateChange]);

  const runningKey = sessions.filter((x) => x.running).map((x) => x.handle).join(",");

  useEffect(() => {
    stateCb.current?.({ running: sessions.filter((x) => x.running).length, total: sessions.length });
  }, [sessions, runningKey]);

  useEffect(() => {
    if (!runningKey) return;
    const handles = runningKey.split(",");
    let alive = true;
    const tick = async () => {
      const results = await Promise.allSettled(handles.map(async (handle) => ({ handle, data: await bridge.shellOutput(handle) })));
      if (!alive) return;
      setSessions((prev) => prev.map((sess) => {
        if (!sess.running) return sess;
        const found = results.find((r) => r.status === "fulfilled" && r.value.handle === sess.handle);
        if (!found || found.status === "rejected") {
          return { ...sess, running: false, error: found?.status === "rejected" ? errMessage(found.reason) : "Output unavailable" };
        }
        const d = found.value.data as ShellHandle & Record<string, unknown>;
        if (typeof d.error === "string" && !d.output) {
          return { ...sess, running: false, error: d.error };
        }
        return {
          ...sess,
          output: typeof d.output === "string" ? d.output : sess.output,
          running: d.running === true,
          exitCode: typeof d.exit_code === "number" ? d.exit_code : null,
          truncated: d.truncated === true,
          error: typeof d.error === "string" ? d.error : null,
        };
      }));
    };
    void tick();
    const timer = window.setInterval(() => { void tick(); }, 1200);
    return () => { alive = false; window.clearInterval(timer); };
  }, [runningKey]);

  useEffect(() => { outRef.current?.scrollTo({ top: outRef.current.scrollHeight }); }, [sessions]);

  const run = async (e: React.FormEvent) => {
    e.preventDefault();
    const cmd = command.trim();
    if (!cmd || starting) return;
    setStarting(true); setError(null);
    try {
      const res = await bridge.terminalExec(projectId, cmd);
      const handle = String(res?.handle ?? res?.id ?? "");
      if (!handle) throw new Error("The bridge did not return a shell handle.");
      setSessions((prev) => [...prev, {
        handle,
        command: cmd,
        cwd: typeof res?.cwd === "string" ? res.cwd : (cwd ?? null),
        running: res?.running !== false,
        exitCode: null,
        output: "",
        error: null,
        truncated: false,
      }]);
      setCommand("");
    } catch (err) {
      setError(errMessage(err));
    } finally { setStarting(false); }
  };

  const clearFinished = async () => {
    try {
      await bridge.clearFinishedShells();
      setSessions((prev) => prev.filter((x) => x.running));
    } catch (err) { setError(errMessage(err)); }
  };

  const copy = async (text: string, handle: string) => {
    try { await navigator.clipboard.writeText(text); setCopied(handle); window.setTimeout(() => setCopied(null), 1500); }
    catch { setError("Clipboard access was denied by the browser."); }
  };

  /** Stop uses the real guarded bridge endpoint. The bridge reports honestly
   *  when a handle is unknown or the process is already gone. */
  const stop = async (sess: TerminalSession) => {
    setKilling(sess.handle);
    setError(null);
    try {
      await bridge.killShell(sess.handle);
      setSessions((prev) => prev.map((x) => x.handle === sess.handle
        ? { ...x, output: `${x.output}${x.output ? "\n" : ""}[Keel] Stop requested via bridge.killShell. Waiting for process exit…` }
        : x));
      // Confirm the real state instead of assuming the kill succeeded.
      const res = await bridge.shellOutput(sess.handle) as ShellHandle & Record<string, unknown>;
      setSessions((prev) => prev.map((x) => x.handle === sess.handle ? {
        ...x,
        running: res?.running === true,
        exitCode: typeof res?.exit_code === "number" ? res.exit_code : x.exitCode,
        output: typeof res?.output === "string" ? res.output : x.output,
        error: typeof res?.error === "string" ? res.error : null,
      } : x));
    } catch (err) {
      setError(errMessage(err));
    } finally { setKilling(null); }
  };

  return (
    <div className={s.terminal}>
      <div className={s.panelHead}>
        <div>
          <h3>Terminal</h3>
          <p className={s.muted}>Working directory: <code className={s.mono}>{cwd ?? "not reported by bridge"}</code></p>
        </div>
        <div className={s.rowGap}>
          <Badge tone={sessions.some((x) => x.running) ? "warning" : "neutral"} dot>
            {sessions.some((x) => x.running) ? "Process running" : "Idle"}
          </Badge>
          <Button size="sm" variant="ghost" onClick={() => void clearFinished()}><Icon name="trash" size={14} /> Clear finished</Button>
        </div>
      </div>
      <p className={s.note}>Commands run in the trusted project folder through Keel&apos;s guarded shell runner. The bridge permission system can refuse a command; the refusal is shown here verbatim and is never bypassed.</p>
      {error && <p className={s.errorBox} role="alert">{error}</p>}
      <form className={s.termForm} onSubmit={(e) => void run(e)}>
        <label className="sr-only" htmlFor={`term-${projectId}`}>Shell command</label>
        <span className={s.prompt} aria-hidden="true">$</span>
        <input
          id={`term-${projectId}`}
          className={s.termInput}
          value={command}
          onChange={(e) => setCommand(e.target.value)}
          placeholder="Run a command in this project…"
          autoComplete="off"
          spellCheck={false}
          disabled={starting}
        />
        <Button size="sm" variant="primary" type="submit" loading={starting} disabled={!command.trim()}>
          <Icon name="play" size={14} /> Run
        </Button>
      </form>
      <div className={s.termOutputs} ref={outRef}>
        {!sessions.length ? (
          <EmptyState icon={<Icon name="terminal" size={24} />} title="No commands run yet"
            description="Output and exit codes appear here. Each command runs as a detached process tracked by its bridge handle." />
        ) : sessions.map((sess) => (
          <section key={sess.handle} className={s.termSession} aria-label={`Shell ${sess.handle}`}>
            <header className={s.termSessionHead}>
              <code className={s.mono}>$ {sess.command}</code>
              <div className={s.rowGap}>
                <Badge tone={sess.running ? "warning" : sess.exitCode === 0 ? "success" : "danger"} dot>
                  {sess.running ? "running" : `exit ${sess.exitCode ?? "unknown"}`}
                </Badge>
                {sess.running && (
                  <Button size="sm" variant="ghost" loading={killing === sess.handle} onClick={() => void stop(sess)}>
                    <Icon name="stop" size={14} /> Stop
                  </Button>
                )}
                <IconButton label={`Copy output of ${sess.handle}`} onClick={() => void copy(sess.output, sess.handle)}>
                  <Icon name={copied === sess.handle ? "check" : "copy"} size={14} />
                </IconButton>
              </div>
            </header>
            {sess.cwd && <p className={s.muted}>cwd: <code className={s.mono}>{sess.cwd}</code></p>}
            {sess.error && <p className={s.errorBox} role="alert">{sess.error}</p>}
            {sess.output ? <pre className={s.output}>{sess.output}</pre> : !sess.error && <p className={s.hint}>No output returned yet.</p>}
            {sess.truncated && <p className={s.hint}>Bridge output was truncated at its capture limit.</p>}
          </section>
        ))}
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* context / environment                                               */
/* ------------------------------------------------------------------ */

function Fact({ label, value, missing }: { label: string; value?: string; missing?: string }) {
  return (
    <div className={s.fact}>
      <dt>{label}</dt>
      <dd>{value ? <span className={s.mono}>{value}</span> : <span className={s.notReported}>{missing ?? "not reported by bridge"}</span>}</dd>
    </div>
  );
}

export function ContextView({ project }: { project: Project | null }) {
  const [providers, setProviders] = useState<string[]>([]);
  const [tokens, setTokens] = useState<string | null>(null);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    let alive = true;
    Promise.allSettled([bridge.providers(), bridge.usage()]).then(([p, u]) => {
      if (!alive) return;
      const list = asArray<Record<string, unknown>>(p.status === "fulfilled" ? p.value : null, ["providers"])
        .filter((x) => x.configured === true || x.connected === true)
        .map((x) => String(x.name ?? x.id ?? ""));
      setProviders(list.filter(Boolean));
      if (u.status === "fulfilled") {
        const o = (u.value ?? {}) as Record<string, unknown>;
        const usage = (o.usage && typeof o.usage === "object" ? o.usage : o) as Record<string, unknown>;
        const input = typeof usage.input_tokens === "number" ? usage.input_tokens : undefined;
        const output = typeof usage.output_tokens === "number" ? usage.output_tokens : undefined;
        if (input !== undefined || output !== undefined) {
          setTokens(`${(input ?? 0).toLocaleString()} in / ${(output ?? 0).toLocaleString()} out`);
        }
      }
      setLoaded(true);
    });
    return () => { alive = false; };
  }, []);

  const model = typeof project?.model === "string" && project.model ? project.model : undefined;

  return (
    <div className={s.panelBody}>
      <div className={s.panelHead}><div><h3>Context</h3><p className={s.muted}>Facts from the bridge only</p></div></div>
      <SectionTitle>Workspace</SectionTitle>
      <dl className={s.factList}>
        <Fact label="Project" value={project?.name} missing="no project selected" />
        <Fact label="Absolute path" value={project?.path} missing="not reported by bridge" />
        <Fact label="Project model" value={model} />
        <Fact label="Permission mode" missing="not reported by this bridge endpoint" />
      </dl>
      <SectionTitle>Model / provider</SectionTitle>
      {!loaded ? <p className={s.hint}>Reading bridge state…</p> : providers.length ? (
        <ul className={s.simpleList}>{providers.map((p) => <li key={p}>{p}</li>)}</ul>
      ) : <p className={s.hint}>No configured provider was reported by the bridge.</p>}
      <SectionTitle>Tokens</SectionTitle>
      {!loaded ? <p className={s.hint}>Reading bridge state…</p> : tokens
        ? <p className={s.mono}>{tokens}<span className={s.muted}> (session total, as reported)</span></p>
        : <p className={s.hint}>Token counts were not reported by the bridge.</p>}
    </div>
  );
}

export function EnvironmentView({ project, projectId }: { project: Project | null; projectId: string | null }) {
  const [shells, setShells] = useState<ShellHandle[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [tick, setTick] = useState(0);

  useEffect(() => {
    let alive = true;
    bridge.shells()
      .then((res) => { if (alive) setShells(asArray<ShellHandle>(res, ["shells"])); })
      .catch((err) => { if (alive) setError(errMessage(err)); });
    return () => { alive = false; };
  }, [projectId, tick]);

  return (
    <div className={s.panelBody}>
      <div className={s.panelHead}>
        <div><h3>Environment</h3><p className={s.muted}>Workspace and local runtime facts</p></div>
        <IconButton label="Refresh environment" onClick={() => setTick((t) => t + 1)}><Icon name="refresh" size={15} /></IconButton>
      </div>
      <SectionTitle>Workspace</SectionTitle>
      <dl className={s.factList}>
        <Fact label="Absolute path" value={project?.path} missing="not reported by bridge" />
        <Fact label="Trust state" value={project ? (project.trusted ? "trusted" : "not trusted") : undefined} missing="no project selected" />
        <Fact label="Shell list endpoint" value="/api/fleet/shells" />
        <Fact label="Transport" value="same-origin /api/bridge/*" />
      </dl>
      <SectionTitle>Tracked shells</SectionTitle>
      {error && <p className={s.errorBox} role="alert">{error}</p>}
      {shells.length ? (
        <ul className={s.simpleList}>
          {shells.map((sh) => {
            const handle = String(sh.handle ?? sh.id ?? "?");
            const running = sh.running === true;
            return <li key={handle}><code className={s.mono}>{handle}</code> — {running ? "running" : `exit ${sh.exit_code ?? "unknown"}`} <span className={s.muted}>{String(sh.command ?? "")}</span></li>;
          })}
        </ul>
      ) : <p className={s.hint}>No shells are tracked. Terminal sessions started from the Code panel may be excluded from this list by the bridge.</p>}
      <SectionTitle>Not exposed by this bridge</SectionTitle>
      <ul className={s.simpleList}>
        <li>No project preview URL endpoint — a local browser preview cannot be opened from bridge data alone.</li>
        <li>No permission-mode or token-limit field on the project response.</li>
        <li>No file upload endpoint for project files.</li>
      </ul>
    </div>
  );
}

/** Small reusable bridge-unavailable banner with a real retry. */
export function BridgeError({ message, onRetry }: { message: string | null; onRetry: () => void }) {
  if (!message) return null;
  return (
    <div className={s.bridgeBanner} role="alert">
      <Icon name="warning" size={16} />
      <span>{message}</span>
      <Button size="sm" onClick={onRetry}>Retry</Button>
    </div>
  );
}

export function EmptyProject({ onAdd }: { onAdd: () => void }) {
  return (
    <EmptyState
      icon={<Icon name="folder" size={28} />}
      title="No project selected"
      description="Add a local folder path that the Keel bridge can access. Keel will ask for trust before reading files or running commands."
      action={<Button variant="primary" onClick={onAdd}><Icon name="plus" size={15} /> Add project</Button>}
    />
  );
}
