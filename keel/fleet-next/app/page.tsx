"use client";

import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { api } from "@/lib/client";

/* ----------------------------------------------------------- ask card */

function AskCard({ row, onAnswer }: { row: Row; onAnswer: (row: Row, answer: string) => void }) {
  const b = row.body ?? {};
  const options: string[] = Array.isArray(b.options) ? b.options : [];
  const [text, setText] = useState("");
  const answered = b.status === "answered";
  if (answered) {
    return (
      <div className="ask-card" role="status">
        <div className="ask-title">Question answered</div>
        <div className="ask-answer"><b>You:</b> {b.answer}</div>
      </div>
    );
  }
  return (
    <div className="ask-card" role="dialog" aria-modal="true" aria-label="Agent is asking">
      <div className="ask-title">Agent is asking · waiting for you</div>
      <div className="ask-question">{b.question}</div>
      {options.length > 0 && (
        <div className="ask-options">
          {options.map((o) => (
            <button key={o} className="ask-option" onClick={() => onAnswer(row, o)}>{o}</button>
          ))}
        </div>
      )}
      <form className="ask-input-row" onSubmit={(e) => { e.preventDefault(); const t = text.trim(); if (t) onAnswer(row, t); }}>
        <input placeholder="Type your answer…" value={text} onChange={(e) => setText(e.target.value)} aria-label="Your answer" autoFocus />
        <button className="btn primary" type="submit" disabled={!text.trim()}>Answer</button>
      </form>
    </div>
  );
}



type View = "agents" | "tasks" | "library" | "routines";
type DrawerTab = "engine" | "notes";
type Surface = "cowork" | "code" | "duet" | "fleet";
type CowView = "home" | "chat" | "projects" | "artifacts" | "scheduled" | "customize";
type CustomizeTab = "skills" | "connectors" | "plugins";
type ModeSetting = "build" | "plan" | "autopilot" | "acceptEdits";

interface Bot {
  id: string;
  name: string;
  role?: string;
  engine: string;
  provider: string;
  model: string;
  notes?: string;
  avatar_hue?: number;
  reasoning_effort?: string;
}
interface Row {
  seq: number;
  bot_id?: string;
  kind: string;
  body: any;
  created_at: string;
}
interface ProviderInfo {
  name: string;
  configured: boolean;
  session?: boolean;
  default_model: string;
}
interface TaskItem {
  id: string;
  title: string;
  status: string;
  priority?: string;
  assigned_bot_id?: string | null;
}
interface FileItem {
  id: string;
  name: string;
  size: number;
  mime?: string;
  bot_id?: string;
}
interface RoutineItem {
  id: string;
  name: string;
  cron_expr: string;
  timezone?: string;
  last_run_status?: string | null;
  next_run_at?: string | null;
  paused?: number;
}

const fmtBytes = (n: number) =>
  n >= 1_000_000 ? `${(n / 1_000_000).toFixed(1)} MB` : `${Math.max(1, Math.round(n / 1000))} KB`;

const initials = (name: string) => (name.trim()[0] ?? "?").toUpperCase();
const hueOf = (bot: Bot | null | undefined, fallback = 24) => bot?.avatar_hue ?? fallback;

const NAV: { id: View; label: string }[] = [
  { id: "agents", label: "Chats" },
  { id: "tasks", label: "Tasks" },
  { id: "library", label: "Library" },
  { id: "routines", label: "Routines" },
];

const QUICK_STARTS = [
  {
    icon: "code",
    title: "Write a script",
    prompt: "Write a TypeScript script that fetches data from an API and processes it.",
  },
  {
    icon: "doc",
    title: "Analyze my tasks",
    prompt: "Summarize the active tasks across my fleet and suggest what to do next.",
  },
  {
    icon: "bolt",
    title: "Brainstorm ideas",
    prompt: "Brainstorm 10 innovative product ideas for AI-powered tools this year.",
  },
  {
    icon: "globe",
    title: "Research a topic",
    prompt: "Give me a thorough research overview of quantum computing and its applications, from what you know.",
  },
] as const;

function QuickIcon({ kind }: { kind: string }) {
  const common = { width: 16, height: 16, viewBox: "0 0 24 24", fill: "none", stroke: "currentColor", strokeWidth: 1.7, strokeLinecap: "round" as const, strokeLinejoin: "round" as const };
  if (kind === "code") return (<svg {...common}><path d="M9 8l-4 4 4 4M15 8l4 4-4 4M13 6l-2 12" /></svg>);
  if (kind === "doc") return (<svg {...common}><path d="M7 3h8l4 4v14H7zM15 3v4h4M10 12h6M10 16h6" /></svg>);
  if (kind === "bolt") return (<svg {...common}><path d="M13 3L5 14h6l-1 7 8-11h-6z" /></svg>);
  return (<svg {...common}><circle cx="12" cy="12" r="9" /><path d="M3 12h18M12 3c3 3 3 15 0 18M12 3c-3 3-3 15 0 18" /></svg>);
}

/* ====================================================== duet (coding) */

type DuetTabKind = "review" | "terminal" | "openfile" | "browser" | "file";
interface DuetTab {
  id: string;
  kind: DuetTabKind;
  path?: string;
}
interface TreeEntry {
  path: string;
  name: string;
  size: number;
  dir: string;   // parent directory, "" at root, forward slashes
}
interface TreeNode {
  name: string;
  path: string;  // full relative path from project root
  isDir: boolean;
  size?: number;
  children: TreeNode[];
}
interface CachedFile {
  path: string;
  name: string;
  content: string;
  base64: string;
  binary: boolean;
  mime: string;
  size: number;
  truncated: boolean;
  dirty: boolean;
}
interface ProjectInfo {
  id: string;
  path: string;
  name: string;
  model: string | null;
  last_opened_at: string;
  trusted?: number;
}

const SLASH_COMMANDS: { name: string; desc: string; aliases: string[] }[] = [
  { name: "context", desc: "Token usage recorded by the bridge — all agents, this install", aliases: ["cost", "usage"] },
  { name: "model", desc: "/model <name> — switch this agent's model", aliases: [] },
  { name: "shell", desc: "/shell <command> — run it in the project terminal", aliases: ["sh"] },
  { name: "review", desc: "Open the Review tab (git status · log · diffstat)", aliases: ["diff"] },
  { name: "open", desc: "/open <path> — open a project file in a tab", aliases: [] },
  { name: "help", desc: "Everything Keel Duet can do", aliases: ["?"] },
];

const TEXT_FILE_EXTENSIONS = new Set([
  "txt", "md", "markdown", "json", "jsonl", "ndjson", "csv", "tsv", "xml", "svg",
  "yaml", "yml", "toml", "ini", "cfg", "conf", "env", "log", "sql", "graphql",
  "ts", "tsx", "js", "jsx", "mjs", "cjs", "d.ts", "py", "pyw", "rb", "go", "rs",
  "java", "kt", "swift", "c", "h", "cpp", "hpp", "cc", "cs", "php", "lua",
  "sh", "bash", "zsh", "fish", "ps1", "psm1", "bat", "cmd", "html", "htm", "css",
  "scss", "less", "vue", "svelte", "astro", "dart", "r", "jl", "ex", "exs", "erl",
  "clj", "scala", "groovy", "pl", "pm", "vim", "dockerfile", "gitignore", "makefile",
]);

function isTextLike(name: string, mime: string, size: number): boolean {
  if (mime.startsWith("text/")) return true;
  if (/(json|javascript|xml|yaml|toml|csv|markdown|sql|graphql|x-sh)/.test(mime)) return true;
  const ext = (name.split(".").pop() ?? "").toLowerCase();
  if (TEXT_FILE_EXTENSIONS.has(ext)) return true;
  return size <= 64 * 1024 && !mime;
}

/* ========================================================== page */

export default function FleetPage() {
  const [view, setView] = useState<View>("agents");
  const [bots, setBots] = useState<Bot[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [rows, setRows] = useState<Row[]>([]);
  const [live, setLive] = useState(false);
  const [toast, setToast] = useState<string | null>(null);
  const [draft, setDraft] = useState("");
  const [search, setSearch] = useState("");
  const [greeting, setGreeting] = useState("Welcome");
  const [streamText, setStreamText] = useState("");
  const [busy, setBusy] = useState(false);          // a turn is in flight
  const [shellsPanel, setShellsPanel] = useState(false);
  const shellsRef = useRef<HTMLDivElement | null>(null);
  const [shells, setShells] = useState<any[]>([]);
  const [mode, setMode] = useState<ModeSetting>("build");
  const [queue, setQueue] = useState<{ id: number; content: string; mode: ModeSetting }[]>([]);
  const queueId = useRef(1);
  const [modelsMeta, setModelsMeta] = useState<{ id: string; supported_parameters?: string[]; reasoning?: { supported_efforts: string[]; default_effort?: string | null; mandatory?: boolean } | null }[]>([]);
  const [effortSel, setEffortSel] = useState("");
  const [decidedApprovals, setDecidedApprovals] = useState<Record<number, "once" | "always" | "deny">>({});
  const [toastAction, setToastAction] = useState<{ label: string; run: () => void } | null>(null);
  const [editingTaskId, setEditingTaskId] = useState<string | null>(null);
  const [editTitle, setEditTitle] = useState("");
  const [dragId, setDragId] = useState<string | null>(null);
  const [dropTarget, setDropTarget] = useState<{ id: string; before: boolean } | null>(null);
  const [theme, setTheme] = useState<"light" | "dark">("light");

  /* ---- Duet (coding surface) */
  const [surface, setSurface] = useState<Surface>("cowork");
  const [cowView, setCowView] = useState<CowView>("home");
  const [customizeTab, setCustomizeTab] = useState<CustomizeTab>("skills");
  const [menuOpen, setMenuOpen] = useState(false);
  const [trustTarget, setTrustTarget] = useState<ProjectInfo | null>(null);
  const [pendingProjectId, setPendingProjectId] = useState<string | null>(null);
  const [artifacts, setArtifacts] = useState<FileItem[]>([]);
  const [artifactPreview, setArtifactPreview] = useState<FileItem | null>(null);
  const [skills, setSkills] = useState<any[] | null>(null);
  const [skillsFilter, setSkillsFilter] = useState("");
  const [connectors, setConnectors] = useState<any[] | null>(null);
  const [keepAwake, setKeepAwake] = useState<{ supported: boolean; on: boolean } | null>(null);
  const [projectModalOpen, setProjectModalOpen] = useState(false);
  const [modalPathInput, setModalPathInput] = useState("");
  const [artifactAskOpen, setArtifactAskOpen] = useState(false);
  const [routineModalOpen, setRoutineModalOpen] = useState(false);
  const [routineName, setRoutineName] = useState("");
  const [routinePrompt, setRoutinePrompt] = useState("");
  const [routineCron, setRoutineCron] = useState("0 8 * * *");
  const [routineTz, setRoutineTz] = useState("UTC");
  const coworkFolderRef = useRef<HTMLInputElement | null>(null);
  const [defaultProjectId, setDefaultProjectId] = useState<string | null>(() => {
    try { return window.localStorage.getItem("keel-default-project"); } catch { return null; }
  });
  const [projects, setProjects] = useState<ProjectInfo[]>([]);
  const [activeProjectId, setActiveProjectId] = useState<string | null>(null);
  const [projectPathInput, setProjectPathInput] = useState("");
  const [projectAdding, setProjectAdding] = useState(false);
  const [treeEntries, setTreeEntries] = useState<TreeEntry[]>([]);
  const [treeLoading, setTreeLoading] = useState(false);
  const [expandedDirs, setExpandedDirs] = useState<Record<string, boolean>>({ "": true });
  const [duetTabs, setDuetTabs] = useState<DuetTab[]>([
    { id: "review", kind: "review" },
    { id: "terminal", kind: "terminal" },
    { id: "openfile", kind: "openfile" },
  ]);
  const [activeDuetTab, setActiveDuetTab] = useState<string>("review");
  const [tabAddOpen, setTabAddOpen] = useState(false);
  const [fileCache, setFileCache] = useState<Record<string, CachedFile>>({});
  const [fileLoading, setFileLoading] = useState(false);
  const [quickOpenPath, setQuickOpenPath] = useState("");
  const [termInput, setTermInput] = useState("");
  const [termShell, setTermShell] = useState<"powershell" | "cmd" | "posix">(
    typeof navigator !== "undefined" && /win/i.test(navigator.platform) ? "powershell" : "posix");
  const [termLines, setTermLines] = useState<string[]>([
    "Keel Duet terminal — commands run detached, one process per line.",
    "Pick a project on the left first; output streams in below.",
  ]);
  const [termBusy, setTermBusy] = useState(false);
  const [termHistory, setTermHistory] = useState<string[]>([]);
  const [termHistIdx, setTermHistIdx] = useState(-1);
  const termOutRef = useRef(0);            // bytes of output consumed from the active shell
  const termHandleRef = useRef<string | null>(null);
  const termLinesRef = useRef<HTMLPreElement | null>(null);
  const [reviewData, setReviewData] = useState<any>(null);
  const [reviewLoading, setReviewLoading] = useState(false);
  const [browserUrl, setBrowserUrl] = useState("http://localhost:3000");
  const [browserLoadedUrl, setBrowserLoadedUrl] = useState("");
  const [usageOpen, setUsageOpen] = useState(false);
  const [usageData, setUsageData] = useState<any>(null);
  const [helpOpen, setHelpOpen] = useState(false);
  const [slashDismissed, setSlashDismissed] = useState(false);
  const [slashIdx, setSlashIdx] = useState(0);
  const attachRef = useRef<HTMLInputElement | null>(null);

  const [tasks, setTasks] = useState<TaskItem[]>([]);
  const [files, setFiles] = useState<FileItem[]>([]);
  const [routines, setRoutines] = useState<RoutineItem[]>([]);
  const [taskFilter, setTaskFilter] = useState<"all" | "active">("active");
  const [newTask, setNewTask] = useState("");

  const [drawerOpen, setDrawerOpen] = useState(false);
  const [drawerTab, setDrawerTab] = useState<DrawerTab>("engine");
  const [providers, setProviders] = useState<ProviderInfo[]>([]);
  const [modelList, setModelList] = useState<string[]>([]);
  const [providerSel, setProviderSel] = useState("auto");
  const [modelSel, setModelSel] = useState("");
  const [keyInput, setKeyInput] = useState("");
  const [keyStatus, setKeyStatus] = useState("");
  const [keyBusy, setKeyBusy] = useState(false);
  const [notes, setNotes] = useState("");

  const [modalOpen, setModalOpen] = useState(false);
  const [newName, setNewName] = useState("");
  const [newRole, setNewRole] = useState("");
  const [newEngine, setNewEngine] = useState<"provider" | "echo">("provider");
  const [newHue, setNewHue] = useState(210);
  const [nameError, setNameError] = useState("");

  const selectedIdRef = useRef<string | null>(null);
  useEffect(() => { selectedIdRef.current = selectedId; }, [selectedId]);
  const rowsEndRef = useRef<HTMLDivElement | null>(null);
  const segRef = useRef<HTMLDivElement | null>(null);
  const segBtns = useRef<(HTMLButtonElement | null)[]>([]);
  const [segBox, setSegBox] = useState<{ left: number; width: number }>({ left: 0, width: 0 });
  const composerRef = useRef<HTMLInputElement | null>(null);
  const searchRef = useRef<HTMLInputElement | null>(null);

  const selectedBot = bots.find((b) => b.id === selectedId) ?? null;

  const say = (msg: string) => {
    setToast(msg);
    setToastAction(null);
    window.setTimeout(() => { setToast(null); setToastAction(null); }, 3200);
  };
  const sayAction = (msg: string, label: string, run: () => void) => {
    setToast(msg);
    setToastAction({ label, run });
    window.setTimeout(() => { setToast(null); setToastAction(null); }, 9000);
  };

  const toggleTheme = () => {
    const next = theme === "dark" ? "light" : "dark";
    document.documentElement.dataset.theme = next;
    try { localStorage.setItem("keel-theme", next); } catch { /* ignore */ }
    setTheme(next);
  };

  useLayoutEffect(() => {
    const idx = NAV.findIndex((n) => n.id === view);
    const btn = segBtns.current[idx];
    if (btn) setSegBox({ left: btn.offsetLeft, width: btn.offsetWidth });
  }, [view]);
  useEffect(() => {
    const onResize = () => {
      const idx = NAV.findIndex((n) => n.id === view);
      const btn = segBtns.current[idx];
      if (btn) setSegBox({ left: btn.offsetLeft, width: btn.offsetWidth });
    };
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, [view]);

  /* ---- data loaders */
  async function refreshBots() {
    try {
      const body = await api("bots");
      setBots(body.bots ?? []);
    } catch (err: any) { console.error("bots load failed", err); }
  }
  async function loadRows(id: string) {
    try {
      const body = await api(`bots/${id}/rows`);
      setRows(body.rows ?? []);
    } catch (err: any) { console.error("rows load failed", err); }
  }
  async function loadProviders() {
    try {
      const body = await api("providers");
      setProviders(body.providers ?? []);
    } catch (err: any) { console.error("providers load failed", err); }
  }
  async function refreshTasks() {
    try {
      const body = await api("tasks");
      setTasks(body.tasks ?? []);
    } catch (err: any) { console.error("tasks load failed", err); }
  }
  async function refreshView(v: View) {
    try {
      if (v === "tasks") await refreshTasks();
      else if (v === "library") setFiles((await api("library")).files ?? []);
      else if (v === "routines") await refreshRoutines();
    } catch (err: any) {
      console.error(`${v} load failed`, err);
      say(`Couldn't load ${v}: ${err.message}`);
    }
  }

  /* ---- keyboard shortcuts: Esc closes pop-ups, / focuses search */
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        setModalOpen(false);
        setDrawerOpen(false);
        setTabAddOpen(false);
        setHelpOpen(false);
        setUsageOpen(false);
        setMenuOpen(false);
        setProjectModalOpen(false);
        setRoutineModalOpen(false);
        setArtifactPreview(null);
        setArtifactAskOpen(false);
        setSlashDismissed(true);
        return;
      }
      if (e.ctrlKey && (e.key === "u" || e.key === "U")) {
        e.preventDefault();
        attachRef.current?.click();
        return;
      }
      if (e.key === "/" && !/input|textarea|select/i.test(String((e.target as HTMLElement)?.tagName))) {
        e.preventDefault();
        searchRef.current?.focus();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    const h = new Date().getHours();
    setGreeting(h < 5 ? "Good night" : h < 12 ? "Good morning" : h < 18 ? "Good afternoon" : "Good evening");
    try {
      setTheme(document.documentElement.dataset.theme === "dark" ? "dark" : "light");
      const stored = window.localStorage.getItem("keel-mode");
      if (stored === "plan" || stored === "build" || stored === "autopilot" || stored === "acceptEdits") {
        setMode(stored as ModeSetting);
      }
    } catch { /* ignore */ }
    refreshBots();
    loadProviders();
    refreshTasks();
    void loadProjects();
    void refreshArtifacts();
    void loadUsageData();
    void loadKeepAwake();
    try {
      const stored = window.localStorage.getItem("keel-surface");
      if (stored === "duet" || stored === "code" || stored === "cowork" || stored === "fleet") {
        setSurface(stored as Surface);
      }
    } catch { /* ignore */ }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    const es = new EventSource("/api/bridge/events");
    const onOpen = () => setLive(true);
    const onError = () => setLive(false);
    let timer: number | null = null;
    const onRow = (ev: MessageEvent) => {
      try {
        const row = JSON.parse(ev.data);
        // live token stream: ephemeral, not in the rows table
        if (row?.type === "stream") {
          if (row.bot_id === selectedIdRef.current) {
            setStreamText((t) => t + (row.delta || ""));
          }
          return;
        }
        if (row?.bot_id && row.bot_id === selectedIdRef.current) {
          if (row.kind === "turn_end") {
            setBusy(false);
            flushQueue();
            void loadUsageData();
          }
          if (timer) window.clearTimeout(timer);
          timer = window.setTimeout(() => {
            void (async () => {
              if (selectedIdRef.current) await loadRows(selectedIdRef.current);
              // swapping the stream bubble for the persisted message is
              // seamless once the reloaded transcript has rendered
              setStreamText("");
            })();
          }, 120);
        }
      } catch { /* ignore bad frame */ }
    };
    es.addEventListener("open", onOpen);
    es.addEventListener("error", onError);
    es.addEventListener("row", onRow as EventListener);
    return () => {
      if (timer) window.clearTimeout(timer);
      es.close();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (!selectedId) { setRows([]); setStreamText(""); return; }
    setStreamText("");
    loadRows(selectedId);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedId]);

  useEffect(() => {
    if (!selectedBot) return;
    setProviderSel(selectedBot.provider || "auto");
    setModelSel(selectedBot.model || "");
    setNotes(selectedBot.notes || "");
    setKeyStatus("");
    setEffortSel(selectedBot.reasoning_effort || "");
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedId]);

  useEffect(() => {
    rowsEndRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [rows, busy]);

  useEffect(() => {
    refreshView(view);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [view]);

  /* ---- surfaces: trust gate + shared prompts */
  function guardedSelectProject(id: string) {
    const target = projects.find((p) => p.id === id);
    if (target && Number(target.trusted ?? 0) === 0) {
      setTrustTarget(target);
      setPendingProjectId(id);
      return;
    }
    void selectProject(id);
  }

  async function trustWorkspace() {
    const id = pendingProjectId;
    if (!id) { setTrustTarget(null); return; }
    try {
      const body = await api(`projects/${id}/trust`, {
        method: "POST",
        body: JSON.stringify({ trusted: true }),
      });
      setProjects((prev) => prev.map((p) => (p.id === id ? { ...p, trusted: 1 } : p)));
      setTrustTarget(null);
      setPendingProjectId(null);
      await selectProject(id);
      say("Workspace trusted — Keel can work in this folder now.");
    } catch (err: any) {
      say(`Trust failed: ${err.message}`);
      setTrustTarget(null);
      setPendingProjectId(null);
    }
  }

  async function revokeTrust(id: string) {
    try {
      const body = await api(`projects/${id}/trust`, {
        method: "POST",
        body: JSON.stringify({ trusted: false }),
      });
      setProjects((prev) => prev.map((p) => (p.id === id ? { ...p, trusted: 0 } : p)));
      if (activeProjectId === id) {
        setActiveProjectId(null);
        setTreeEntries([]);
        say("Trust revoked. The folder stays on disk; Duet/Code can't touch it until trusted again.");
      } else {
        say("Trust revoked.");
      }
    } catch (err: any) { say(`Revoke failed: ${err.message}`); }
  }

  const PROMPT_DAILY = "Give me my daily briefing: what my agents did recently, what's due, and what needs my attention. Be concise.";
  const PROMPT_ATTENTION = "What needs my attention right now, based on my fleet, tasks, and projects? Be brief and concrete.";
  const PROMPT_FLEET_SUMMARY = "Summarize what my agents did recently and suggest the next three things to do.";

  function firstAgentId(): string | null {
    return selectedId ?? bots[0]?.id ?? null;
  }
  async function runPrompt(prompt: string) {
    const botId = firstAgentId();
    if (!botId) { say("Create an agent first — Keel works through agents."); return; }
    if (!selectedId) setSelectedId(botId);
    setDraft("");
    await sendMessageRaw(prompt, mode);
  }

  /* ---- routines (F4) — used by Fleet and the Cowork Scheduled page */
  async function refreshRoutines() {
    try {
      const body = await api("routines");
      setRoutines(body.routines ?? []);
    } catch (err: any) { console.error("routines load failed", err); }
  }
  async function routineAction(id: string, action: "run" | "pause" | "resume" | "enable" | "disable" | "delete") {
    try {
      await api(`routines/${id}/${action}`, {
        method: "POST",
        body: JSON.stringify(action === "pause" ? { reason: "paused from Keel" } : {}),
      });
      await refreshRoutines();
      if (action === "run") say("Run queued — watch the routine's history.");
    } catch (err: any) { say(`Routine action failed: ${err.message}`); }
  }
  const ROUTINE_TEMPLATES: { name: string; cron: string; prompt: string }[] = [
    { name: "Daily briefing", cron: "0 8 * * *", prompt: PROMPT_DAILY },
    { name: "Inbox triage", cron: "0 9 * * 1-5", prompt: "Scan my open tasks and prioritize them for today, grouped by urgency." },
    { name: "Meeting prep", cron: "30 7 * * 1-5", prompt: "Prepare talking points for today's meetings based on open tasks and library files." },
    { name: "Weekly review", cron: "0 17 * * 5", prompt: "Weekly review: completed tasks, library files created, and a suggested focus for next week." },
    { name: "Content ideas", cron: "0 10 * * 1", prompt: "Suggest five content ideas based on my project files and recent agent work." },
    { name: "Monitor a topic", cron: "0 12 * * *", prompt: "What changed in my projects since yesterday? Flag errors and stale tasks." },
  ];
  async function createRoutineFromTemplate(t: { name: string; cron: string; prompt: string }) {
    const botId = firstAgentId();
    if (!botId) { say("Create an agent first — scheduled tasks run on an agent."); return; }
    try {
      await api("routines", {
        method: "POST",
        body: JSON.stringify({
          name: t.name, prompt: t.prompt, cron_expr: t.cron,
          timezone: Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC",
          bot_id: botId, enabled: true,
        }),
      });
      await refreshRoutines();
      say(`Scheduled “${t.name}” — runs on ${bots.find((b) => b.id === botId)?.name ?? "your agent"}.`);
    } catch (err: any) { say(`Couldn't schedule: ${err.message}`); }
  }

  /* ---- artifacts — Keel's library, all agents */
  async function refreshArtifacts() {
    try {
      const body = await api("library");
      setArtifacts(body.files ?? []);
    } catch (err: any) { console.error("artifacts load failed", err); }
  }

  /* ---- customize — skills + connectors from the bridge */
  async function loadSkills() {
    try {
      const body = await api("skills");
      setSkills(body.skills ?? []);
    } catch (err: any) { setSkills([]); say(`Skills unavailable: ${err.message}`); }
  }
  async function loadConnectors() {
    try {
      const body = await api("connectors");
      setConnectors(body.connectors ?? []);
    } catch (err: any) { setConnectors([]); say(`Connectors unavailable: ${err.message}`); }
  }

  /* ---- keep awake (Windows only; real SetThreadExecutionState process) */
  async function loadKeepAwake() {
    try { setKeepAwake(await api("keep-awake")); }
    catch { setKeepAwake({ supported: false, on: false }); }
  }
  async function toggleKeepAwake() {
    if (!keepAwake) return;
    try {
      const body = await api("keep-awake", {
        method: "POST",
        body: JSON.stringify({ on: !keepAwake.on }),
      });
      setKeepAwake({ supported: keepAwake.supported, on: !!body?.on });
      if (body?.error) say(String(body.error));
      else say(body?.on ? "Keep awake on — this machine won't sleep while Keel runs." : "Keep awake off.");
    } catch (err: any) { say(`Keep awake failed: ${err.message}`); }
  }

  const currentContextWindow: number | null = (() => {
    const meta = (modelsMeta as any[]).find((m) => m.id === currentModel);
    return meta && typeof meta.context_length === "number" ? meta.context_length : null;
  })();

  /* ---- surface persistence + duet defaults */
  useEffect(() => {
    try { window.localStorage.setItem("keel-surface", surface); } catch { /* ignore */ }
    if (surface === "duet" || surface === "code" || surface === "cowork") {
      if (!selectedIdRef.current && bots.length > 0) setSelectedId(bots[0].id);
    }
    if (surface === "duet" && activeProjectId) void loadReview();
    if (surface === "cowork" && cowView === "scheduled") void loadKeepAwake();
    if (surface === "cowork" && (cowView === "projects" || cowView === "artifacts")) {
      void loadProjects();
      void refreshArtifacts();
    }
    if (surface === "cowork" && cowView === "customize" && (skills === null || connectors === null)) {
      void loadSkills();
      void loadConnectors();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [surface, cowView]);

  /* ---- apply the saved default project once it's in the registry */
  const didApplyDefault = useRef(false);
  useEffect(() => {
    if (didApplyDefault.current || !defaultProjectId || activeProjectId) return;
    const target = projects.find((p) => p.id === defaultProjectId);
    if (target && Number(target.trusted ?? 0) === 1) {
      didApplyDefault.current = true;
      void selectProject(target.id);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projects]);

  /* ---- terminal auto-scroll */
  useEffect(() => {
    if (termLinesRef.current) {
      termLinesRef.current.scrollTop = termLinesRef.current.scrollHeight;
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [termLines]);

  /* ---- catalog metadata (models + effort support) */
  async function loadCatalogMeta(name: string | null) {
    const candidates = !name || name === "auto"
      ? ["openrouter", "google", "nvidia", "openai-compatible"]
      : [name];
    for (const c of candidates) {
      try {
        const body = await api("providers/catalog", {
          method: "POST",
          body: JSON.stringify({ name: c }),
        });
        if (body?.ok && Array.isArray(body.models_meta)) {
          setModelsMeta(body.models_meta);
          return;
        }
      } catch { /* try the next candidate */ }
    }
    setModelsMeta([]);
  }

  useEffect(() => {
    void loadCatalogMeta(selectedBot?.provider ?? null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedId]);

  /* ---- Duet: projects + files + terminal + review */
  async function loadProjects() {
    try {
      const body = await api("projects");
      setProjects(body.projects ?? []);
      return body.projects ?? [];
    } catch (err: any) {
      console.error("projects load failed", err);
      return [];
    }
  }

  async function addProject() {
    const path = projectPathInput.trim().replace(/^"|"$/g, "");
    if (!path || projectAdding) return;
    setProjectAdding(true);
    try {
      const body = await api("projects", {
        method: "POST",
        body: JSON.stringify({ path }),
      });
      const proj = body?.project;
      setProjectPathInput("");
      await loadProjects();
      if (proj?.id) guardedSelectProject(proj.id);
      say(`Project added: ${proj?.name ?? path}`);
    } catch (err: any) {
      say(`Couldn't add project: ${err.message}`);
    } finally {
      setProjectAdding(false);
    }
  }

  async function removeProject(id: string) {
    try {
      await api(`projects/${id}/remove`, { method: "POST", body: "{}" });
      setProjects((prev) => prev.filter((p) => p.id !== id));
      if (activeProjectId === id) {
        setActiveProjectId(null);
        setTreeEntries([]);
      }
      say("Project removed from Duet — files on disk are untouched.");
    } catch (err: any) {
      say(`Remove failed: ${err.message}`);
    }
  }

  async function selectProject(id: string) {
    setActiveProjectId(id);
    setFileCache({});
    setExpandedDirs({ "": true });
    try {
      await api(`projects/${id}/open`, { method: "POST", body: "{}" });
    } catch { /* opening is a nicety, never blocks */ }
    setTreeLoading(true);
    try {
      const body = await api(`projects/${id}/tree`);
      setTreeEntries(body.entries ?? []);
    } catch (err: any) {
      say(`Couldn't read the tree: ${err.message}`);
    } finally {
      setTreeLoading(false);
    }
    void loadProjects();
    void loadReview(id);
  }

  const activeProject = projects.find((p) => p.id === activeProjectId) ?? null;

  function buildTree(entries: TreeEntry[]): TreeNode[] {
    const root: TreeNode = { name: "", path: "", isDir: true, children: [] };
    const dirMap = new Map<string, TreeNode>();
    dirMap.set("", root);
    const ensureDir = (rel: string): TreeNode => {
      const existing = dirMap.get(rel);
      if (existing) return existing;
      const parts = rel.split("/").filter(Boolean);
      let curPath = "";
      let cur = root;
      for (const part of parts) {
        curPath = curPath ? `${curPath}/${part}` : part;
        let next = dirMap.get(curPath);
        if (!next) {
          next = { name: part, path: curPath, isDir: true, children: [] };
          dirMap.set(curPath, next);
          cur.children.push(next);
        }
        cur = next;
      }
      return cur;
    };
    for (const entry of entries) {
      const parent = ensureDir(entry.dir);
      parent.children.push({
        name: entry.name,
        path: entry.path,
        isDir: false,
        size: entry.size,
        children: [],
      });
    }
    const sortTree = (node: TreeNode) => {
      node.children.sort((a, b) => {
        if (a.isDir !== b.isDir) return a.isDir ? -1 : 1;
        return a.name.localeCompare(b.name);
      });
      node.children.forEach(sortTree);
    };
    sortTree(root);
    return root.children;
  }

  async function openFileTab(path: string) {
    const pid = activeProjectId;
    if (!pid) return;
    const id = `file:${path}`;
    setDuetTabs((prev) => prev.some((t) => t.id === id) ? prev : [...prev, { id, kind: "file", path }]);
    setActiveDuetTab(id);
    if (fileCache[path]) return;
    setFileLoading(true);
    try {
      const body = await api(`projects/${pid}/file/read?path=${encodeURIComponent(path)}`);
      setFileCache((prev) => ({
        ...prev,
        [path]: {
          path,
          name: body.name ?? path.split("/").pop() ?? path,
          content: body.binary ? "" : String(body.content ?? ""),
          base64: body.binary ? String(body.content ?? "") : "",
          binary: !!body.binary,
          mime: body.mime ?? "text/plain; charset=utf-8",
          size: body.size ?? 0,
          truncated: !!body.truncated,
          dirty: false,
        },
      }));
    } catch (err: any) {
      say(`Couldn't open ${path}: ${err.message}`);
    } finally {
      setFileLoading(false);
    }
  }

  async function saveFile(path: string) {
    const pid = activeProjectId;
    const cached = fileCache[path];
    if (!pid || !cached || cached.binary) return;
    try {
      await api(`projects/${pid}/file/write`, {
        method: "POST",
        body: JSON.stringify({ path, content: cached.content }),
      });
      setFileCache((prev) => ({ ...prev, [path]: { ...prev[path], dirty: false } }));
      say(`Saved ${path}`);
    } catch (err: any) {
      say(`Save failed: ${err.message}`);
    }
  }

  function closeDuetTab(id: string) {
    setDuetTabs((prev) => {
      const remaining = prev.filter((t) => t.id !== id);
      if (activeDuetTab === id) {
        setActiveDuetTab(remaining.length ? remaining[remaining.length - 1].id : "openfile");
      }
      return remaining;
    });
    setTabAddOpen(false);
  }

  function addDuetTab(kind: DuetTabKind) {
    if (kind !== "file") {
      setDuetTabs((prev) => prev.some((t) => t.kind === kind) ? prev : [...prev, { id: kind, kind }]);
      setActiveDuetTab(kind);
    }
    setTabAddOpen(false);
    if (kind === "review") void loadReview();
  }

  async function loadReview(pidOverride?: string) {
    const pid = pidOverride ?? activeProjectId;
    if (!pid) { setReviewData(null); return; }
    setReviewLoading(true);
    try {
      const body = await api(`projects/${pid}/review`);
      setReviewData(body);
    } catch (err: any) {
      setReviewData({ error: err.message });
    } finally {
      setReviewLoading(false);
    }
  }

  async function runTerminalCommand(cmdOverride?: string) {
    const pid = activeProjectId;
    const command = (cmdOverride ?? termInput).trim();
    if (!pid) { say("Add a project first — the terminal needs a working directory."); return; }
    if (!command || termBusy) return;
    setTermInput("");
    setTermHistory((prev) => [...prev.slice(-49), command]);
    setTermHistIdx(-1);
    setTermBusy(true);
    setTermLines((prev) => [...prev, `$ ${command}`]);
    termOutRef.current = 0;
    termHandleRef.current = null;
    try {
      const body = await api(`projects/${pid}/terminal/exec`, {
        method: "POST",
        body: JSON.stringify({ command, shell: termShell }),
      });
      const handle = body?.handle;
      if (!handle) {
        setTermLines((prev) => [...prev, `error: ${body?.error ?? "no handle returned"}`]);
        setTermBusy(false);
        return;
      }
      termHandleRef.current = handle;
      for (let i = 0; i < 240; i++) {
        await new Promise((r) => setTimeout(r, 600));
        try {
          const out = await api(`shells/${handle}/output`);
          const text: string = String(out?.output ?? "");
          const fresh = text.slice(termOutRef.current);
          if (fresh) {
            termOutRef.current = text.length;
            setTermLines((prev) => [...prev, ...fresh.split("\n")]);
          }
          if (!out?.running) {
            setTermLines((prev) => [...prev, `(exit ${out?.exit_code ?? "?"})`]);
            setTermBusy(false);
            return;
          }
        } catch (err: any) {
          setTermLines((prev) => [...prev, `error reading output: ${err.message}`]);
          setTermBusy(false);
          return;
        }
      }
      setTermLines((prev) => [...prev, "(still running after 2 minutes — the process continues; output so far is shown)"]);
      setTermBusy(false);
    } catch (err: any) {
      setTermLines((prev) => [...prev, `error: ${err.message}`]);
      setTermBusy(false);
    }
  }

  async function attachFiles(files: FileList | null) {
    if (!files || files.length === 0) return;
    const parts: string[] = [];
    let attached = 0;
    for (const file of Array.from(files)) {
      try {
        const head = `--- attached file: ${file.name} (${fmtBytes(file.size)}) ---`;
        if (isTextLike(file.name, file.type, file.size) && file.size <= 1_000_000) {
          const text = await file.text();
          parts.push(`\n\n${head}\n\`\`\`\n${text}\n\`\`\``);
          attached += 1;
        } else if (file.size <= 300_000) {
          const buf = await file.arrayBuffer();
          let binary = "";
          const bytes = new Uint8Array(buf);
          for (let i = 0; i < bytes.length; i += 8192) {
            binary += String.fromCharCode(...bytes.subarray(i, i + 8192));
          }
          parts.push(`\n\n${head}\n[binary content, base64]\n${btoa(binary)}`);
          attached += 1;
        } else {
          parts.push(`\n\n${head}\n[${file.type || "binary"} — too large to inline (${fmtBytes(file.size)}); only its name and size are sent]`);
          attached += 1;
        }
      } catch {
        parts.push(`\n\n--- attached file: ${file.name} ---\n[unreadable]`);
        attached += 1;
      }
    }
    setDraft((d) => (d ? `${d}${parts.join("")}` : `Attached ${attached} file${attached === 1 ? "" : "s"}:${parts.join("")}`));
    say(`${attached} file${attached === 1 ? "" : "s"} attached — text is sent in full, small binaries as base64, anything else by name+size.`);
    if (attachRef.current) attachRef.current.value = "";
  }

  /* ---- slash commands */
  const slashQuery = draft.startsWith("/") ? draft.slice(1) : null;
  const slashHead = slashQuery !== null ? slashQuery.split(" ")[0].toLowerCase() : "";
  const slashArgs = slashQuery !== null && slashQuery.includes(" ")
    ? slashQuery.slice(slashQuery.indexOf(" ") + 1).trim()
    : "";
  const slashMatches = slashQuery !== null && !slashQuery.includes(" ")
    ? SLASH_COMMANDS.filter((c) => slashHead === "" || c.name.startsWith(slashHead) || c.aliases.some((a) => a.startsWith(slashHead)))
    : [];
  const slashOpen = slashMatches.length > 0 && !slashDismissed;

  async function loadUsageData() {
    try {
      const body = await api("usage");
      setUsageData(body.usage ?? null);
    } catch { /* bridge down — panel shows placeholders */ }
  }
  async function loadUsage() {
    await loadUsageData();
    setUsageOpen(true);
  }

  function runSlash(name: string, args: string) {
    const finish = () => { setDraft(""); setSlashDismissed(false); setSlashIdx(0); };
    switch (name) {
      case "context": case "cost": case "usage":
        void loadUsage(); finish(); return true;
      case "help": case "?":
        setHelpOpen(true); finish(); return true;
      case "review": case "diff":
        setSurface("duet");
        addDuetTab("review");
        finish(); return true;
      case "model": {
        if (args) { changeModel(args); finish(); return true; }
        say(`Current model: ${currentModel || "none"} — usage: /model <name>`);
        finish(); return true;
      }
      case "shell": case "sh":
        if (!args) { say("Usage: /shell <command>"); setDraft("/shell "); return true; }
        setSurface("duet");
        addDuetTab("terminal");
        void runTerminalCommand(args);
        finish(); return true;
      case "open": {
        if (!args) { say("Usage: /open <path>  (path relative to the project root)"); setDraft("/open "); return true; }
        setSurface("duet");
        void openFileTab(args);
        finish(); return true;
      }
      default:
        return false;
    }
  }

  function handleSlashKeyDown(e: React.KeyboardEvent<HTMLInputElement>): boolean {
    if (!slashOpen) return false;
    if (e.key === "ArrowDown") { e.preventDefault(); setSlashIdx((i) => (i + 1) % slashMatches.length); return true; }
    if (e.key === "ArrowUp") { e.preventDefault(); setSlashIdx((i) => (i - 1 + slashMatches.length) % slashMatches.length); return true; }
    if (e.key === "Escape") { e.preventDefault(); setSlashDismissed(true); return true; }
    if (e.key === "Enter" || e.key === "Tab") {
      e.preventDefault();
      const cmd = slashMatches[Math.min(slashIdx, slashMatches.length - 1)];
      if (cmd) runSlash(cmd.name, slashArgs);
      return true;
    }
    return false;
  }

  const currentModel = selectedBot?.model || "";
  const modelMeta = modelsMeta.find((m) => m.id === currentModel) || null;
  const effortChoices: string[] = modelMeta?.reasoning?.supported_efforts ?? [];
  const modelChoices: string[] = (() => {
    const ids = modelsMeta.map((m) => m.id);
    if (currentModel && !ids.includes(currentModel)) return [currentModel, ...ids];
    if (ids.length === 0 && currentModel) return [currentModel];
    return ids;
  })();

  function pickMode(m: ModeSetting) {
    setMode(m);
    try { window.localStorage.setItem("keel-mode", m); } catch { /* ignore */ }
  }

  async function changeModel(model: string) {
    if (!selectedBot || model === selectedBot.model) return;
    setEffortSel("");
    try {
      const body = await api(`bots/${selectedBot.id}/update`, {
        method: "POST",
        body: JSON.stringify({ model }),
      });
      setBots((prev) => prev.map((b) => (b.id === selectedBot.id ? { ...b, ...body.bot } : b)));
    } catch (err: any) { say(`Model switch failed: ${err.message}`); }
  }

  async function changeEffort(effort: string) {
    if (!selectedBot) return;
    setEffortSel(effort);
    try {
      const body = await api(`bots/${selectedBot.id}/update`, {
        method: "POST",
        body: JSON.stringify({ reasoning_effort: effort }),
      });
      setBots((prev) => prev.map((b) => (b.id === selectedBot.id ? { ...b, ...body.bot } : b)));
    } catch (err: any) { say(`Effort save failed: ${err.message}`); }
  }

  /* ---- clear finished shells (pill hygiene) */
  async function clearFinishedShells() {
    try {
      const body = await api("shells/clear/finished");
      say(body?.cleared ? `Cleared ${body.cleared} finished shell${body.cleared === 1 ? "" : "s"}.` : "Nothing finished to clear.");
      const fresh = await api("shells");
      setShells(Array.isArray(fresh?.shells) ? fresh.shells : []);
    } catch (err: any) {
      say(`Clear failed: ${err.message}`);
    }
  }

  /* ---- pool background shells every few seconds */
  useEffect(() => {
    let stop = false;
    const tick = async () => {
      while (!stop) {
        try {
          const body = await api("shells");
          if (!stop) setShells(Array.isArray(body?.shells) ? body.shells : []);
        } catch { /* bridge down — keep polling quietly */ }
        await new Promise((r) => setTimeout(r, 2500));
      }
    };
    void tick();
    return () => { stop = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  /* ---- Ctrl+B toggles the background shells panel */
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.ctrlKey && (e.key === "b" || e.key === "B")) {
        e.preventDefault();
        setShellsPanel((v) => !v);
      }
      if (e.key === "Escape") setShellsPanel(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  /* ---- actions */
  async function sendMessageRaw(text: string, modeArg: ModeSetting) {
    const id = selectedIdRef.current;
    if (!id) return;
    setStreamText("");
    setBusy(true);
    try {
      await api(`bots/${id}/messages`, {
        method: "POST",
        body: JSON.stringify({ content: text, mode: modeArg }),
      });
      await loadRows(id);
    } catch (err: any) {
      say(`Message failed: ${err.message}`);
      setBusy(false);
    }
  }

  /* ---- slash intercept: ANY draft starting with / is a command, never a prompt */
  function trySlashCommand(text: string): boolean {
    if (!text.startsWith("/") || text.length < 2) return false;
    const body = text.slice(1);
    const sp = body.indexOf(" ");
    const head = (sp === -1 ? body : body.slice(0, sp)).toLowerCase();
    const args = sp === -1 ? "" : body.slice(sp + 1).trim();
    if (head === "") return false;
    const cmd = SLASH_COMMANDS.find((c) => c.name === head || c.aliases.includes(head));
    if (!cmd) {
      say(`Unknown command “/${head}” — type /help`);
      return true; // do NOT send it to the model
    }
    runSlash(cmd.name, args);
    return true;
  }

  async function sendMessage() {
    const text = draft.trim();
    if (!text || !selectedId || busy) return;
    setDraft("");
    if (trySlashCommand(text)) return;
    await sendMessageRaw(text, mode);
  }

  const queueRef = useRef(queue);
  useEffect(() => { queueRef.current = queue; }, [queue]);

  async function flushQueue() {
    const next = queueRef.current[0];
    if (!next) return;
    setQueue((q) => q.slice(1));
    if (trySlashCommand(next.content.trim())) return; // queued slash commands run locally
    await sendMessageRaw(next.content, next.mode);
  }

  function enqueueDraft() {
    const text = draft.trim();
    if (!text) return;
    setQueue((q) => [...q, { id: queueId.current++, content: text, mode }]);
    setDraft("");
    say("Queued — sends when the current turn ends.");
  }

  async function stopTurn() {
    if (!selectedId) return;
    try {
      await api(`bots/${selectedId}/cancel`, { method: "POST", body: "{}" });
      say("Stop requested — the turn ends at the next model boundary.");
    } catch (err: any) {
      say(`Stop failed: ${err.message}`);
    }
  }

  function useQuickStart(prompt: string) {
    setView("agents");
    if (!selectedId && bots[0]) setSelectedId(bots[0].id);
    setDraft(prompt);
    window.setTimeout(() => composerRef.current?.focus(), 80);
  }

  async function createAgent() {
    const name = newName.trim();
    if (!name) {
      setNameError("Give it a name first — even " + '"Scout"' + " works.");
      return;
    }
    setNameError("");
    try {
      const body = await api("bots", {
        method: "POST",
        body: JSON.stringify({ name, role: newRole.trim(), engine: newEngine, avatar_hue: newHue }),
      });
      setModalOpen(false);
      setNewName("");
      setNewRole("");
      setNewEngine("provider");
      setNewHue(Math.floor(Math.random() * 360));
      await refreshBots();
      if (body?.bot?.id) setSelectedId(body.bot.id);
      say(`${name} joined the fleet.`);
    } catch (err: any) {
      say(`Couldn't create agent: ${err.message}`);
    }
  }

  async function saveEngine() {
    if (!selectedBot) return;
    try {
      const body = await api(`bots/${selectedBot.id}/update`, {
        method: "POST",
        body: JSON.stringify({ provider: providerSel, model: modelSel }),
      });
      setBots((prev) => prev.map((b) => (b.id === selectedBot.id ? { ...b, ...body.bot } : b)));
      say("Engine saved.");
    } catch (err: any) { say(`Engine save failed: ${err.message}`); }
  }

  async function saveNotes() {
    if (!selectedBot) return;
    try {
      const body = await api(`bots/${selectedBot.id}/update`, {
        method: "POST",
        body: JSON.stringify({ notes }),
      });
      setBots((prev) => prev.map((b) => (b.id === selectedBot.id ? { ...b, ...body.bot } : b)));
      say("Notes saved.");
    } catch (err: any) { say(`Notes save failed: ${err.message}`); }
  }

  async function validateKey() {
    if (providerSel === "auto") {
      setKeyStatus("Pick the specific provider first (not auto), then validate.");
      return;
    }
    const key = keyInput.trim();
    setKeyBusy(true);
    try {
      if (key) {
        const body = await api("providers/credential", {
          method: "POST",
          body: JSON.stringify({ name: providerSel, key }),
        });
        setKeyInput("");
        if (!body.ok) {
          setKeyStatus(`Key not accepted — ${body.detail ?? body.error}`);
          return;
        }
        setModelList(body.models ?? []);
        setKeyStatus(`Key accepted — ${body.model_count} models loaded (this session only).`);
      } else {
        const body = await api("providers/catalog", {
          method: "POST",
          body: JSON.stringify({ name: providerSel }),
        });
        if (!body.ok) {
          setKeyStatus(`Models unavailable — ${body.detail ?? body.error}`);
          return;
        }
        setModelList(body.models ?? []);
        setKeyStatus(`${body.model_count} models loaded from key (${body.key_source}).`);
      }
      await loadProviders();
    } catch (err: any) {
      setKeyInput("");
      setKeyStatus(`Validation failed — ${err.message}`);
    } finally {
      setKeyBusy(false);
    }
  }

  async function forgetKey() {
    setKeyBusy(true);
    try {
      const body = await api("providers/credential/clear", {
        method: "POST",
        body: JSON.stringify({ name: providerSel }),
      });
      setKeyStatus(body.ok ? `Session key for ${providerSel} forgotten.` : body.detail ?? "No session key to clear.");
      setModelList([]);
      await loadProviders();
    } catch (err: any) {
      setKeyStatus(err.message);
    } finally {
      setKeyBusy(false);
    }
  }

  async function decideApproval(row: Row, decision: "once" | "deny" | "always") {
    if (!selectedId) return;
    const seq = row.seq;
    setDecidedApprovals((prev) => ({ ...prev, [seq]: decision }));
    try {
      await api(`bots/${selectedId}/approvals/${row.body.approval_id}/decide`, {
        method: "POST",
        body: JSON.stringify({ decision }),
      });
      await loadRows(selectedId);
    } catch (err: any) {
      setDecidedApprovals((prev) => {
        const next = { ...prev };
        delete next[seq];
        return next;
      });
      say(`Approval failed: ${err.message}`);
    }
  }

  async function runRoutine(id: string) {
    try {
      await api(`routines/${id}/run`, { method: "POST", body: "{}" });
      say("Routine run requested.");
    } catch (err: any) { say(`Run failed: ${err.message}`); }
  }

  async function addTask() {
    const title = newTask.trim();
    if (!title) return;
    try {
      const body = await api("tasks", {
        method: "POST",
        body: JSON.stringify({ title }),
      });
      setNewTask("");
      refreshTasks();
    } catch (err: any) { say(`Task failed: ${err.message}`); }
  }

  /* ---- task reorder / undo / edit / delete */
  async function toggleTaskDone(t: TaskItem) {
    const next = t.status === "completed" ? "pending" : "completed";
    setTasks((prev) => prev.map((x) => (x.id === t.id ? { ...x, status: next } : x)));
    try {
      await api(`tasks/${t.id}/update`, {
        method: "POST",
        body: JSON.stringify({ status: next }),
      });
    } catch (err: any) { say(`Task update failed: ${err.message}`); }
  }

  async function saveTaskTitle(t: TaskItem) {
    const title = editTitle.trim();
    setEditingTaskId(null);
    if (!title || title === t.title) return;
    setTasks((prev) => prev.map((x) => (x.id === t.id ? { ...x, title } : x)));
    try {
      await api(`tasks/${t.id}/update`, {
        method: "POST",
        body: JSON.stringify({ title }),
      });
    } catch (err: any) { say(`Rename failed: ${err.message}`); }
  }

  async function revertTask(t: TaskItem) {
    try {
      const body = await api(`tasks/${t.id}/undo`, { method: "POST", body: "{}" });
      setTasks((prev) => prev.map((x) => (x.id === t.id ? { ...x, ...body.task } : x)));
      say("Reverted to previous state.");
    } catch (err: any) {
      say(err.message?.includes("nothing") ? "Nothing to undo." : `Revert failed: ${err.message}`);
    }
  }

  async function undoDeletedTask(id: string) {
    try {
      const body = await api(`tasks/${id}/undo`, { method: "POST", body: "{}" });
      setTasks((prev) => [...prev, body.task]);
      say("Task restored.");
    } catch (err: any) { say(`Undo failed: ${err.message}`); }
  }

  async function deleteTask(t: TaskItem) {
    try {
      await api(`tasks/${t.id}/delete`, { method: "POST", body: "{}" });
      setTasks((prev) => prev.filter((x) => x.id !== t.id));
      sayAction("Task deleted.", "Undo", () => undoDeletedTask(t.id));
    } catch (err: any) { say(`Delete failed: ${err.message}`); }
  }

  async function reorderTasks(ordered: TaskItem[]) {
    try {
      const body = await api("tasks/reorder", {
        method: "POST",
        body: JSON.stringify({ ids: ordered.map((t) => t.id) }),
      });
      setTasks(body.tasks ?? ordered);
    } catch (err: any) {
      say(`Reorder failed: ${err.message}`);
      refreshTasks();
    }
  }

  async function moveTask(t: TaskItem, dir: -1 | 1) {
    const idx = tasks.findIndex((x) => x.id === t.id);
    const j = idx + dir;
    if (idx < 0 || j < 0 || j >= tasks.length) return;
    const next = [...tasks];
    [next[idx], next[j]] = [next[j], next[idx]];
    setTasks(next);
    await reorderTasks(next);
  }

  function onTaskDragStart(id: string) {
    setDragId(id);
  }
  function onTaskDragOver(e: React.DragEvent, id: string) {
    e.preventDefault();
    const rect = (e.currentTarget as HTMLElement).getBoundingClientRect();
    const before = e.clientY < rect.top + rect.height / 2;
    setDropTarget({ id, before });
  }
  function onTaskDrop(id: string) {
    const from = tasks.findIndex((t) => t.id === dragId);
    if (dragId == null || dragId === id || from < 0) {
      setDragId(null);
      setDropTarget(null);
      return;
    }
    const moving = tasks[from];
    const rest = tasks.filter((t) => t.id !== dragId);
    let insertAt = rest.findIndex((t) => t.id === id);
    if (dropTarget && !dropTarget.before) insertAt += 1;
    const next = [...rest.slice(0, insertAt), moving, ...rest.slice(insertAt)];
    setTasks(next);
    setDragId(null);
    setDropTarget(null);
    void reorderTasks(next);
  }

  /* ---- row rendering */
  const TOOL_LABEL: Record<string, string> = {
    read_file: "Read", write_file: "Write", edit_file: "Edit",
    run_shell: "Shell", glob: "Glob", grep: "Grep",
    list_tasks: "List tasks", create_task: "Create task", update_task: "Update task",
    save_file: "Save file", send_to_bot: "Delegate", ask_user: "Ask",
  };
  const toolLabel = (name: string) => TOOL_LABEL[name] ?? name;
  function toolIcon(name: string) {
    const p = { width: 13, height: 13, viewBox: "0 0 24 24", fill: "none", stroke: "currentColor", strokeWidth: 1.8, strokeLinecap: "round" as const, strokeLinejoin: "round" as const };
    switch (name) {
      case "read_file": return <svg {...p}><path d="M7 3h8l5 5v13H7z" /><path d="M15 3v5h5M10.5 13h5M10.5 16.5h5" /></svg>;
      case "write_file":
      case "edit_file": return <svg {...p}><path d="M12 20h9" /><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L9 17l-4 1 1-4 10.5-10.5z" /></svg>;
      case "run_shell": return <svg {...p}><path d="M4 17l6-6-6-6" /><path d="M12 19h8" /></svg>;
      case "glob": return <svg {...p}><circle cx="10.5" cy="10.5" r="6.5" /><path d="M15.5 15.5L21 21" /><path d="M7.5 10.5h6" /></svg>;
      case "grep": return <svg {...p}><circle cx="11" cy="11" r="7" /><path d="M21 21l-4.3-4.3M11 8v6M8 11h6" /></svg>;
      case "list_tasks": return <svg {...p}><path d="M4 6h16M4 12h16M4 18h10" /></svg>;
      case "send_to_bot": return <svg {...p}><path d="M5 12h14M13 6l6 6-6 6" /></svg>;
      case "ask_user": return <svg {...p}><circle cx="12" cy="12" r="9" /><path d="M9.5 9.5a2.5 2.5 0 0 1 4.9.8c0 1.6-2.2 2-2.2 3.4M12 17h.01" /></svg>;
      default: return <svg {...p}><path d="M9 8l-4 4 4 4M15 8l4 4-4 4" /></svg>;
    }
  }

  function renderRows() {
    const out: React.ReactNode[] = [];
    let stepBuf: Row[] = [];
    const flushStepGroup = (key: string) => {
      if (stepBuf.length === 0) return;
      const buf = stepBuf;
      stepBuf = [];
      const counts: Record<string, number> = {};
      for (const r of buf) counts[toolLabel(r.body?.name ?? "tool")] = (counts[toolLabel(r.body?.name ?? "tool")] ?? 0) + 1;
      const summary = Object.entries(counts).map(([n, c]) => `${c} ${n}`).join(", ");
      const first = buf[0].seq;
      const last = buf[buf.length - 1].seq;
      out.push(
        <div className="step-group" key={`grp-${key}`}>
          {buf.map((r) => {
            const b = r.body ?? {};
            const st = b.status === "done" ? "step-done" : b.status === "error" ? "step-error" : "step-running";
            const label = toolLabel(b.name ?? "tool");
            return (
              <div className={`step-line ${st}`} key={r.seq}>
                <span className="step-icon">{toolIcon(b.name ?? "")}</span>
                <span><span className="tool-name">{label}</span><span className="tool-line-break">—</span><span className="tool-detail">{b.detail}</span></span>
                <span className="step-state">{b.status === "done" ? "✓" : b.status === "error" ? "✕" : "…"}</span>
              </div>
            );
          })}
          {buf.length > 1 && <div className="steps-meta">Used {summary}</div>}
        </div>,
      );
      void first; void last;
    };

    for (const row of rows) {
      if (row.kind === "step") { stepBuf.push(row); continue; }
      flushStepGroup(String(row.seq));
      const b = row.body ?? {};
      if (row.kind === "notice") {
        out.push(<div key={row.seq} className={`notice${b.level === "warning" ? " warn" : ""}`}>{b.text}</div>);
      } else if (row.kind === "message") {
        const role = b.role === "user" ? "user" : "assistant";
        out.push(
          <div key={row.seq} className={`bubble ${role}`}>
            <span className="msg-actions" aria-label="message actions">
              <button className="act-copy" title="Copy message" aria-label="Copy message" onClick={() => copyMessage(row)}>
                <svg viewBox="0 0 24 24"><rect x="9" y="9" width="11" height="11" rx="2" /><path d="M5 15V5a2 2 0 0 1 2-2h10" /></svg>
              </button>
              <button className="act-fork" title="Fork from here" aria-label="Fork from here" onClick={() => forkFromHere(row)}>
                <svg viewBox="0 0 24 24"><circle cx="6" cy="6" r="2.4" /><circle cx="18" cy="6" r="2.4" /><circle cx="6" cy="18" r="2.4" /><circle cx="18" cy="18" r="2.4" /><path d="M6 8.4v7.2" /><path d="M18 8.4v7.2" /><path d="M6 12h12" /></svg>
              </button>
              <button className="act-undo" title="Undo — rewind to before this" aria-label="Undo message" onClick={() => rewindFromHere(row)}>
                <svg viewBox="0 0 24 24"><path d="M9 14L4 9l5-5" /><path d="M4 9h11a5 5 0 0 1 0 10h-3" /></svg>
              </button>
            </span>
            <span className="role">{role === "user" ? "you" : selectedBot?.name ?? "agent"}</span>
            {b.content}
          </div>,
        );
      } else if (row.kind === "turn_end") {
        out.push(
          <div key={row.seq} className="turn-meta">
            turn ended{b.duration_ms ? ` · ${(b.duration_ms / 1000).toFixed(1)}s` : ""}{b.terminal_reason ? ` · ${b.terminal_reason}` : ""}
          </div>,
        );
      } else if (row.kind === "ask") {
        out.push(<AskCard key={row.seq} row={row} onAnswer={answerAsk} />);
      } else if (row.kind === "approval") {
        const optimistic = decidedApprovals[row.seq];
        const serverStatus = b.status && b.status !== "pending" ? b.status : null;
        const resolved: string | null = optimistic
          ? (optimistic === "deny" ? "denied" : "approved")
          : serverStatus;
        if (resolved) {
          // decided: the card collapses to a single muted line and a click
          // on Allow once/Always allow/Don't allow dismisses it for good
          out.push(
            <div key={row.seq} className="approval-resolved" role="status">
              <span className={`resolved-dot ${resolved === "denied" ? "deny" : "allow"}`} />
              {resolved === "denied" ? "denied" : "approved"} · {b.tool_name}
              {optimistic === "always" ? " · always allow" : optimistic === "once" ? " · allow once" : optimistic === "deny" ? " · don't allow" : ""}
            </div>,
          );
        } else {
          out.push(
            <div key={row.seq} className="approval">
              <b>Approval required — {b.tool_name}</b>
              <div className="hint">Consequential tool call paused for your decision.</div>
              <div className="actions">
                <button className="btn primary" onClick={() => decideApproval(row, "once")}>Allow once</button>
                <button className="btn primary" onClick={() => decideApproval(row, "always")}>Always allow</button>
                <button className="btn dangerish" onClick={() => decideApproval(row, "deny")}>Don&apos;t allow</button>
              </div>
            </div>,
          );
        }
      }
    }
    flushStepGroup("end");
    return out;
  }

  /* ---- message actions (Copy / Fork / Undo) + asks */
  async function copyMessage(row: Row) {
    const text = row.body?.content ?? "";
    try {
      await navigator.clipboard.writeText(String(text));
      say("Message copied.");
    } catch {
      say("Could not copy to clipboard.");
    }
  }

  async function forkFromHere(row: Row) {
    if (!selectedId) return;
    try {
      const body = await api(`bots/${selectedId}/fork`, {
        method: "POST",
        body: JSON.stringify({ up_to_seq: row.seq }),
      });
      await refreshBots();
      if (body?.bot?.id) setSelectedId(body.bot.id);
      say("Forked at this point.");
    } catch (err: any) {
      say(`Fork failed: ${err.message}`);
    }
  }

  async function rewindFromHere(row: Row) {
    if (!selectedId || !window.confirm("Undo — rewind the conversation to before this message?")) return;
    try {
      const body = await api(`bots/${selectedId}/rewind`, {
        method: "POST",
        body: JSON.stringify({ from_seq: row.seq }),
      });
      const deleted = body?.rows ?? [];
      await loadRows(selectedId);
      sayAction("Rewound.", "Undo", async () => {
        try {
          await api(`bots/${selectedId}/restore`, {
            method: "POST",
            body: JSON.stringify({ rows: deleted }),
          });
          await loadRows(selectedId);
          say("Rewind undone.");
        } catch (err: any) { say(`Undo failed: ${err.message}`); }
      });
    } catch (err: any) {
      say(`Undo failed: ${err.message}`);
    }
  }

  async function answerAsk(row: Row, answer: string) {
    if (!selectedId) return;
    const askId = row.body?.ask_id;
    if (!askId) return;
    try {
      await api(`bots/${selectedId}/asks/${askId}/answer`, {
        method: "POST",
        body: JSON.stringify({ answer }),
      });
      await loadRows(selectedId);
    } catch (err: any) {
      say(`Could not answer: ${err.message}`);
    }
  }

  /* ---- derived */
  const filteredBots = bots.filter((b) =>
    !search.trim() || b.name.toLowerCase().includes(search.trim().toLowerCase()),
  );
  const recentTasks = tasks.slice(0, 5);
  const configuredCount = providers.filter((p) => p.configured).length;
  const visibleTasks = tasks.filter((t) =>
    taskFilter === "all" ? true : !["completed", "cancelled"].includes(t.status),
  );

  /* ========================================================== render */

  /* ---- Duet: tree rendering */
  function renderTreeNodes(nodes: TreeNode[], depth: number): React.ReactNode {
    return nodes.map((node) => {
      if (node.isDir) {
        const open = expandedDirs[node.path] !== false;
        return (
          <div className="tree-node" key={node.path}>
            <button
              className="tree-row tree-dir"
              style={{ paddingLeft: 8 + depth * 14 }}
              aria-expanded={open}
              onClick={() => setExpandedDirs((prev) => ({ ...prev, [node.path]: !open }))}
            >
              <svg viewBox="0 0 24 24" className={`tree-chevron${open ? " open" : ""}`} fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M9 6l6 6-6 6" /></svg>
              <svg viewBox="0 0 24 24" className="tree-glyph folder" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z" /></svg>
              <span className="tree-name">{node.name}</span>
            </button>
            {open && renderTreeNodes(node.children, depth + 1)}
          </div>
        );
      }
      return (
        <button
          key={node.path}
          className="tree-row tree-file"
          style={{ paddingLeft: 8 + depth * 14 + 14 }}
          title={node.path}
          onClick={() => void openFileTab(node.path)}
        >
          <svg viewBox="0 0 24 24" className="tree-glyph" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M7 3h8l4 4v14H7z" /><path d="M15 3v4h4" /></svg>
          <span className="tree-name">{node.name}</span>
          <span className="tree-size">{fmtBytes(node.size ?? 0)}</span>
        </button>
      );
    });
  }

  function renderDuetNav() {
    const tree = buildTree(treeEntries);
    return (
      <>
        <div className="side-label"><span>Projects</span><span className="count">{projects.length}</span></div>
        <form className="project-add" onSubmit={(e) => { e.preventDefault(); void addProject(); }}>
          <input
            value={projectPathInput}
            onChange={(e) => setProjectPathInput(e.target.value)}
            placeholder="Paste an absolute folder path…"
            aria-label="Project folder path"
            spellCheck={false}
          />
          <button className="btn primary" type="submit" disabled={projectAdding || !projectPathInput.trim()}>
            {projectAdding ? "…" : "Add"}
          </button>
        </form>
        <p className="project-hint">The browser can’t see your disk, so paste the path — e.g. <code>C:\Users\you\todo-app</code>. Removing a project only hides it here; your files stay.</p>
        <div className="project-list">
          {projects.map((p) => (
            <div key={p.id} className={`project${p.id === activeProjectId ? " is-active" : ""}`}>
              <button className="project-main" onClick={() => guardedSelectProject(p.id)} title={p.path}>
                <b>{p.name}</b>
                <small>{p.path}</small>
              </button>
              <button className="project-remove" onClick={() => void removeProject(p.id)} aria-label={`Remove ${p.name}`} title="Remove from Duet — files are untouched">×</button>
            </div>
          ))}
          {projects.length === 0 && <p className="agent-empty">No project yet.</p>}
        </div>

        {activeProject && (
          <>
            <div className="side-label"><span>Files</span><span className="count">{treeEntries.length}</span></div>
            <div className="tree" aria-label="project files">
              {treeLoading && <p className="tree-loading">Reading tree…</p>}
              {!treeLoading && treeEntries.length === 0 && <p className="agent-empty">Empty folder or unreadable.</p>}
              {renderTreeNodes(tree, 0)}
              {treeEntries.length >= 4000 && <p className="tree-loading">Tree capped at 4,000 entries.</p>}
            </div>
          </>
        )}
      </>
    );
  }

  /* ---- Duet: panes */
  const tabLabel = (t: DuetTab): string => {
    switch (t.kind) {
      case "review": return "Review";
      case "terminal": return "Terminal";
      case "openfile": return "Open file";
      case "browser": return "Browser";
      case "file": {
        const cached = t.path ? fileCache[t.path] : undefined;
        const base = cached?.name ?? (t.path ? t.path.split("/").pop() ?? t.path : "file");
        return cached?.dirty ? `${base} ●` : base;
      }
    }
  };

  function renderFilePane(cacheKey: string) {
    const cached = fileCache[cacheKey];
    const pid = activeProjectId;
    if (fileLoading && !cached) {
      return (
        <div className="duet-pane-inner">
          <p className="tree-loading">Opening {cacheKey}…</p>
        </div>
      );
    }
    if (!cached) {
      return (
        <div className="duet-pane-inner">
          <p className="tree-loading">Could not open {cacheKey}.</p>
        </div>
      );
    }
    if (cached.binary) {
      const isImage = cached.mime.startsWith("image/");
      return (
        <div className="duet-pane-inner openfile-pane">
          <div className="pane-head">
            <div className="pane-title">
              <h2>{cached.name}</h2>
              <p>{cached.path} · {fmtBytes(cached.size)}{cached.truncated ? " · truncated at 1.5 MB" : ""}</p>
            </div>
          </div>
          <div className="binary-body">
            {isImage && cached.base64 ? (
              <img className="binary-image" alt={cached.name} src={`data:${cached.mime};base64,${cached.base64}`} />
            ) : (
              <div className="binary-note">
                <p><b>Binary file</b> — {fmtBytes(cached.size)}, {cached.mime}</p>
                <p>No inline preview. Use your editor of choice for this one.</p>
                <p className="binary-hint">Preview-by-download was deliberately not built — the bridge never hands you a file URL it didn’t sign itself.</p>
              </div>
            )}
          </div>
        </div>
      );
    }
    const lineCount = cached.content === "" ? 0 : cached.content.split("\n").length;
    return (
      <div className="duet-pane-inner openfile-pane editor-pane">
        <div className="pane-head">
          <div className="pane-title">
            <h2>{cached.path}</h2>
            <p>{fmtBytes(cached.size)} · {lineCount.toLocaleString()} lines{cached.truncated ? " · truncated at 1.5 MB — the rest of the file is not editable here" : ""}{cached.dirty ? " · unsaved changes" : ""}</p>
          </div>
          <button className="btn primary" onClick={() => void saveFile(cacheKey)} disabled={!cached.dirty || !pid}>Save</button>
        </div>
        <textarea
          className="file-editor"
          value={cached.content}
          spellCheck={false}
          aria-label={`Editing ${cached.path}`}
          onChange={(e) => {
            const value = e.target.value;
            setFileCache((prev) => ({ ...prev, [cacheKey]: { ...prev[cacheKey], content: value, dirty: true } }));
          }}
        />
      </div>
    );
  }

  function renderReviewPane() {
    const statusLines = String(reviewData?.status ?? "").split("\n").filter((l: string) => l.trim().length > 0);
    const isGit = reviewData?.is_git === true;
    return (
      <div className="duet-pane-inner review-pane">
        <div className="pane-head">
          <div className="pane-title">
            <h2>Review</h2>
            <p>{activeProject ? activeProject.path : "add a project on the left"}</p>
          </div>
          <button className="btn" onClick={() => void loadReview()} disabled={!activeProjectId || reviewLoading}>
            {reviewLoading ? "Reading git…" : "Refresh"}
          </button>
        </div>
        {!activeProject ? (
          <div className="empty-view"><h3>No project selected</h3><p>Add a folder on the left — Review reads git status, log and diffstat from it.</p></div>
        ) : reviewData?.error ? (
          <div className="empty-view"><h3>Review failed</h3><p>{reviewData.error}</p></div>
        ) : reviewData && !isGit ? (
          <div className="empty-view">
            <h3>Not a git repository</h3>
            <p>Review wants git. Either this folder isn’t a repo, or git isn’t on PATH.</p>
            <p className="empty-code">git init &nbsp;&amp;&amp;&nbsp; git add -A &nbsp;&amp;&amp;&nbsp; git commit -m "initial"</p>
          </div>
        ) : reviewData ? (
          <div className="review-sections">
            <div className="review-section">
              <h3>Working tree <span className="review-count">{statusLines.length} change{statusLines.length === 1 ? "" : "s"}</span></h3>
              {statusLines.length > 0
                ? <pre className="review-pre">{reviewData.status}</pre>
                : <p className="review-clean">Clean tree ✓</p>}
            </div>
            <div className="review-section">
              <h3>Recent commits</h3>
              <pre className="review-pre">{reviewData.log?.trim() ? reviewData.log : "(no commits yet)"}</pre>
            </div>
            <div className="review-section">
              <h3>Diffstat vs HEAD</h3>
              <pre className="review-pre">{reviewData.diff_stat?.trim() ? reviewData.diff_stat : "(nothing differs from HEAD)"}</pre>
            </div>
          </div>
        ) : (
          <p className="tree-loading">Reading git…</p>
        )}
        <p className="pane-foot">Read-only — Review never runs a mutating command. No commits, no pushes, no checkouts.</p>
      </div>
    );
  }

  function renderTerminalPane() {
    return (
      <div className="duet-pane-inner terminal-pane">
        <div className="pane-head">
          <div className="pane-title">
            <h2>Terminal</h2>
            <p>{activeProject ? activeProject.path : "add a project on the left"}</p>
          </div>
          <div className="terminal-controls">
            <select className="chip-select" value={termShell} onChange={(e) => setTermShell(e.target.value as "powershell" | "cmd" | "posix")} aria-label="Shell">
              <option value="powershell">powershell</option>
              <option value="cmd">cmd</option>
              <option value="posix">posix sh</option>
            </select>
            <button className="btn" onClick={() => setTermLines([])}>Clear</button>
          </div>
        </div>
        <pre className="terminal-out" ref={termLinesRef}>{termLines.join("\n")}</pre>
        <form className="terminal-input-row" onSubmit={(e) => { e.preventDefault(); void runTerminalCommand(); }}>
          <span className="terminal-prompt" aria-hidden="true">$</span>
          <input
            value={termInput}
            onChange={(e) => setTermInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "ArrowUp") {
                e.preventDefault();
                if (termHistory.length > 0) {
                  const idx = termHistIdx === -1 ? termHistory.length - 1 : Math.max(0, termHistIdx - 1);
                  setTermHistIdx(idx);
                  setTermInput(termHistory[idx]);
                }
              } else if (e.key === "ArrowDown") {
                e.preventDefault();
                if (termHistIdx !== -1) {
                  const idx = termHistIdx + 1;
                  if (idx >= termHistory.length) { setTermHistIdx(-1); setTermInput(""); }
                  else { setTermHistIdx(idx); setTermInput(termHistory[idx]); }
                }
              }
            }}
            placeholder={activeProjectId ? "type a command and press Enter…" : "add a project first…"}
            disabled={termBusy || !activeProjectId}
            aria-label="Command"
            spellCheck={false}
            autoComplete="off"
          />
          <button className="btn primary" type="submit" disabled={termBusy || !termInput.trim() || !activeProjectId}>
            {termBusy ? "Running…" : "Run"}
          </button>
        </form>
        <p className="pane-foot">Each command is its own detached process — there is no shared session. Long-running dev servers (npm run dev …) work fine; Ctrl+C can’t reach them from here yet, stop them with Task Manager or <code>Stop-Process</code>.</p>
      </div>
    );
  }

  function renderBrowserPane() {
    const goBrowser = (e: React.FormEvent) => {
      e.preventDefault();
      let url = browserUrl.trim();
      if (!url) return;
      if (!/^[a-z][a-z0-9+.-]*:\/\//i.test(url)) url = `http://${url}`;
      setBrowserUrl(url);
      setBrowserLoadedUrl(url);
    };
    return (
      <div className="duet-pane-inner browser-pane">
        <div className="pane-head">
          <div className="pane-title">
            <h2>Browser</h2>
            <p>embedded preview — not a full browser</p>
          </div>
          <form className="browser-bar" onSubmit={goBrowser}>
            <input
              value={browserUrl}
              onChange={(e) => setBrowserUrl(e.target.value)}
              spellCheck={false}
              autoComplete="off"
              placeholder="http://localhost:3000"
              aria-label="URL to preview"
            />
            <button className="btn primary" type="submit">Go</button>
          </form>
        </div>
        {browserLoadedUrl ? (
          <iframe
            className="browser-frame"
            src={browserLoadedUrl}
            sandbox="allow-scripts allow-same-origin allow-forms allow-popups allow-modals"
            title={`Preview of ${browserLoadedUrl}`}
            referrerPolicy="no-referrer"
          />
        ) : (
          <div className="empty-view">
            <h3>Nothing loaded yet</h3>
            <p>Type a URL and press Go. Local dev servers (localhost:3000 / 5173 / 8080) usually allow embedding. Many external sites refuse framing via CSP — that’s the site’s choice, not a Keel bug.</p>
          </div>
        )}
        <p className="pane-foot">Sandboxed preview — separate cookies, no downloads, no extensions. For anything beyond a dev-server peek, use your real browser.</p>
      </div>
    );
  }

  function renderOpenFilePane() {
    return (
      <div className="duet-pane-inner openfile-pane">
        <div className="pane-head">
          <div className="pane-title">
            <h2>Open file</h2>
            <p>{activeProject ? "click any file in the tree — or type a path here" : "add a project on the left"}</p>
          </div>
        </div>
        <form className="quick-open" onSubmit={(e) => { e.preventDefault(); const p = quickOpenPath.trim(); if (p) void openFileTab(p); }}>
          <input
            value={quickOpenPath}
            onChange={(e) => setQuickOpenPath(e.target.value)}
            placeholder="path relative to project root — e.g. src/main.ts"
            aria-label="File path"
            spellCheck={false}
            autoComplete="off"
          />
          <button className="btn primary" type="submit" disabled={!quickOpenPath.trim() || !activeProjectId}>Open</button>
        </form>
        <p className="pane-foot">Every file is openable: text files edit + save inline. Images preview. Large or binary files say so honestly. Nothing leaves your machine except what the model itself reads when you ask it to.</p>
      </div>
    );
  }

  function renderDuetMain() {
    const activeTabObj = duetTabs.find((t) => t.id === activeDuetTab) ?? null;
    const streamingBubble = streamText !== "" ? (
      <div className="bubble assistant streaming" aria-label="agent is typing">
        <span className="role">{selectedBot?.name ?? "agent"}</span>
        {streamText}
        <span className="stream-caret" aria-hidden="true" />
      </div>
    ) : null;
    return (
      <section className="duet" aria-label="Keel Duet workspace">
        <div className="duet-tabbar" role="tablist" aria-label="Duet tabs">
          {duetTabs.map((t) => (
            <div key={t.id} role="tab" aria-selected={t.id === activeDuetTab} className={`duet-tab${t.id === activeDuetTab ? " is-active" : ""}`}>
              <button className="duet-tab-label" onClick={() => setActiveDuetTab(t.id)} title={t.kind === "file" ? t.path : tabLabel(t)}>
                {tabLabel(t)}
              </button>
              <button className="duet-tab-close" onClick={() => closeDuetTab(t.id)} aria-label={`Close ${tabLabel(t)}`}>×</button>
            </div>
          ))}
          <button className="duet-tab-add" onClick={() => setTabAddOpen((v) => !v)} aria-label="Add tab" aria-expanded={tabAddOpen}>+</button>
          {tabAddOpen && (
            <div className="duet-tab-menu" role="menu" aria-label="Add tab">
              <button role="menuitem" onClick={() => addDuetTab("review")}>Review</button>
              <button role="menuitem" onClick={() => addDuetTab("terminal")}>Terminal</button>
              <button role="menuitem" onClick={() => addDuetTab("openfile")}>Open file</button>
              <button role="menuitem" onClick={() => addDuetTab("browser")}>Browser</button>
              <p className="duet-tab-menu-note">File tabs are added from the tree on the left.</p>
            </div>
          )}
        </div>

        <div className="duet-panes">
          {duetTabs.map((t) => {
            const visible = t.id === activeDuetTab;
            let pane: React.ReactNode = null;
            if (t.kind === "review") pane = renderReviewPane();
            else if (t.kind === "terminal") pane = renderTerminalPane();
            else if (t.kind === "openfile") pane = renderOpenFilePane();
            else if (t.kind === "browser") pane = renderBrowserPane();
            else if (t.kind === "file" && t.path) pane = renderFilePane(t.path);
            return (
              <div key={t.id} className="duet-pane" role="tabpanel" style={{ display: visible ? "flex" : "none" }}>
                {pane}
              </div>
            );
          })}
          {activeTabObj === null && (
            <div className="duet-pane" role="tabpanel">
              <div className="empty-view"><h3>No tabs open</h3><p>Press + to add Review, Terminal, Open file or Browser.</p></div>
            </div>
          )}
        </div>

        <div className="duet-chat" aria-label="chat with the model">
          <div className="duet-chat-scroll">
            {rows.length === 0 && !busy ? (
              <div className="duet-empty">
                <span className="duet-badge">keel duet</span>
                <p>
                  Chatting with <b>{selectedBot?.name ?? "—"}</b>
                  {activeProject ? (<> in <code>{activeProject.path}</code></>) : null}.
                  {" "}The model reads and edits files, runs shells, asks you questions, and spawns sub-agents when a job needs them — no toggle for any of that.
                </p>
                <p className="duet-empty-try">Try: <em>“Summarize this codebase, then list the top 3 risks.”</em></p>
              </div>
            ) : (
              renderRows()
            )}
            {streamingBubble}
            {busy && streamText === "" && (
              <div className="thinking-line" role="status" aria-label="agent is thinking">
                <svg className="thinking-glyph" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true"><path d="M12 3v4M12 17v4M3 12h4M17 12h4M5.6 5.6l2.8 2.8M15.6 15.6l2.8 2.8M5.6 18.4l2.8-2.8M15.6 8.4l2.8-2.8" /></svg>
                <span className="thinking-text">Thinking…</span>
              </div>
            )}
            <div ref={rowsEndRef} />
          </div>
          {renderComposer("duet")}
        </div>
      </section>
    );
  }

  /* ---- Cowork Projects page */
  function renderCoworkProjects() {
    return (
      <section className="cowork-page" aria-label="Projects">
        <div className="cowork-page-head">
          <h1 className="cowork-page-title">Projects</h1>
          <button className="cowork-cta" onClick={() => { setModalPathInput(""); setProjectModalOpen(true); }}>New project</button>
        </div>
        {projects.length === 0 ? (
          <div className="cowork-empty">
            <svg viewBox="0 0 48 48" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M6 14a4 4 0 0 1 4-4h8l4 4h16a4 4 0 0 1 4 4v18a4 4 0 0 1-4 4H10a4 4 0 0 1-4-4z" /></svg>
            <h2>No projects yet</h2>
            <p>Projects are folders Keel is allowed to work in — codebases, writing folders, anything.</p>
            <button className="cowork-cta" onClick={() => { setModalPathInput(""); setProjectModalOpen(true); }}>New project</button>
          </div>
        ) : (
          <div className="project-grid">
            {projects.map((p) => (
              <div key={p.id} className="project-card">
                <button className="project-card-main" onClick={() => { guardedSelectProject(p.id); setSurface("code"); }}>
                  <b>{p.name}</b>
                  <span className="project-card-path" title={p.path}>{p.path}</span>
                  <span className="project-card-meta">{timeAgo(p.last_opened_at || (p as any).created_at)} · {Number(p.trusted ?? 0) === 1 ? "trusted" : "not trusted"}</span>
                </button>
                <div className="project-card-foot">
                  {Number(p.trusted ?? 0) === 1 ? (
                    <button className="project-card-link" onClick={() => void revokeTrust(p.id)}>Revoke trust</button>
                  ) : (
                    <span className="project-card-warn">Trust required to work here</span>
                  )}
                  <button className="project-card-link danger" onClick={() => void removeProject(p.id)} aria-label={`Remove ${p.name}`}>Remove</button>
                </div>
              </div>
            ))}
          </div>
        )}
      </section>
    );
  }

  /* ---- Cowork Artifacts page — Keel's library, across all agents */
  function renderCoworkArtifacts() {
    const agentName = (botId?: string) => bots.find((b) => b.id === botId)?.name ?? "agent";
    return (
      <section className="cowork-page" aria-label="Artifacts">
        <div className="cowork-page-head">
          <h1 className="cowork-page-title">Artifacts</h1>
          <div className="cowork-page-actions">
            <button className="cowork-cta-outline" onClick={() => { void runPrompt(PROMPT_ATTENTION); setCowView("chat"); }}>What needs my attention</button>
            <button className="cowork-cta" onClick={() => setArtifactAskOpen(true)}>New artifact</button>
          </div>
        </div>
        {artifacts.length === 0 ? (
          <div className="cowork-empty">
            <svg viewBox="0 0 48 48" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M12 4h16l8 8v32H12z" /><path d="M28 4v8h8M18 22h10M18 29h10M18 36h6" /></svg>
            <h2>Create your first artifact</h2>
            <p>Artifacts are files your agents save to the Fleet Library — documents, code, data, anything.</p>
            <button className="cowork-cta" onClick={() => setArtifactAskOpen(true)}>New artifact</button>
          </div>
        ) : (
          <div className="artifact-grid">
            {artifacts.map((f) => (
              <button key={f.id} className="artifact-card" onClick={() => setArtifactPreview(f)} title={f.name}>
                <span className={`artifact-glyph kind-${fileKindLabel(f.mime, f.name).toLowerCase()}`}>{fileKindLabel(f.mime, f.name)}</span>
                <b className="artifact-name">{f.name}</b>
                <span className="artifact-meta">{fmtBytes(f.size)} · {agentName(f.bot_id)}</span>
              </button>
            ))}
          </div>
        )}
      </section>
    );
  }

  /* ---- Cowork Scheduled page */
  function renderCoworkScheduled() {
    const activeRoutines = routines.filter((r: any) => r.enabled !== false);
    const templateCards = [
      { t: ROUTINE_TEMPLATES[0], icon: <circle cx="12" cy="13" r="8" />, desc: "What happened overnight, what’s due today" },
      { t: ROUTINE_TEMPLATES[1], icon: <path d="M4 6h16M4 12h16M4 18h10" />, desc: "Prioritize open tasks, grouped by urgency" },
      { t: ROUTINE_TEMPLATES[2], icon: <rect x="3" y="5" width="18" height="16" rx="2" />, desc: "Talking points for your calendar" },
      { t: ROUTINE_TEMPLATES[3], icon: <path d="M5 19l6-7-6-7M13 5h7M13 12h7M13 19h7" />, desc: "Friday wrap-up and next week’s focus" },
      { t: ROUTINE_TEMPLATES[4], icon: <path d="M12 3l9 16H3z" />, desc: "Ideas from your files and recent work" },
      { t: ROUTINE_TEMPLATES[5], icon: <circle cx="12" cy="12" r="9" />, desc: "What changed since yesterday, flagged" },
    ];
    return (
      <section className="cowork-page" aria-label="Scheduled tasks">
        <div className="cowork-page-head">
          <div>
            <h1 className="cowork-page-title">Scheduled</h1>
            <p className="cowork-page-sub">Run tasks on a schedule or whenever you need them.</p>
          </div>
          <button className="cowork-cta" onClick={() => {
            setRoutineName(""); setRoutinePrompt(""); setRoutineCron("0 8 * * *");
            setRoutineTz(Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC");
            setRoutineModalOpen(true);
          }}>New task</button>
        </div>

        <div className="keep-awake-bar" role="status">
          <span className="keep-awake-icon">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round"><circle cx="12" cy="12" r="4.5" /><path d="M12 2v2M12 20v2M2 12h2M20 12h2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" /></svg>
          </span>
          <span className="keep-awake-text">Scheduled tasks only run while your computer is awake and online.</span>
          <label className="keep-awake-toggle">
            <span>Keep awake</span>
            <button
              role="switch"
              aria-checked={!!keepAwake?.on}
              className={`switch${keepAwake?.on ? " is-on" : ""}`}
              onClick={() => void toggleKeepAwake()}
              disabled={!keepAwake?.supported}
              title={keepAwake?.supported === false ? "Keep awake is Windows-only right now" : "Prevent this machine from sleeping"}
              aria-label="Toggle keep awake"
            ><span className="switch-knob" /></button>
          </label>
        </div>

        {routines.length === 0 ? (
          <>
            <div className="cowork-empty slim">
              <svg viewBox="0 0 64 64" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true"><circle cx="32" cy="36" r="18" /><path d="M32 26v10l7 7M25 4h14" /></svg>
              <h2>No scheduled tasks yet.</h2>
            </div>
            <p className="template-label">Start from a template</p>
            <div className="template-grid">
              {templateCards.map(({ t, icon, desc }) => (
                <button key={t.name} className="template-card" onClick={() => void createRoutineFromTemplate(t)}>
                  <span className="template-icon"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">{icon}</svg></span>
                  <b>{t.name}</b>
                  <span className="template-desc">{desc}</span>
                  <span className="template-cron">{t.cron} UTC</span>
                </button>
              ))}
            </div>
          </>
        ) : (
          <div className="routine-list">
            {routines.map((r: any) => {
              const paused = !!r.paused;
              const agent = bots.find((b) => b.id === r.bot_id)?.name ?? "agent";
              return (
                <div key={r.id} className={`routine-row${r.enabled && !paused ? " is-live" : ""}`}>
                  <span className="routine-dot" aria-hidden="true" />
                  <div className="routine-main">
                    <b>{r.name}</b>
                    <p className="routine-prompt">{r.prompt}</p>
                    <span className="routine-meta">{r.cron_expr} {r.timezone ?? "UTC"} · runs on {agent}{paused ? " · paused" : ""}</span>
                  </div>
                  <div className="routine-actions">
                    <button className="btn" onClick={() => void routineAction(r.id, "run")} title="Run now">Run</button>
                    {paused
                      ? <button className="btn" onClick={() => void routineAction(r.id, "resume")}>Resume</button>
                      : <button className="btn" onClick={() => void routineAction(r.id, "pause")}>Pause</button>}
                    <button className="btn danger" onClick={() => void routineAction(r.id, "delete")}>Delete</button>
                  </div>
                </div>
              );
            })}
            <p className="template-label">More automation</p>
            <div className="template-grid">
              {templateCards.map(({ t, icon, desc }) => (
                <button key={t.name} className="template-card" onClick={() => void createRoutineFromTemplate(t)}>
                  <span className="template-icon"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">{icon}</svg></span>
                  <b>{t.name}</b>
                  <span className="template-desc">{desc}</span>
                  <span className="template-cron">{t.cron} UTC</span>
                </button>
              ))}
            </div>
          </div>
        )}
      </section>
    );
  }

  /* ---- Cowork Customize page */
  function renderCoworkCustomize() {
    const skillSections: { key: string; label: string; items: any[] }[] = [
      { key: "user", label: "Created by you", items: (skills ?? []).filter((s) => s.scope === "user") },
      { key: "bundled", label: "From Keel (bundled)", items: (skills ?? []).filter((s) => s.scope === "bundled") },
      { key: "project", label: "Project scope", items: (skills ?? []).filter((s) => s.scope === "project") },
    ];
    const filter = skillsFilter.trim().toLowerCase();
    const matches = (s: any) => !filter || s.name.toLowerCase().includes(filter) || (s.description ?? "").toLowerCase().includes(filter);
    const tabBtn = (id: CustomizeTab, label: string, count?: number) => (
      <button key={id} className={`customize-tab${customizeTab === id ? " is-active" : ""}`} onClick={() => setCustomizeTab(id)} role="tab" aria-selected={customizeTab === id}>
        {label}{typeof count === "number" ? <span className="customize-count">{count}</span> : null}
      </button>
    );
    return (
      <section className="cowork-page" aria-label="Customize Keel">
        <div className="cowork-page-head">
          <h1 className="cowork-page-title">Customize</h1>
          {customizeTab === "skills" && (
            <input
              className="customize-search"
              placeholder="Search skills…"
              value={skillsFilter}
              onChange={(e) => setSkillsFilter(e.target.value)}
              aria-label="Search skills"
            />
          )}
        </div>
        <div className="customize-tabs" role="tablist" aria-label="Customize sections">
          {tabBtn("skills", "Skills", skills?.length)}
          {tabBtn("connectors", "Connectors", connectors?.length)}
          {tabBtn("plugins", "Plugins")}
        </div>

        {customizeTab === "skills" && (
          <div className="skills-body">
            {skills === null && <p className="tree-loading">Loading skills…</p>}
            {skills !== null && skills.length === 0 && <p className="tree-loading">No skills found. Bundled skills ship with Keel; your own live in <code>~/.keel/skills</code>.</p>}
            {skillSections.map((sec) => {
              const items = sec.items.filter(matches);
              if (items.length === 0) return null;
              return (
                <div key={sec.key} className="skills-section">
                  <h3>{sec.label} <span className="customize-count">{items.length}</span></h3>
                  {items.map((s) => (
                    <div key={`${s.scope}-${s.name}`} className="skill-row">
                      <span className="skill-glyph"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round"><path d="M4 6h16M4 12h16M4 18h7" /><rect x="17" y="15" width="4" height="4" rx="0.8" /></svg></span>
                      <span className="skill-main">
                        <b>{s.name}</b>
                        <span className="skill-desc">{s.description || "No description."}</span>
                      </span>
                      <span className="skill-flags">
                        {Number(s.injection_suspects ?? 0) > 0
                          ? <span className="skill-flag warn" title="Lines in the skill body look like shell injection — flagged, not run">{s.injection_suspects} flag{Number(s.injection_suspects) === 1 ? "" : "s"}</span>
                          : <span className="skill-flag ok">clean</span>}
                        {s.scope === "project" && <span className="skill-flag warn">project-scope · untrusted by default</span>}
                      </span>
                    </div>
                  ))}
                </div>
              );
            })}
          </div>
        )}

        {customizeTab === "connectors" && (
          <div className="skills-body">
            {connectors === null && <p className="tree-loading">Loading connectors…</p>}
            {connectors !== null && connectors.length === 0 && (
              <div className="connectors-empty">
                <p>No MCP servers configured. Add them to <code>~/.keel/settings.json</code>, then restart Keel:</p>
                <pre>{'{\n  "mcpServers": {\n    "my-server": {\n      "command": "npx",\n      "args": ["-y", "my-mcp-server"]\n    }\n  }\n}'}</pre>
                <p className="connectors-note">Keel speaks stdio MCP only. Nothing is connected until you list it here — there is no marketplace and no auto-install.</p>
              </div>
            )}
            {connectors !== null && connectors.length > 0 && connectors.map((c) => (
              <div key={c.name} className="connector-row">
                <span className="skill-glyph"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round"><path d="M12 2v6M12 16v6M4.9 4.9l4.2 4.2M14.9 14.9l4.2 4.2M2 12h6M16 12h6M4.9 19.1l4.2-4.2M14.9 9.1l4.2-4.2" /></svg></span>
                <span className="skill-main">
                  <b>{c.name}</b>
                  <code className="connector-command">{c.command}{c.args?.length ? ` ${c.args.join(" ")}` : ""}</code>
                </span>
                {c.env_keys?.length > 0 && <span className="skill-flags"><span className="skill-flag">{c.env_keys.length} env</span></span>}
              </div>
            ))}
          </div>
        )}

        {customizeTab === "plugins" && (
          <div className="plugins-panel">
            <h2>Keel has no plugin system yet.</h2>
            <p>Skills and MCP connectors are the two extension points today, on purpose:</p>
            <ul>
              <li><b>Skills</b> — teach Keel how to do something (a workflow, a house style, a domain). They live in <code>~/.keel/skills</code> or ship with the app.</li>
              <li><b>Connectors</b> — give Keel something to talk to (your database, your browser, your tracker). Any stdio MCP server works.</li>
            </ul>
            <button className="cowork-cta-outline" onClick={() => setCustomizeTab("skills")}>View bundled skills</button>
          </div>
        )}
      </section>
    );
  }

  /* ---- Cowork main switch */
  function renderCoworkMain() {
    switch (cowView) {
      case "chat": return renderCoworkChat();
      case "projects": return renderCoworkProjects();
      case "artifacts": return renderCoworkArtifacts();
      case "scheduled": return renderCoworkScheduled();
      case "customize": return renderCoworkCustomize();
      default: return renderCoworkHome();
    }
  }

  /* ---- Code surface — chat + environment/context/connectors rail */
  function renderRailCard(title: string, children: React.ReactNode, action?: React.ReactNode) {
    return (
      <div className="rail-card">
        <div className="rail-head">
          <h3>{title}</h3>
          {action}
        </div>
        {children}
      </div>
    );
  }

  function renderCodeMain() {
    const used = usageData
      ? Number(usageData.input_tokens ?? 0) + Number(usageData.output_tokens ?? 0)
      : null;
    const cacheRead = usageData ? Number(usageData.cache_read_input_tokens ?? 0) : 0;
    const cacheWrite = usageData ? Number(usageData.cache_creation_input_tokens ?? 0) : 0;
    const ctxPct = currentContextWindow && used !== null
      ? Math.min(100, (used / currentContextWindow) * 100)
      : null;
    return (
      <section className="code-main" aria-label="Keel Code session">
        <div className="code-chat">
          <div className="code-chat-scroll">
            {rows.length === 0 && !busy ? (
              <div className="code-empty">
                <Starburst size={44} />
                <p>Describe a task or ask a question.</p>
                {activeProject
                  ? <p className="code-empty-sub">Working in <code>{activeProject.path}</code></p>
                  : <p className="code-empty-sub">No folder picked — the model works wherever it is unless you add one.</p>}
              </div>
            ) : renderRows()}
            {streamText !== "" && (
              <div className="bubble assistant streaming" aria-label="agent is typing">
                <span className="role">{selectedBot?.name ?? "agent"}</span>
                {streamText}
                <span className="stream-caret" aria-hidden="true" />
              </div>
            )}
            {busy && streamText === "" && (
              <div className="thinking-line" role="status" aria-label="agent is thinking">
                <svg className="thinking-glyph" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true"><path d="M12 3v4M12 17v4M3 12h4M17 12h4M5.6 5.6l2.8 2.8M15.6 15.6l2.8 2.8M5.6 18.4l2.8-2.8M15.6 8.4l2.8-2.8" /></svg>
                <span className="thinking-text">Thinking…</span>
              </div>
            )}
            <div ref={rowsEndRef} />
          </div>
          {renderComposer("code")}
        </div>

        <aside className="code-rail" aria-label="session details">
          {renderRailCard("Environment", (
            <div className="rail-env">
              <div className="rail-env-row">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round"><rect x="3" y="4" width="18" height="14" rx="2" /><path d="M8 21h8M12 18v3" /></svg>
                <div>
                  <b>This computer</b>
                  <span>{activeProject ? `${activeProject.name} · local folder` : "local machine — no folder picked"}</span>
                </div>
                <button className="rail-save" onClick={saveEnvironment}>Save</button>
              </div>
              <div className="rail-env-path" title={activeProject?.path ?? ""}>
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round"><path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z" /></svg>
                <span>{activeProject ? activeProject.path : "Add a folder from Projects — or with the + menu"}</span>
              </div>
            </div>
          ))}

          {renderRailCard("Context", (
            <div className="rail-context">
              <div className="rail-context-top">
                <b className="rail-context-pct">
                  {ctxPct !== null ? `${ctxPct < 1 ? "<1" : Math.round(ctxPct)}%` : "—"}
                </b>
                <span className="rail-context-total">
                  {currentContextWindow
                    ? `${used !== null ? used.toLocaleString() : "…"} / ${currentContextWindow.toLocaleString()}`
                    : `${used !== null ? used.toLocaleString() : "…"} tokens`}
                </span>
              </div>
              <div className="rail-context-bar" aria-hidden="true">
                <div className="rail-context-fill" style={{ width: ctxPct !== null ? `${Math.max(1.5, ctxPct)}%` : "0%" }} />
              </div>
              <div className="rail-context-rows">
                <div><span>Messages & reasoning</span><b>{used !== null ? used.toLocaleString() : "…"}</b></div>
                <div><span>Cache reads</span><b>{cacheRead.toLocaleString()}</b></div>
                <div><span>Cache writes</span><b>{cacheWrite.toLocaleString()}</b></div>
                {currentContextWindow && used !== null && (
                  <div><span>Free space</span><b>{Math.max(0, currentContextWindow - used).toLocaleString()}</b></div>
                )}
              </div>
              <p className="rail-note">
                {currentContextWindow
                  ? "Sum of this install’s recorded turns; window from the model catalog."
                  : "Context window not exposed by this model — raw totals only."}
              </p>
            </div>
          ))}

          {renderRailCard("Connectors", (
            <div className="rail-connectors">
              {connectors === null ? (
                <p className="tree-loading">Loading…</p>
              ) : connectors.length === 0 ? (
                <div className="rail-connectors-empty">
                  <p>No MCP servers configured.</p>
                  <button className="rail-save" onClick={() => { setSurface("cowork"); setCowView("customize"); setCustomizeTab("connectors"); void loadConnectors(); }}>How to add →</button>
                </div>
              ) : (
                <>
                  {connectors.slice(0, 6).map((c) => (
                    <div key={c.name} className="rail-connector">
                      <span className="rail-connector-dot" aria-hidden="true" />
                      <div>
                        <b>{c.name}</b>
                        <span>{c.command}</span>
                      </div>
                    </div>
                  ))}
                  {connectors.length > 6 && <p className="rail-note">+{connectors.length - 6} more</p>}
                  <button className="rail-save" onClick={() => { setSurface("cowork"); setCowView("customize"); setCustomizeTab("connectors"); }}>Manage</button>
                </>
              )}
            </div>
          ))}
        </aside>
      </section>
    );
  }

  function saveEnvironment() {
    if (!activeProjectId) { say("No folder picked — add one in Projects or with the + menu."); return; }
    setDefaultProjectId(activeProjectId);
    try { window.localStorage.setItem("keel-default-project", activeProjectId); } catch { /* ignore */ }
    say("Saved as your environment — next launch reopens this folder.");
  }

  function addFolderFromMenu() {
    setSurface("cowork");
    setCowView("home");
    window.setTimeout(() => coworkFolderRef.current?.focus(), 80);
  }

  /* ---- Cowork glyph — our own starburst, not anyone else's */
  function Starburst({ size = 56 }: { size?: number }) {
    const rays = Array.from({ length: 9 }, (_, i) => i);
    return (
      <svg width={size} height={size} viewBox="0 0 48 48" fill="none" aria-hidden="true" className="starburst">
        {rays.map((i) => (
          <line
            key={i}
            x1="24" y1="24"
            x2={24 + 17 * Math.cos((i * Math.PI * 2) / 9)}
            y2={24 + 17 * Math.sin((i * Math.PI * 2) / 9)}
            stroke="currentColor" strokeWidth="2.1" strokeLinecap="round"
          />
        ))}
        <circle cx="24" cy="24" r="4.6" fill="currentColor" />
      </svg>
    );
  }

  const timeAgo = (iso: string): string => {
    const then = new Date(iso).getTime();
    if (Number.isNaN(then)) return "";
    const sec = Math.max(0, (Date.now() - then) / 1000);
    if (sec < 60) return "just now";
    if (sec < 3600) return `${Math.floor(sec / 60)}m ago`;
    if (sec < 86400) return `${Math.floor(sec / 3600)}h ago`;
    const days = Math.floor(sec / 86400);
    if (days < 30) return `${days}d ago`;
    return `${Math.floor(days / 30)}mo ago`;
  };

  const fileKindLabel = (mime?: string, name?: string): string => {
    const m = mime ?? "";
    const n = (name ?? "").toLowerCase();
    if (m.includes("pdf")) return "PDF";
    if (m.startsWith("image/")) return "Image";
    if (m.startsWith("text/") || /\.(md|txt|csv|json|ya?ml|html?|xml|svg)$/.test(n)) return "Text";
    if (/\.(docx?|odt)$/.test(n)) return "Word";
    if (/\.(xlsx?|csv)$/.test(n)) return "Sheet";
    if (/\.(pptx?|key)$/.test(n)) return "Slides";
    return "File";
  };

  /* ---- Cowork sidebar */
  function renderCoworkNav() {
    const item = (id: CowView | "home", label: string, icon: React.ReactNode, badge?: number) => (
      <button
        key={id}
        className={`cowork-nav-item${cowView === id ? " is-active" : ""}`}
        onClick={() => setCowView(id as CowView)}
        aria-current={cowView === id ? "page" : undefined}
      >
        <span className="cowork-nav-icon">{icon}</span>
        <span>{label}</span>
        {typeof badge === "number" && badge > 0 && <span className="cowork-nav-badge">{badge}</span>}
      </button>
    );
    const ic = (paths: React.ReactNode) => (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">{paths}</svg>
    );
    return (
      <>
        <div className="side-label"><span>Keel Cowork</span><span className="count cowork-mark">co</span></div>
        <button
          className="cowork-new"
          onClick={() => { setDraft(""); setSelectedId(null); setCowView("home"); }}
        >
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round"><path d="M12 5v14M5 12h14" /></svg>
          New chat
        </button>
        <div className="cowork-nav">
          {item("projects", "Projects", ic(<><path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z" /></>), projects.length)}
          {item("artifacts", "Artifacts", ic(<><path d="M7 3h8l5 5v13H7z" /><path d="M15 3v5h5M10 13h5M10 17h5" /></>), artifacts.length)}
          {item("scheduled", "Scheduled", ic(<><circle cx="12" cy="13" r="8" /><path d="M12 9.5V13l2.2 2.2M9 2.5h6" /></>), routines.filter((r: any) => r.enabled !== false && !r.paused).length)}
          {item("customize", "Customize", ic(<><path d="M4 6h16M4 12h10M4 18h7" /><circle cx="19" cy="18" r="2.4" /></>))}
        </div>
        <div className="side-label"><span>Recents</span></div>
        <div className="recents">
          {recentTasks.length === 0 ? (
            <p className="recents-empty">No tasks yet.</p>
          ) : (
            recentTasks.map((t) => (
              <button key={t.id} className="ri" onClick={() => { setSurface("fleet" as Surface); setView("tasks"); }}>
                <b>{t.title}</b>
                <span>{t.status}</span>
              </button>
            ))
          )}
        </div>
      </>
    );
  }

  /* ---- Cowork home */
  const [projectMenuOpen, setProjectMenuOpen] = useState(false);
  function renderCoworkHome() {
    const folderLabel = activeProject?.name ?? null;
    return (
      <section className="cowork-home" aria-label="Keel Cowork home">
        <div className="cowork-hero">
          <Starburst size={54} />
          <h1 className="cowork-hello">You’re here.</h1>
          <p className="cowork-sub">Keel Cowork — your desktop for everything Keel does.</p>
        </div>

        <form
          className="cowork-composer"
          onSubmit={(e) => {
            e.preventDefault();
            const botId = firstAgentId();
            if (!botId) { say("Create an agent first — Keel works through agents."); return; }
            if (!selectedId) setSelectedId(botId);
            const prompt = draft.trim();
            if (!prompt) return;
            void sendMessageRaw(prompt, mode).then(() => setCowView("chat"));
            setDraft("");
          }}
        >
          <textarea
            autoFocus
            rows={2}
            className="cowork-composer-input"
            placeholder="How can I help you today?"
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                e.currentTarget.form?.requestSubmit();
              }
            }}
            onFocus={() => { if (!selectedId && bots[0]) setSelectedId(bots[0].id); }}
            aria-label="Message Keel"
          />
          <div className="cowork-composer-bar">
            <button type="button" className="chip-btn attach-btn" title="Add files, folder, or commands" aria-label="More options" aria-expanded={menuOpen} onClick={() => setMenuOpen((v) => !v)}>
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" aria-hidden="true"><path d="M12 5v14M5 12h14" /></svg>
            </button>
            {menuOpen && (
              <div className="composer-menu" role="menu" aria-label="Add things to the conversation">
                <button role="menuitem" onClick={() => { setMenuOpen(false); attachRef.current?.click(); }}>
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"><path d="M21.4 11.05l-8.49 8.49a6 6 0 0 1-8.49-8.49l9.2-9.2a4 4 0 0 1 5.66 5.66l-9.2 9.19a2 2 0 0 1-2.83-2.83l8.49-8.48" /></svg>
                  <span>Add files or photos</span><kbd>Ctrl+U</kbd>
                </button>
                <button role="menuitem" onClick={() => { setMenuOpen(false); coworkFolderRef.current?.focus(); }}>
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"><path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z" /></svg>
                  <span>Add folder</span>
                </button>
                <button role="menuitem" onClick={() => { setMenuOpen(false); setDraft("/"); }}>
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round"><path d="M6 20L12 4M15 20l-4-8" /></svg>
                  <span>Slash commands</span><kbd>/</kbd>
                </button>
                <button role="menuitem" onClick={() => { setMenuOpen(false); setCowView("customize"); setCustomizeTab("connectors"); }}>
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"><path d="M12 2v4M12 18v4M4.9 4.9l2.8 2.8M16.3 16.3l2.8 2.8M2 12h4M18 12h4M4.9 19.1l2.8-2.8M16.3 7.7l2.8-2.8" /><circle cx="12" cy="12" r="4" /></svg>
                  <span>Manage connectors</span>
                </button>
              </div>
            )}
            <div className="cowork-composer-right">
              <select className="chip-select model-select" value={currentModel || ""} onChange={(e) => changeModel(e.target.value)} title="Model" aria-label="Model">
                {modelChoices.length === 0 && <option value="">no model</option>}
                {modelChoices.map((m) => (<option key={m} value={m}>{m}</option>))}
              </select>
              <button className="cowork-send" type="submit" disabled={!draft.trim()} aria-label="Send message" title="Send">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.1" strokeLinecap="round" strokeLinejoin="round"><path d="M12 19V5M5 12l7-7 7 7" /></svg>
              </button>
            </div>
          </div>
        </form>

        <div className="cowork-folder-wrap">
          <button type="button" className="cowork-folder-btn" onClick={() => setProjectMenuOpen((v) => !v)} aria-expanded={projectMenuOpen}>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"><path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z" /></svg>
            {folderLabel ?? "Project or folder"}
            <svg viewBox="0 0 24 24" className="cowork-chev" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" aria-hidden="true"><path d="M6 9l6 6 6-6" /></svg>
          </button>
          {projectMenuOpen && (
            <div className="cowork-folder-menu" role="menu" aria-label="Pick a project or add a folder">
              <div className="cowork-folder-head">Projects</div>
              {projects.map((p) => (
                <button key={p.id} role="menuitem" className="cowork-folder-item" onClick={() => { setProjectMenuOpen(false); guardedSelectProject(p.id); setSurface("code"); }}>
                  <b>{p.name}</b>
                  <small>{p.path}</small>
                </button>
              ))}
              {projects.length === 0 && <p className="cowork-folder-empty">No projects yet — add one below.</p>}
              <form className="cowork-folder-add" onSubmit={(e) => { e.preventDefault(); void addProject(); }}>
                <input
                  ref={coworkFolderRef}
                  value={projectPathInput}
                  onChange={(e) => setProjectPathInput(e.target.value)}
                  placeholder="Paste an absolute folder path…"
                  aria-label="Folder path"
                  spellCheck={false}
                />
                <button className="btn primary" type="submit" disabled={projectAdding || !projectPathInput.trim()}>{projectAdding ? "…" : "Add"}</button>
              </form>
            </div>
          )}
        </div>

        <div className="cowork-ideas" aria-label="Ideas for you">
          <p className="cowork-ideas-label">Ideas for you</p>
          <button className="idea-card" onClick={() => { const t = ROUTINE_TEMPLATES[0]; void createRoutineFromTemplate(t); setCowView("scheduled"); }}>
            <span className="idea-icon"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="13" r="8" /><path d="M12 9.5V13l2.2 2.2M9 2.5h6" /></svg></span>
            <b>Send me a daily briefing</b>
            <span>Your agents’ work, your priorities — every morning.</span>
          </button>
          <button className="idea-card" onClick={() => { void runPrompt(PROMPT_FLEET_SUMMARY); setCowView("chat"); }}>
            <span className="idea-icon"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round"><path d="M4 6h16M4 12h16M4 18h10" /></svg></span>
            <b>Summarize my fleet</b>
            <span>What every agent did, and the next three things to do.</span>
          </button>
          <button className="idea-card" onClick={() => { void runPrompt(PROMPT_ATTENTION); setCowView("chat"); }}>
            <span className="idea-icon"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round"><path d="M12 3l9 16H3z" /><path d="M12 10v4M12 17h.01" /></svg></span>
            <b>What needs my attention</b>
            <span>Priorities across agents, tasks, projects, and files.</span>
          </button>
        </div>
      </section>
    );
  }

  /* ---- Cowork chat (after the first message from home) */
  function renderCoworkChat() {
    return (
      <section className="cowork-chat" aria-label="Conversation">
        <div className="cowork-chat-head">
          <button className="btn" onClick={() => setCowView("home")} title="Back to Cowork home">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" style={{ width: 12, height: 12, verticalAlign: "-2px", marginRight: 6 }}><path d="M15 6l-6 6 6 6" /></svg>
            New chat
          </button>
          <span className="cowork-chat-title">{selectedBot?.name ?? "Keel"}</span>
          {activeProject && <span className="duet-badge" title={activeProject.path}>{activeProject.name}</span>}
        </div>
        <div className="duet-chat-scroll">
          {rows.length === 0 && !busy ? (
            <div className="duet-empty"><p>Thinking about your request…</p></div>
          ) : renderRows()}
          {streamText !== "" && (
            <div className="bubble assistant streaming" aria-label="agent is typing">
              <span className="role">{selectedBot?.name ?? "agent"}</span>
              {streamText}
              <span className="stream-caret" aria-hidden="true" />
            </div>
          )}
          {busy && streamText === "" && (
            <div className="thinking-line" role="status" aria-label="agent is thinking">
              <svg className="thinking-glyph" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true"><path d="M12 3v4M12 17v4M3 12h4M17 12h4M5.6 5.6l2.8 2.8M15.6 15.6l2.8 2.8M5.6 18.4l2.8-2.8M15.6 8.4l2.8-2.8" /></svg>
              <span className="thinking-text">Thinking…</span>
            </div>
          )}
          <div ref={rowsEndRef} />
        </div>
        {renderComposer("cowork")}
      </section>
    );
  }

  /* ---- shared composer (Fleet + Code + Duet) */
  function renderComposer(kind: Surface | "fleet" = "fleet") {
    const isDuet = kind !== "fleet" && kind !== "cowork";
    return (
      <div className="composer">
        {queue.length > 0 && (
          <div className="queue-panel" aria-label="Queued messages">
            <div className="queue-panel-head">
              <span>QUEUE · {queue.length}</span>
              <button className="queue-clear" onClick={() => setQueue([])}>Clear queue</button>
            </div>
            {queue.map((q, i) => (
              <div className="queue-item" key={q.id} title={q.content}>
                <span className="queue-num">#{i + 1}</span>
                <span className="queue-text">{q.content}</span>
                <button onClick={() => setQueue((prev) => prev.filter((x) => x.id !== q.id))} aria-label="Remove from queue">×</button>
              </div>
            ))}
          </div>
        )}

        {slashOpen && (
          <div className="slash-pop" role="listbox" aria-label="Slash commands">
            <div className="slash-pop-head">Commands — ↑↓ to move, ⏎ to run</div>
            {slashMatches.map((c, i) => (
              <button
                key={c.name}
                role="option"
                aria-selected={i === slashIdx}
                className={`slash-row${i === slashIdx ? " is-selected" : ""}`}
                onMouseEnter={() => setSlashIdx(i)}
                onClick={() => runSlash(c.name, slashArgs)}
              >
                <span className="slash-name">/{c.name}</span>
                <span className="slash-desc">{c.desc}</span>
              </button>
            ))}
          </div>
        )}

        {usageOpen && (
          <div className="usage-pop" role="dialog" aria-label="Context usage">
            <div className="usage-head">
              <span>Context — tokens recorded by the bridge</span>
              <button className="queue-clear" onClick={() => setUsageOpen(false)}>Close esc</button>
            </div>
            {usageData ? (
              <div className="usage-grid">
                <div><b>{(usageData.input_tokens ?? 0).toLocaleString()}</b><span>input tokens</span></div>
                <div><b>{(usageData.output_tokens ?? 0).toLocaleString()}</b><span>output tokens</span></div>
                <div><b>{(usageData.cache_read_input_tokens ?? 0).toLocaleString()}</b><span>cache reads</span></div>
                <div><b>{(usageData.cache_creation_input_tokens ?? 0).toLocaleString()}</b><span>cache writes</span></div>
                <div className="usage-total"><b>{(((usageData.input_tokens ?? 0) + (usageData.output_tokens ?? 0))).toLocaleString()}</b><span>total in+out</span></div>
              </div>
            ) : (
              <p className="usage-note">Loading usage…</p>
            )}
            <p className="usage-note">Sum of every finished turn across all agents on this install. Remaining context window depends on the model — there is no honest universal number.</p>
          </div>
        )}

        {helpOpen && (
          <div className="help-pop" role="dialog" aria-label="Keel Duet help">
            <div className="usage-head">
              <span>Keel Duet — what it can do</span>
              <button className="queue-clear" onClick={() => setHelpOpen(false)}>Close esc</button>
            </div>
            <ul className="help-list">
              <li><b>Chat</b> — talk to any of your agents; the model edits, reads, runs shells, and delegates on its own.</li>
              <li><b>Sub-agents</b> — the model spawns <code>Task</code> sub-agents automatically when a job needs them. Nothing to toggle; it just decides.</li>
              <li><b>Tabs</b> — Review (git status · log · diffstat), Terminal (detached, output streams), Open file (edit + save any text file), Browser (iframe preview), plus one tab per file.</li>
              <li><b>Files</b> — the paperclip attaches <i>any</i> file: text is sent in full, small binaries as base64, the rest by name+size.</li>
              <li><b>/commands</b> — <code>/context</code> usage, <code>/model &lt;name&gt;</code>, <code>/shell &lt;cmd&gt;</code>, <code>/review</code>, <code>/open &lt;path&gt;</code>, <code>/help</code>.</li>
              <li><b>Ctrl+B</b> — background shells pill. <b>Ctrl+Enter</b> — queue follow-up. <b>Esc</b> — close pop-ups.</li>
              <li><b>Autopilot</b> — the agent works without asking first; Tier-2 and deny rules still bind.</li>
            </ul>
          </div>
        )}

        <div className="composer-box">
          <input
            ref={composerRef}
            placeholder={busy
              ? "Working… queue a follow-up (Ctrl+Enter) or stop"
              : isDuet
                ? `Ask ${selectedBot?.name ?? "your agent"} about ${activeProject?.name ?? "the project"}…  ( / for commands, 📎 to attach files )`
                : `Message ${selectedBot?.name ?? "your agent"}…  ( / for commands )`}
            value={draft}
            onChange={(e) => {
              setDraft(e.target.value);
              setSlashDismissed(false);
              setSlashIdx(0);
            }}
            onKeyDown={(e) => {
              if (handleSlashKeyDown(e)) return;
              if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) {
                e.preventDefault();
                enqueueDraft();
                return;
              }
              if (e.key === "Enter") {
                e.preventDefault();
                sendMessage();
              }
            }}
            aria-label="Message"
          />
          <div className="composer-toolbar">
            <div className="composer-plus-wrap">
              <button type="button" className="chip-btn attach-btn" title="Add files, folder, or commands" aria-label="More options" aria-expanded={menuOpen} onClick={() => setMenuOpen((v) => !v)}>
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" aria-hidden="true"><path d="M12 5v14M5 12h14" /></svg>
              </button>
              {menuOpen && (
                <div className="composer-menu" role="menu" aria-label="Add things to the conversation">
                  <button role="menuitem" onClick={() => { setMenuOpen(false); attachRef.current?.click(); }}>
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"><path d="M21.4 11.05l-8.49 8.49a6 6 0 0 1-8.49-8.49l9.2-9.2a4 4 0 0 1 5.66 5.66l-9.2 9.19a2 2 0 0 1-2.83-2.83l8.49-8.48" /></svg>
                    <span>Add files or photos</span><kbd>Ctrl+U</kbd>
                  </button>
                  <button role="menuitem" onClick={() => { setMenuOpen(false); addFolderFromMenu(); }}>
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"><path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z" /></svg>
                    <span>Add folder</span>
                  </button>
                  <button role="menuitem" onClick={() => { setMenuOpen(false); setDraft("/"); }}>
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round"><path d="M6 20L12 4M15 20l-4-8" /></svg>
                    <span>Slash commands</span><kbd>/</kbd>
                  </button>
                  <button role="menuitem" onClick={() => { setMenuOpen(false); setSurface("cowork"); setCowView("customize"); setCustomizeTab("connectors"); }}>
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"><path d="M12 2v4M12 18v4M4.9 4.9l2.8 2.8M16.3 16.3l2.8 2.8M2 12h4M18 12h4M4.9 19.1l2.8-2.8M16.3 7.7l2.8-2.8" /><circle cx="12" cy="12" r="4" /></svg>
                    <span>Manage connectors</span>
                  </button>
                </div>
              )}
            </div>
            <input ref={attachRef} type="file" multiple hidden aria-hidden="true" tabIndex={-1} onChange={(e) => void attachFiles(e.target.files)} />
            {isDuet && (
              <select className="chip-select duet-agent-select" value={selectedId ?? ""} onChange={(e) => setSelectedId(e.target.value)} title="Which agent chats — the agents live in the Fleet view" aria-label="Agent">
                {bots.map((b) => (<option key={b.id} value={b.id}>{b.name}</option>))}
              </select>
            )}
            <select className="chip-select" value={mode} onChange={(e) => pickMode(e.target.value as ModeSetting)} title="Manual: asks before everything · Accept edits: file writes without asking, shells still ask · Plan: read-only · Autopilot: runs without asking (Tier-2/deny rules still bind)" aria-label="Mode">
              <option value="build">Build</option>
              <option value="acceptEdits">Accept edits</option>
              <option value="plan">Plan</option>
              <option value="autopilot">Autopilot</option>
            </select>
            <select className="chip-select model-select" value={currentModel || ""} onChange={(e) => changeModel(e.target.value)} title="Model for this agent" aria-label="Model">
              {modelChoices.length === 0 && <option value="">no model — validate a key</option>}
              {modelChoices.map((m) => (<option key={m} value={m}>{m}</option>))}
            </select>
            {effortChoices.length > 0 && (
              <select className="chip-select effort-select" value={effortSel} onChange={(e) => changeEffort(e.target.value)} title={`Reasoning effort for ${currentModel}`} aria-label="Reasoning effort">
                <option value="">effort</option>
                {effortChoices.map((e) => (<option key={e} value={e}>{e}</option>))}
              </select>
            )}
            <div className="composer-spacer" />
            {shells.some((s) => s.running) && (
              <div className="shells-pill-wrap" ref={shellsRef}>
                <button type="button" className="shells-pill" onClick={() => setShellsPanel((v) => !v)} aria-label={`${shells.filter((s) => s.running).length} shell${shells.filter((s) => s.running).length === 1 ? "" : "s"} running — toggle (Ctrl+B)`} title="Background shells — Ctrl+B">
                  <span className="pill-dot" />
                  <span>{shells.filter((s) => s.running).length} shell{shells.filter((s) => s.running).length === 1 ? "" : "s"}</span>
                  <kbd>CTRL B</kbd>
                </button>
                {shellsPanel && (
                  <div className="shells-pop" role="dialog" aria-label="Background shells">
                    <div className="shells-pop-head">
                      <span>Background shells — real detached processes</span>
                      <span className="shells-pop-actions">
                        {shells.some((s) => !s.running) && <button className="queue-clear" onClick={clearFinishedShells}>Clear finished</button>}
                        <button className="queue-clear" onClick={() => setShellsPanel(false)}>Close esc</button>
                      </span>
                    </div>
                    {[...shells].sort((a, b) => Number(b.running) - Number(a.running)).map((s: any) => (
                      <div className="shell-row" key={s.handle}>
                        <span className={`pill-dot${s.running ? "" : " idle"}`} style={{ width: 8, height: 8, display: "inline-block", borderRadius: 99, background: s.running ? "var(--ok)" : s.exit_code === 0 ? "var(--muted)" : "var(--danger)" }} />
                        <span style={{ minWidth: 0, flex: 1 }}>
                          <span className="shell-cmd" title={s.command}>{s.command}</span>
                          <br />
                          <span className="shell-meta">{s.handle} · {s.shell} · {s.running ? "running" : `exit ${s.exit_code}`}{s.pid ? ` · pid ${s.pid}` : ""} · started {s.started_at}</span>
                        </span>
                      </div>
                    ))}
                    {shells.length === 0 && <div className="shell-row">No background shells. Agents start them on purpose (builds, dev servers) — they run detached and keep running.</div>}
                  </div>
                )}
              </div>
            )}
            <button type="button" className="queue-btn" disabled={!draft.trim()} onClick={enqueueDraft} title="Queue for when the current turn ends (Ctrl+Enter)">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" aria-hidden="true"><path d="M12 5v14M5 12h14" /></svg>
              Queue <kbd>CTRL⏎</kbd>
            </button>
            {busy ? (
              <button type="button" className="stop" onClick={stopTurn} aria-label="Stop the current turn" title="Stop — ends at the next model boundary">
                <svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><rect x="6" y="6" width="12" height="12" rx="2.2" /></svg>
              </button>
            ) : (
              <button type="button" className="send" onClick={sendMessage} disabled={!draft.trim()} aria-label="Send message">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M12 19V5M5 12l7-7 7 7" /></svg>
              </button>
            )}
          </div>
          <div className="composer-hints" aria-hidden="true">
            <span><b>↵</b> send</span>
            <span><b>⌃↵</b> queue</span>
            <span><b>/</b> commands</span>
            <span><b>⌃B</b> shells</span>
            <span><b>esc</b> close</span>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="win">
      {/* ============ sidebar ============ */}
      <aside className="side" aria-label="sidebar">
        <div className="dots" aria-hidden="true"><i /><i /><i /></div>

        {surface === "cowork" ? renderCoworkNav() : surface === "fleet" ? (
          <>
        <div className="nav">
          <button className="new-agent" onClick={() => setModalOpen(true)} aria-label="Create a new agent">
            <span className="plus" aria-hidden="true">+</span> New agent
          </button>
          <label className="search">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" aria-hidden="true">
              <path d="M11 18a7 7 0 1 0 0-14 7 7 0 0 0 0 14zM21 21l-5-5" />
            </svg>
            <input ref={searchRef} value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Search agents…  /" aria-label="Search agents" />
          </label>
          <button className="ghost-item" onClick={() => (selectedBot ? (setDrawerTab("notes"), setDrawerOpen(true)) : say("Select an agent first."))}>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" aria-hidden="true">
              <path d="M5 4v16M12 4v16M19 4v16M3 9h4M10 14h4M17 8h4" />
            </svg>
            Customize
          </button>
        </div>

        <div className="side-label"><span>Agents</span><span className="count">{bots.length}</span></div>
        <div className="agent-list">
          {filteredBots.map((bot) => (
            <button key={bot.id} className={`agent${bot.id === selectedId ? " is-active" : ""}`} onClick={() => setSelectedId(bot.id)}>
              <span className="avatar" style={{ background: `linear-gradient(160deg, hsl(${hueOf(bot)} 62% 55%), hsl(${hueOf(bot)} 62% 30%))` }}>
                {initials(bot.name)}
              </span>
              <span style={{ minWidth: 0 }}>
                <b>{bot.name}</b>
                <small>{bot.role || bot.engine}</small>
              </span>
            </button>
          ))}
          {filteredBots.length === 0 && (
            <p className="agent-empty">{search ? `No agents match “${search}”.` : "No agents yet."}</p>
          )}
        </div>

        <div className="side-label"><span>Recents</span></div>
        <div className="recents">
          {recentTasks.length === 0 ? (
            <p className="recents-empty">No tasks yet.</p>
          ) : (
            recentTasks.map((t) => (
              <button key={t.id} className="ri" onClick={() => setView("tasks")}>
                <b>{t.title}</b>
                <span>{t.status}</span>
              </button>
            ))
          )}
        </div>

          </>
        ) : (
          renderDuetNav()
        )}

        <div className="user">
          <span className="av">Y</span>
          <span style={{ minWidth: 0 }}>
            <b>You</b>
            <span>the operator · local</span>
          </span>
          <span className={`live-dot${live ? "" : " bad"}`} title={live ? "bridge live" : "bridge reconnecting"} />
        </div>
      </aside>

      {/* ============ main column ============ */}
      <section className="mainw">
        {/* top bar */}
        <div className="top">
          <div className="tl">
            <button aria-label="Toggle agent panel" aria-pressed={drawerOpen} onClick={() => setDrawerOpen((v) => !v)}>
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" aria-hidden="true">
                <path d="M4 4h16v16H4zM9.5 4v16" />
              </svg>
            </button>
            <span className="sep" aria-hidden="true" />
            <div className="surface-toggle" role="tablist" aria-label="Workspace">
              <button role="tab" aria-selected={surface === "cowork"} className={surface === "cowork" ? "is-active" : ""} onClick={() => setSurface("cowork")} title="Keel Cowork — the desktop, everything in one place">Cowork</button>
              <button role="tab" aria-selected={surface === "code"} className={surface === "code" ? "is-active" : ""} onClick={() => setSurface("code")} title="Keel Code — the coding session, environment and context on the right">Code</button>
              <button role="tab" aria-selected={surface === "duet"} className={surface === "duet" ? "is-active" : ""} onClick={() => setSurface("duet")} title="Keel Duet — coding with the file tree, tabs, terminal and browser">Duet</button>
              <button role="tab" aria-selected={surface === "fleet"} className={surface === "fleet" ? "is-active" : ""} onClick={() => setSurface("fleet")} title="Fleet — agents, tasks, library, routines">Fleet</button>
            </div>
          </div>

          {surface === "duet" || surface === "code" ? (
            <div className="duet-crumbs" aria-label="Project breadcrumb">
              <span className="duet-badge">{surface === "duet" ? "keel duet" : "keel code"}</span>
              {activeProject ? (
                <>
                  <b className="crumb-sep" aria-hidden="true">/</b>
                  <b className="crumb-name">{activeProject.name}</b>
                  <code className="crumb-path" title={activeProject.path}>{activeProject.path}</code>
                </>
              ) : surface === "code" ? (
                <span className="crumb-path">{selectedBot?.name ?? "no agent"} — pick a folder in Projects</span>
              ) : (
                <span className="crumb-path">no project — paste a folder path on the left</span>
              )}
            </div>
          ) : surface === "cowork" ? (
            <div className="duet-crumbs" aria-label="Keel Cowork">
              <span className="duet-badge">keel cowork</span>
              <span className="crumb-name">{cowView === "home" || cowView === "chat" ? "desktop" : cowView}</span>
              {activeProject && (
                <>
                  <b className="crumb-sep" aria-hidden="true">/</b>
                  <code className="crumb-path" title={activeProject.path}>{activeProject.name}</code>
                </>
              )}
            </div>
          ) : (
            <div className="tabs" role="tablist" aria-label="workspace views" ref={segRef}>
              <span className="seg-indicator" style={{ left: segBox.left, width: segBox.width }} aria-hidden="true" />
              {NAV.map((n, i) => (
                <button
                  key={n.id}
                  ref={(el) => { segBtns.current[i] = el; }}
                  role="tab"
                  aria-selected={view === n.id}
                  className={view === n.id ? "is-active" : ""}
                  onClick={() => setView(n.id)}
                >
                  {n.label}
                </button>
              ))}
            </div>
          )}

          <div className="tr">
            <span className={`live-pill${live ? "" : " bad"}`} title="SSE connection to the bridge">
              <i />{live ? "live" : "reconnecting"}
            </span>
            <button className="mode" aria-label="Toggle theme" onClick={toggleTheme}>
              <svg className="moon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                <path d="M20 14.5A8 8 0 0 1 9.5 4 8 8 0 1 0 20 14.5z" />
              </svg>
              <svg className="sun" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                <path d="M12 16a4 4 0 1 0 0-8 4 4 0 0 0 0 8zM12 2v2M12 20v2M2 12h2M20 12h2M5 5l1.5 1.5M17.5 17.5L19 19M5 19l1.5-1.5M17.5 6.5L19 5" />
              </svg>
            </button>
          </div>
        </div>

        {/* views */}
        {surface === "cowork" ? (
          renderCoworkMain()
        ) : surface === "code" ? (
          renderCodeMain()
        ) : surface === "duet" ? (
          renderDuetMain()
        ) : view === "agents" ? (
          <section className="conversation" aria-label="conversation">
            <div className="agent-strip" aria-label="agents">
              {bots.map((bot) => (
                <button
                  key={bot.id}
                  className={`strip-avatar${bot.id === selectedId ? " is-active" : ""}`}
                  onClick={() => setSelectedId(bot.id)}
                  style={{ background: `linear-gradient(160deg, hsl(${hueOf(bot)} 62% 55%), hsl(${hueOf(bot)} 62% 30%))` }}
                  aria-label={bot.name}
                >
                  {initials(bot.name)}
                </button>
              ))}
            </div>

            {selectedBot ? (
              <>
                <div className="chat-head">
                  <span className="avatar" style={{ background: `linear-gradient(160deg, hsl(${hueOf(selectedBot)} 62% 55%), hsl(${hueOf(selectedBot)} 62% 30%))` }}>
                    {initials(selectedBot.name)}
                  </span>
                  <div style={{ minWidth: 0 }}>
                    <h1>{selectedBot.name}</h1>
                    <p>{selectedBot.engine === "echo" ? "scripted test bot" : selectedBot.provider === "auto" ? "provider: auto" : selectedBot.provider}{selectedBot.model ? ` · ${selectedBot.model}` : ""}</p>
                  </div>
                </div>

                <div className="rows">
                  {rows.length === 0 && !busy ? (
                    <div className="empty-view"><h3>Say hello to {selectedBot.name}</h3><p>Type a message below.</p></div>
                  ) : (
                    renderRows()
                  )}
                  {streamText !== "" && (
                    <div className="bubble assistant streaming" aria-label="agent is typing">
                      <span className="role">{selectedBot?.name ?? "agent"}</span>
                      {streamText}
                      <span className="stream-caret" aria-hidden="true" />
                    </div>
                  )}
                  {busy && streamText === "" && (
                    <div className="thinking-line" role="status" aria-label="agent is thinking">
                      <svg className="thinking-glyph" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true"><path d="M12 3v4M12 17v4M3 12h4M17 12h4M5.6 5.6l2.8 2.8M15.6 15.6l2.8 2.8M5.6 18.4l2.8-2.8M15.6 8.4l2.8-2.8" /></svg>
                      <span className="thinking-text">Thinking…</span>
                    </div>
                  )}
                  <div ref={rowsEndRef} />
                </div>

                {renderComposer("fleet")}
              </>
            ) : (
              <div className="hero">
                <div className="plan">Local <span>·</span> <b>Keel Fleet</b> <span>·</span> free</div>
                <h1 className="hero-title"><em>{greeting}.</em></h1>

                <form className="box" onSubmit={(e) => { e.preventDefault(); sendMessage(); }}>
                  <input
                    ref={composerRef}
                    type="text"
                    placeholder={bots.length ? "How can I help you today?" : "Create an agent to get started…"}
                    value={draft}
                    onChange={(e) => setDraft(e.target.value)}
                    onFocus={() => { if (!selectedId && bots[0]) setSelectedId(bots[0].id); }}
                    aria-label="Prompt"
                  />
                  <div className="bar">
                    <button type="button" className="model-chip" onClick={() => { setDrawerTab("engine"); setDrawerOpen(true); }} title="Open engine settings">
                      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" aria-hidden="true" style={{ width: 12, height: 12 }}>
                        <path d="M12 3v3M12 18v3M4.2 4.2l2.1 2.1M17.7 17.7l2.1 2.1M3 12h3M18 12h3M4.2 19.8l2.1-2.1M17.7 6.3l2.1-2.1" />
                        <circle cx="12" cy="12" r="4" />
                      </svg>
                      <span className="txt">{configuredCount > 0 ? "provider ready" : "no model configured"}</span>
                      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" aria-hidden="true" style={{ width: 11, height: 11 }}>
                        <path d="M6 9l6 6 6-6" />
                      </svg>
                    </button>
                    <button className={`send${busy ? " busy" : ""}`} type="submit" disabled={busy || !draft.trim()} aria-label="Send message">
                      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                        <path d="M12 19V5M5 12l7-7 7 7" />
                      </svg>
                    </button>
                  </div>
                </form>

                <span className="quick-label">QUICK START</span>
                <div className="quick-grid">
                  {QUICK_STARTS.map((q) => (
                    <button key={q.title} className="quick" onClick={() => useQuickStart(q.prompt)}>
                      <span className="quick-icon"><QuickIcon kind={q.icon} /></span>
                      <span>
                        <b>{q.title}</b>
                        <p>{q.prompt}</p>
                      </span>
                    </button>
                  ))}
                </div>
              </div>
            )}
          </section>
        ) : (
          <main className="workspace">
            <div className="workspace-inner">
              {view === "tasks" && (
                <>
                  <div className="tasks-head">
                    <h2>Tasks</h2>
                    <span className="hint" style={{ margin: 0, display: "inline-flex", alignItems: "center", gap: ".35rem" }}>
                      <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true"><path d="M9 6h6M9 12h6M9 18h6M6 6h.01M6 12h.01M6 18h.01" /></svg>
                      drag rows to set the work order — first runs first
                    </span>
                  </div>
                  <div className="task-new">
                    <input value={newTask} placeholder="New task title…" onChange={(e) => setNewTask(e.target.value)} onKeyDown={(e) => e.key === "Enter" && addTask()} aria-label="New task" />
                    <button className="btn primary" onClick={addTask}>Add</button>
                  </div>
                  <div style={{ marginBottom: ".6rem", display: "flex", gap: ".35rem" }}>
                    {(["active", "all"] as const).map((f) => (
                      <button key={f} className={`btn${taskFilter === f ? " primary" : ""}`} onClick={() => setTaskFilter(f)}>{f}</button>
                    ))}
                  </div>
                  {visibleTasks.length === 0 ? (
                    <div className="empty-view"><h3>No {taskFilter === "active" ? "active " : ""}tasks</h3><p>Add one above.</p></div>
                  ) : (
                    visibleTasks.map((t) => {
                      const editing = editingTaskId === t.id;
                      const done = t.status === "completed";
                      const dropCls = dropTarget && dropTarget.id === t.id
                        ? (dropTarget.before ? " drop-before" : " drop-after") : "";
                      return (
                        <div
                          key={t.id}
                          className={`task-row${done ? " is-done" : ""}${dropCls}`}
                          draggable={!editing}
                          onDragStart={() => onTaskDragStart(t.id)}
                          onDragOver={(e) => onTaskDragOver(e, t.id)}
                          onDragEnd={() => { setDragId(null); setDropTarget(null); }}
                          onDrop={() => onTaskDrop(t.id)}
                        >
                          <button className="drag-handle" draggable={false} title="Drag to reorder" aria-label="Drag to reorder">
                            <svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
                              <circle cx="9" cy="6" r="1.6" /><circle cx="9" cy="12" r="1.6" /><circle cx="9" cy="18" r="1.6" /><circle cx="15" cy="6" r="1.6" /><circle cx="15" cy="12" r="1.6" /><circle cx="15" cy="18" r="1.6" />
                            </svg>
                          </button>
                          <button
                            className={`task-check${done ? " is-done" : ""}`}
                            onClick={() => toggleTaskDone(t)}
                            aria-label={done ? "Mark as pending" : "Mark as done"}
                            title={done ? "Mark as pending" : "Mark as done"}
                          >
                            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                              <path d="M5 13l4 4 10-11" />
                            </svg>
                          </button>
                          {editing ? (
                            <input
                              className="task-edit"
                              autoFocus
                              value={editTitle}
                              onChange={(e) => setEditTitle(e.target.value)}
                              onBlur={() => saveTaskTitle(t)}
                              onKeyDown={(e) => {
                                if (e.key === "Enter") saveTaskTitle(t);
                                if (e.key === "Escape") setEditingTaskId(null);
                              }}
                              aria-label="Task title"
                            />
                          ) : (
                            <button className="task-title" onDoubleClick={() => { setEditingTaskId(t.id); setEditTitle(t.title); }} title={`${t.title} — double-click to edit`}>
                              {t.title}
                            </button>
                          )}
                          <span className={`chip ${t.status}`}>{t.status}</span>
                          <button className="icon-btn" onClick={() => moveTask(t, -1)} title="Move up" aria-label="Move up" disabled={false}>
                            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M6 15l6-6 6 6" /></svg>
                          </button>
                          <button className="icon-btn" onClick={() => moveTask(t, 1)} title="Move down" aria-label="Move down">
                            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M6 9l6 6 6-6" /></svg>
                          </button>
                          <button className="icon-btn" onClick={() => revertTask(t)} title="Revert to previous state" aria-label="Revert">
                            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M3 7v6h6" /><path d="M3 13a9 9 0 1 0 2.6-6.4L3 10" /></svg>
                          </button>
                          <button className="icon-btn danger" onClick={() => deleteTask(t)} title="Delete task" aria-label="Delete task">
                            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M4 7h16M10 11v6M14 11v6M6 7l1 13a2 2 0 0 0 2 2h6a2 2 0 0 0 2-2l1-13M9 7V5a2 2 0 0 1 2-2h2a2 2 0 0 1 2 2v2" /></svg>
                          </button>
                        </div>
                      );
                    })
                  )}
                </>
              )}

              {view === "library" && (
                <>
                  <h2>Library</h2>
                  {files.length === 0 ? (
                    <div className="empty-view"><h3>No files yet</h3><p>Agents save deliverables here.</p></div>
                  ) : (
                    files.map((f) => (
                      <div className="card" key={f.id}>
                        <span style={{ flex: 1, minWidth: 0 }}>
                          {f.name}
                          <span className="hint" style={{ margin: 0 }}> · {fmtBytes(f.size)}{f.bot_id ? ` · ${f.bot_id}` : ""}</span>
                        </span>
                        <a className="dl" href={`/api/bridge/library/${f.id}/download`} download={f.name}>Download</a>
                      </div>
                    ))
                  )}
                </>
              )}

              {view === "routines" && (
                <>
                  <h2>Routines</h2>
                  {routines.length === 0 ? (
                    <div className="empty-view"><h3>No routines yet</h3><p>Create them from the classic Fleet UI for now — full parity is on the roadmap.</p></div>
                  ) : (
                    routines.map((r) => (
                      <div className="card" key={r.id}>
                        <span style={{ flex: 1, minWidth: 0 }}>
                          {r.name}
                          <span className="hint" style={{ margin: 0 }}> · <code>{r.cron_expr}</code>{r.timezone ? ` ${r.timezone}` : ""}{r.last_run_status ? ` · last: ${r.last_run_status}` : ""}</span>
                        </span>
                        <button className="btn" onClick={() => runRoutine(r.id)}>Run now</button>
                      </div>
                    ))
                  )}
                </>
              )}
            </div>
          </main>
        )}
      </section>

      {/* ============ drawer ============ */}
      <aside className={`drawer${drawerOpen ? " open" : ""}`} aria-label="agent panel">
        <div className="dtabs" role="tablist">
          <button className={`dtab${drawerTab === "engine" ? " is-active" : ""}`} onClick={() => setDrawerTab("engine")} role="tab">Engine</button>
          <button className={`dtab${drawerTab === "notes" ? " is-active" : ""}`} onClick={() => setDrawerTab("notes")} role="tab">Notes</button>
        </div>

        {!selectedBot ? (
          <p className="hint">Select an agent to configure it.</p>
        ) : drawerTab === "engine" ? (
          <>
            <label className="field">
              <span>Provider</span>
              <select value={providerSel} onChange={(e) => setProviderSel(e.target.value)} aria-label="Provider">
                <option value="auto">auto (Keel chain)</option>
                {providers.map((p) => (
                  <option key={p.name} value={p.name}>
                    {p.name} {p.configured ? (p.session ? "⦿ configured · session" : "⦿ configured") : "— not configured"}
                  </option>
                ))}
              </select>
            </label>

            <div className="status-line">
              {providerSel === "auto" ? (
                configuredCount > 0
                  ? <span><span className="ok">● auto</span> — {configuredCount} provider(s) configured.</span>
                  : <span><span className="miss">● auto</span> — no providers configured; the agent cannot run.</span>
              ) : (providers.find((p) => p.name === providerSel)?.configured ? (
                <span><span className="ok">● configured</span>{providers.find((p) => p.name === providerSel)?.session ? " — session key (never stored)" : " — key present (not stored by Fleet)"}</span>
              ) : (
                <span><span className="miss">● not configured</span> — paste a key below, or set it in your shell.</span>
              ))}
            </div>

            <div className="field">
              <span>API key for this session (never written to disk; gone on restart)</span>
              <div className="key-row">
                <input
                  type="password"
                  value={keyInput}
                  autoComplete="off"
                  maxLength={512}
                  placeholder="paste key, then validate"
                  onChange={(e) => setKeyInput(e.target.value)}
                  onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); validateKey(); } }}
                  aria-label="Session provider key"
                />
                <button className="btn" disabled={keyBusy} onClick={validateKey}>{keyBusy ? "…" : "Validate & load models"}</button>
                <button className="btn" disabled={keyBusy} onClick={forgetKey} title="Forget the session key">Forget</button>
              </div>
              <div className="status-line" role="status">{keyStatus}</div>
            </div>

            <label className="field">
              <span>Model (optional)</span>
              <input list="engine-models" value={modelSel} onChange={(e) => setModelSel(e.target.value)} placeholder="e.g. openrouter/auto" maxLength={120} autoComplete="off" />
              <datalist id="engine-models">
                {modelList.map((m) => <option key={m} value={m} />)}
              </datalist>
            </label>

            <button className="btn primary" onClick={saveEngine}>Save engine</button>
            <p className="hint">Keys come from your shell env, or the box above for this session only. Fleet never writes keys to disk. No key? The agent replies with an inline explanation.</p>
          </>
        ) : (
          <>
            <label className="field">
              <span>Notes (up to 4096 bytes, private to this agent)</span>
              <textarea value={notes} maxLength={4096} onChange={(e) => setNotes(e.target.value)} placeholder="What should this agent remember?" />
            </label>
            <div className="hint">{notes.length}/4096</div>
            <button className="btn primary" onClick={saveNotes}>Save notes</button>
          </>
        )}
      </aside>

      {/* ============ create-agent pop-up ============ */}
      {/* ============ trust this workspace ============ */}
      {trustTarget && (
        <div className="trust-backdrop" role="dialog" aria-modal="true" aria-labelledby="trust-title">
          <div className="trust-modal">
            <h2 id="trust-title">Trust this workspace?</h2>
            <p className="trust-lede">Keel can read, write, and execute files in this folder. Only proceed if you trust it.</p>
            <div className="trust-path">{trustTarget.path}</div>
            <p className="trust-fine">Keel remembers this choice for this folder on this machine. You can revoke it anytime from the Projects page.</p>
            <div className="trust-actions">
              <button className="btn" onClick={() => { setTrustTarget(null); setPendingProjectId(null); }}>Cancel</button>
              <button className="btn dark" onClick={() => void trustWorkspace()}>Trust workspace</button>
            </div>
          </div>
        </div>
      )}

      {/* ============ new project (Cowork) ============ */}
      {projectModalOpen && (
        <div className="trust-backdrop" role="dialog" aria-modal="true" aria-labelledby="np-title" onClick={() => setProjectModalOpen(false)}>
          <div className="trust-modal" onClick={(e) => e.stopPropagation()}>
            <h2 id="np-title">New project</h2>
            <p className="trust-lede">Paste an absolute folder path. Keel reads the folder, never writes until you ask it to.</p>
            <form onSubmit={(e) => { e.preventDefault(); setProjectPathInput(modalPathInput); void addProject(); setProjectModalOpen(false); }}>
              <input
                className="field"
                autoFocus
                value={modalPathInput}
                onChange={(e) => setModalPathInput(e.target.value)}
                placeholder="C:\Users\you\my-app"
                aria-label="Folder path"
                spellCheck={false}
              />
              <div className="trust-actions">
                <button type="button" className="btn" onClick={() => setProjectModalOpen(false)}>Cancel</button>
                <button type="submit" className="btn dark" disabled={!modalPathInput.trim()}>Add project</button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* ============ new scheduled task (Cowork) ============ */}
      {routineModalOpen && (
        <div className="trust-backdrop" role="dialog" aria-modal="true" aria-labelledby="rt-title" onClick={() => setRoutineModalOpen(false)}>
          <div className="trust-modal wide" onClick={(e) => e.stopPropagation()}>
            <h2 id="rt-title">New scheduled task</h2>
            <form onSubmit={(e) => {
              e.preventDefault();
              const botId = firstAgentId();
              if (!botId) { say("Create an agent first — scheduled tasks run on an agent."); return; }
              if (!routineName.trim() || !routinePrompt.trim()) { say("Name and prompt are required."); return; }
              void (async () => {
                try {
                  await api("routines", {
                    method: "POST",
                    body: JSON.stringify({
                      name: routineName.trim(), prompt: routinePrompt.trim(),
                      cron_expr: routineCron.trim() || "0 8 * * *",
                      timezone: routineTz.trim() || "UTC",
                      bot_id: botId, enabled: true,
                    }),
                  });
                  await refreshRoutines();
                  setRoutineModalOpen(false);
                  say(`Scheduled “${routineName.trim()}”.`);
                } catch (err: any) { say(`Couldn't create task: ${err.message}`); }
              })();
            }}>
              <label className="field-label">Name
                <input className="field" autoFocus value={routineName} onChange={(e) => setRoutineName(e.target.value)} placeholder="Morning briefing" />
              </label>
              <label className="field-label">Prompt
                <textarea className="field" rows={3} value={routinePrompt} onChange={(e) => setRoutinePrompt(e.target.value)} placeholder="What should the agent do, every time?" />
              </label>
              <div className="routine-modal-row">
                <label className="field-label grow">Cron
                  <input className="field mono" value={routineCron} onChange={(e) => setRoutineCron(e.target.value)} placeholder="0 8 * * *" spellCheck={false} />
                </label>
                <label className="field-label">Timezone
                  <input className="field" value={routineTz} onChange={(e) => setRoutineTz(e.target.value)} placeholder="UTC" spellCheck={false} />
                </label>
              </div>
              <p className="trust-fine">Cron runs on this machine while Keel Fleet is running. Unattended runs need the agent to be allowed to act — standing policies or Autopilot mode.</p>
              <div className="trust-actions">
                <button type="button" className="btn" onClick={() => setRoutineModalOpen(false)}>Cancel</button>
                <button type="submit" className="btn dark">Create task</button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* ============ new artifact (Cowork) ============ */}
      {artifactAskOpen && (
        <div className="trust-backdrop" role="dialog" aria-modal="true" aria-labelledby="na-title" onClick={() => setArtifactAskOpen(false)}>
          <div className="trust-modal" onClick={(e) => e.stopPropagation()}>
            <h2 id="na-title">New artifact</h2>
            <p className="trust-lede">Describe what you want. Your agent drafts it and saves it to the Library — it shows up here.</p>
            <input
              className="field"
              autoFocus
              id="artifact-ask"
              placeholder="A one-page brief on…"
              aria-label="Artifact description"
              onKeyDown={(e) => {
                if (e.key === "Enter") {
                  const v = (e.target as HTMLInputElement).value.trim();
                  if (v) { void runPrompt(`Create an artifact for me: ${v}. Save it to the Fleet Library when it's ready.`); setArtifactAskOpen(false); setCowView("chat"); }
                }
              }}
            />
            <div className="trust-actions">
              <button className="btn" onClick={() => setArtifactAskOpen(false)}>Cancel</button>
              <button className="btn dark" onClick={() => {
                const el = document.getElementById("artifact-ask") as HTMLInputElement | null;
                const v = el?.value.trim();
                if (v) { void runPrompt(`Create an artifact for me: ${v}. Save it to the Fleet Library when it's ready.`); setArtifactAskOpen(false); setCowView("chat"); }
              }}>Create</button>
            </div>
          </div>
        </div>
      )}

      {/* ============ artifact preview (Cowork) ============ */}
      {artifactPreview && (
        <div className="trust-backdrop" role="dialog" aria-modal="true" aria-labelledby="ap-title" onClick={() => setArtifactPreview(null)}>
          <div className="artifact-preview" onClick={(e) => e.stopPropagation()}>
            <div className="artifact-preview-head">
              <div className="pane-title">
                <h2 id="ap-title">{artifactPreview.name}</h2>
                <p>{fmtBytes(artifactPreview.size)} · {fileKindLabel(artifactPreview.mime, artifactPreview.name)} · {timeAgo((artifactPreview as any).created_at ?? "")}</p>
              </div>
              <div className="artifact-preview-actions">
                <a className="btn" href={`/api/bridge/library/${artifactPreview.id}/download`} download={artifactPreview.name}>Download</a>
                <button className="btn" onClick={() => setArtifactPreview(null)}>Close</button>
              </div>
            </div>
            <iframe className="artifact-preview-frame" src={`/api/bridge/library/${artifactPreview.id}/preview`} title={`Preview of ${artifactPreview.name}`} />
          </div>
        </div>
      )}

      {modalOpen && (
        <div className="modal-veil" role="dialog" aria-modal="true" aria-label="Create agent" onClick={() => setModalOpen(false)}>
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <div className="modal-head">
              <div className="modal-icon" aria-hidden="true">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" width="20" height="20">
                  <path d="M12 3l1.9 5.8a2 2 0 0 0 1.3 1.3L21 12l-5.8 1.9a2 2 0 0 0-1.3 1.3L12 21l-1.9-5.8a2 2 0 0 0-1.3-1.3L3 12l5.8-1.9a2 2 0 0 0 1.3-1.3L12 3z" />
                </svg>
              </div>
              <div>
                <h3>New agent</h3>
                <p>Its own persona, memory and provider — yours alone</p>
              </div>
            </div>

            <div className="agent-preview" aria-hidden="true">
              <div className="preview-avatar" style={{ background: `linear-gradient(160deg, hsl(${newHue} 68% 58%), hsl(${newHue} 68% 28%))` }}>
                {(newName.trim()[0] || "?").toUpperCase()}
              </div>
              <div className="preview-meta">
                <b>{newName.trim() || "Unnamed agent"}</b>
                <span>{newRole.trim() || "no role assigned"}</span>
              </div>
            </div>
            <input className="hue-slider" type="range" min={0} max={359} value={newHue} onChange={(e) => setNewHue(Number(e.target.value))} aria-label="Agent color hue" />

            <label className="field">
              <span>Name</span>
              <input autoFocus value={newName} maxLength={48} placeholder="e.g. Scout" onChange={(e) => { setNewName(e.target.value); setNameError(""); }} onKeyDown={(e) => e.key === "Enter" && createAgent()} aria-invalid={!!nameError} />
            </label>
            <label className="field">
              <span>Role</span>
              <input value={newRole} maxLength={96} placeholder="e.g. research analyst" onChange={(e) => setNewRole(e.target.value)} onKeyDown={(e) => e.key === "Enter" && createAgent()} />
            </label>

            <div className="field">
              <span>Engine</span>
              <div className="seg-radio" role="radiogroup" aria-label="Engine">
                <label>
                  <input type="radio" name="engine" value="provider" checked={newEngine === "provider"} onChange={() => setNewEngine("provider")} />
                  <div className="seg-option"><b>Provider</b><span>a real model thinks here</span></div>
                </label>
                <label>
                  <input type="radio" name="engine" value="echo" checked={newEngine === "echo"} onChange={() => setNewEngine("echo")} />
                  <div className="seg-option"><b>Echo</b><span>scripted — for wiring tests</span></div>
                </label>
              </div>
            </div>

            {nameError && <div className="field-error" role="alert">{nameError}</div>}

            <div style={{ display: "flex", justifyContent: "flex-end", gap: ".55rem", marginTop: ".5rem" }}>
              <button className="btn" onClick={() => setModalOpen(false)}>Cancel</button>
              <button className="btn primary" onClick={createAgent}>Create agent</button>
            </div>
          </div>
        </div>
      )}

      {toast && (
        <div className="toast" role="status">
          <span>{toast}</span>
          {toastAction && (
            <button className="toast-action" onClick={() => { toastAction.run(); setToast(null); setToastAction(null); }}>
              {toastAction.label}
            </button>
          )}
        </div>
      )}
    </div>
  );
}
