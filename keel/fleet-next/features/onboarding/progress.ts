"use client";

// Resumable onboarding state. Only UI preferences live here; credentials,
// agent runs and file data always come from the bridge. Every key is namespaced
// with `keel-onboarding:` so Settings can restart the flow without discarding
// the checklist the shell shows in the sidebar.

import { useEffect, useState } from "react";

export const STEP_IDS = [
  "welcome",
  "local",
  "provider",
  "workspace",
  "permission",
  "capabilities",
  "channels",
  "tour",
] as const;

export type StepId = (typeof STEP_IDS)[number];

export const ITEM_IDS = [
  "surface",
  "provider",
  "workspace",
  "permission",
  "capabilities",
  "channels",
  "tour",
] as const;

export type ItemId = (typeof ITEM_IDS)[number];
export type ItemStatus = "pending" | "done" | "deferred";
export type Checklist = Record<ItemId, ItemStatus>;
export type Mode = "plan" | "build" | "acceptEdits" | "autopilot";

interface ChecklistItem {
  id: ItemId;
  label: string;
  required: boolean;
  /** Where the shell can send the user to finish this item. */
  target: "cowork" | "code" | "settings" | "capabilities" | "channels";
  hint: string;
}

export const CHECKLIST_ITEMS: ChecklistItem[] = [
  {
    id: "surface", label: "Pick a starting surface", required: true, target: "cowork",
    hint: "Start with Cowork, Code or Fleet from the welcome screen.",
  },
  {
    id: "provider", label: "Connect a provider", required: true, target: "settings",
    hint: "Settings → Providers. You can also keep using Keel with a key you add later.",
  },
  {
    id: "workspace", label: "Choose a workspace", required: true, target: "code",
    hint: "Add a local folder in Code and make an explicit trust decision.",
  },
  {
    id: "permission", label: "Choose a permission mode", required: true, target: "settings",
    hint: "The composer's mode control and Settings → Permissions explain each mode.",
  },
  {
    id: "capabilities", label: "Review skills & MCP (optional)", required: false, target: "capabilities",
    hint: "Settings → Capabilities shows installed skills and third-party MCP servers.",
  },
  {
    id: "channels", label: "Voice & channels (optional)", required: false, target: "channels",
    hint: "No external messaging is configured in this build.",
  },
  {
    id: "tour", label: "Take the tour (optional)", required: false, target: "cowork",
    hint: "Help → Take the tour replays the guided walkthrough.",
  },
];

const K = {
  step: "keel-onboarding:step",
  checklist: "keel-onboarding:checklist",
  change: "keel-onboarding-change",
} as const;

export function freshChecklist(): Checklist {
  const out = {} as Checklist;
  for (const id of ITEM_IDS) out[id] = "pending";
  return out;
}

function read<T>(key: string): unknown {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.localStorage.getItem(key);
    return raw === null ? null : JSON.parse(raw);
  } catch {
    return null;
  }
}

function write(key: string, value: unknown): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(key, JSON.stringify(value));
    window.dispatchEvent(new Event(K.change));
  } catch {
    /* storage may be unavailable (private mode); the flow still works in-memory */
  }
}

export function readChecklist(): Checklist {
  const raw = read(K.checklist);
  const base = freshChecklist();
  if (!raw || typeof raw !== "object") return base;
  const obj = raw as Record<string, unknown>;
  for (const id of ITEM_IDS) {
    const v = obj[id];
    if (v === "done" || v === "deferred") base[id] = v;
  }
  return base;
}

/** Merge status updates for one or more items and notify mounted listeners. */
export function updateChecklist(patch: Partial<Checklist>): Checklist {
  const next = { ...readChecklist(), ...patch };
  write(K.checklist, next);
  return next;
}

export function readStep(): StepId {
  const raw = read(K.step);
  return typeof raw === "string" && (STEP_IDS as readonly string[]).includes(raw)
    ? (raw as StepId)
    : "welcome";
}

export function writeStep(step: StepId): void {
  write(K.step, step);
}

/** Point the resumed flow at a specific step (used by "Take the tour"). */
export function restartAtStep(step: StepId): void {
  writeStep(step);
}

/** The mode the existing composer reads at startup; never invent modes. */
export function readMode(): Mode | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.localStorage.getItem("keel-mode");
    return raw === "plan" || raw === "build" || raw === "acceptEdits" || raw === "autopilot"
      ? raw
      : null;
  } catch {
    return null;
  }
}

export function writeMode(mode: Mode): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem("keel-mode", mode);
  } catch {
    /* ignore */
  }
}

/** Local, in-memory mirror of the persisted checklist for the shell + wizard. */
export function useChecklist(): Checklist {
  // Deterministic first render: localStorage is read only AFTER mount so the
  // server HTML and the first client render agree (React #418 fix).
  const [list, setList] = useState<Checklist>(() => freshChecklist());
  useEffect(() => {
    const sync = () => setList(readChecklist());
    sync();
    window.addEventListener(K.change, sync);
    window.addEventListener("storage", sync);
    return () => {
      window.removeEventListener(K.change, sync);
      window.removeEventListener("storage", sync);
    };
  }, []);
  return list;
}

export function requiredDone(list: Checklist): number {
  return CHECKLIST_ITEMS.filter((i) => i.required && list[i.id] === "done").length;
}

export function requiredTotal(): number {
  return CHECKLIST_ITEMS.filter((i) => i.required).length;
}
