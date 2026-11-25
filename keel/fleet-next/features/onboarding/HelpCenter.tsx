"use client";

// Contextual help / troubleshooting. Every status shown here is read from the
// local bridge at the moment the dialog opens; every action either re-reads
// that bridge or navigates to a real destination. Nothing claims a connection
// that was not observed and nothing offers to "fix" a state the renderer does
// not own (starting the bridge, granting trust or storing a key).

import React, { useCallback, useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { bridge, errMessage, isBridgeUnavailable } from "@/lib/api";
import { Badge, Button, IconButton } from "@/components/ui";
import { Icon, type IconName } from "@/components/icons";
import { useApp } from "@/lib/state";
import { restartAtStep } from "./progress";
import s from "./onboarding.module.css";

export type HelpDestination = "cowork" | "code" | "duet" | "fleet" | "capabilities" | "settings";
export type HelpSection = "providers" | "credentials" | "permissions" | "trust" | "diagnostics";

export interface HelpCenterProps {
  open: boolean;
  onClose: () => void;
  onNavigate: (d: HelpDestination) => void;
}

interface ProviderRow { name?: string; id?: string; configured?: boolean; connected?: boolean }
interface ProjectRow { id?: string; path?: string; name?: string; trusted?: boolean | number }

interface ProbeState {
  loading: boolean;
  bridge: "checking" | "online" | "unavailable" | "error";
  detail: string;
  providerTotal: number;
  configured: number;
  projectTotal: number;
  untrusted: number;
}

const EMPTY_PROBE: ProbeState = {
  loading: false, bridge: "checking", detail: "",
  providerTotal: 0, configured: 0, projectTotal: 0, untrusted: 0,
};

function rows<T>(payload: unknown, key: string): T[] {
  if (Array.isArray(payload)) return payload as T[];
  if (payload && typeof payload === "object") {
    const found = (payload as Record<string, unknown>)[key];
    if (Array.isArray(found)) return found as T[];
  }
  return [];
}

function isConfigured(p: ProviderRow): boolean {
  return Boolean((p as { configured?: unknown }).configured) || Boolean((p as { connected?: unknown }).connected);
}

function isTrusted(p: ProjectRow): boolean {
  return p.trusted === true || p.trusted === 1;
}

export default function HelpCenter({ open, onClose, onNavigate }: HelpCenterProps) {
  const { completeOnboarding, restartOnboarding } = useApp();
  const [probeState, setProbeState] = useState<ProbeState>(EMPTY_PROBE);
  const panelRef = useRef<HTMLDivElement>(null);
  const closeRef = useRef(onClose);

  useEffect(() => { closeRef.current = onClose; }, [onClose]);

  // One real read of both registries per open. No cached or invented status.
  const probe = useCallback(async () => {
    setProbeState((prev) => ({ ...prev, loading: true, detail: "" }));
    const [providerResult, projectResult] = await Promise.allSettled([
      bridge.providers(), bridge.projects(),
    ]);

    let state: ProbeState["bridge"] = "online";
    let detail = "The local bridge answered both setup reads.";
    let providerRows: ProviderRow[] = [];
    let projectRows: ProjectRow[] = [];

    if (providerResult.status === "rejected") {
      state = isBridgeUnavailable(providerResult.reason) ? "unavailable" : "error";
      detail = errMessage(providerResult.reason);
    } else {
      providerRows = rows<ProviderRow>(providerResult.value, "providers");
    }
    if (projectResult.status === "rejected") {
      if (state === "online") {
        state = isBridgeUnavailable(projectResult.reason) ? "unavailable" : "error";
        detail = errMessage(projectResult.reason);
      }
    } else {
      projectRows = rows<ProjectRow>(projectResult.value, "projects");
    }

    setProbeState({
      loading: false, bridge: state, detail,
      providerTotal: providerRows.length,
      configured: providerRows.filter(isConfigured).length,
      projectTotal: projectRows.length,
      untrusted: projectRows.filter((p) => !isTrusted(p)).length,
    });
  }, []);

  useEffect(() => {
    if (open) void probe();
  }, [open, probe]);

  // Navigate for real. The Settings module reads `#settings-<id>` on mount and
  // on hashchange, so setting the hash before navigating lands on the exact
  // section. Leaving setup here is the same decision as "Close setup".
  const navigate = useCallback((d: HelpDestination, section?: HelpSection) => {
    if (section) {
      const hash = `#settings-${section}`;
      try { window.history.replaceState(null, "", hash); } catch { window.location.hash = hash; }
      window.dispatchEvent(new Event("hashchange"));
    }
    completeOnboarding();
    onNavigate(d);
    closeRef.current();
  }, [completeOnboarding, onNavigate]);

  const replayTour = useCallback(() => {
    restartAtStep("tour");
    restartOnboarding();
    closeRef.current();
  }, [restartOnboarding]);

  // Escape and Tab belong to this dialog while it is open. Listening on the
  // window in capture phase keeps the wizard's document-level handler from
  // also closing setup when the user dismisses help.
  useEffect(() => {
    if (!open) return;
    const previous = document.activeElement as HTMLElement | null;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.preventDefault();
        e.stopImmediatePropagation();
        closeRef.current();
        return;
      }
      if (e.key !== "Tab") return;
      const root = panelRef.current;
      if (!root) return;
      const items = Array.from(root.querySelectorAll<HTMLElement>(
        'button:not([disabled]), [href], input:not([disabled]), [tabindex]:not([tabindex="-1"])',
      ));
      if (!items.length) { e.preventDefault(); root.focus(); return; }
      const first = items[0], last = items[items.length - 1];
      const active = document.activeElement as HTMLElement | null;
      if (!root.contains(active)) { e.preventDefault(); (e.shiftKey ? last : first).focus(); }
      else if (e.shiftKey && active === first) { e.preventDefault(); last.focus(); }
      else if (!e.shiftKey && active === last) { e.preventDefault(); first.focus(); }
    };
    window.addEventListener("keydown", onKey, true);
    const timer = window.setTimeout(() => {
      (panelRef.current?.querySelector<HTMLElement>("button") ?? panelRef.current)?.focus();
    }, 0);
    return () => {
      window.clearTimeout(timer);
      window.removeEventListener("keydown", onKey, true);
      if (previous && document.contains(previous)) previous.focus();
    };
  }, [open]);

  if (!open || typeof document === "undefined") return null;

  const bridgeTone = probeState.bridge === "online" ? "success"
    : probeState.bridge === "checking" ? "warning" : "danger";
  const bridgeLabel = probeState.bridge === "online" ? "Bridge answered"
    : probeState.bridge === "checking" ? "Checking" : probeState.bridge === "unavailable" ? "Bridge unavailable" : "Probe failed";
  const readFailed = probeState.bridge !== "online" && probeState.bridge !== "checking";

  const bridgeStatus = probeState.bridge === "unavailable"
    ? `Bridge read failed: ${probeState.detail || "bridge_unavailable"}`
    : probeState.bridge === "error"
      ? `Bridge read failed: ${probeState.detail || "unknown error"}`
      : probeState.bridge === "checking"
        ? "Reading bridge status…"
        : "Both setup reads reached the local bridge.";

  const providerStatus = readFailed || probeState.loading && probeState.bridge !== "online"
    ? "Provider state could not be read; do not assume a key is working."
    : probeState.providerTotal === 0
      ? "The bridge reports no providers."
      : `${probeState.configured} of ${probeState.providerTotal} providers report a configured key.`;

  const workspaceStatus = readFailed || probeState.loading && probeState.bridge !== "online"
    ? "Workspace trust could not be read; nothing is trusted by this page."
    : probeState.projectTotal === 0
      ? "No local projects are registered yet."
      : probeState.untrusted === 0
        ? `All ${probeState.projectTotal} registered projects are trusted.`
        : `${probeState.untrusted} of ${probeState.projectTotal} registered projects are still untrusted.`;

  const cards: Array<{
    id: string; icon: IconName; title: string; status: string; body: React.ReactNode;
    actions: Array<{ label: string; icon: IconName; run: () => void }>;
  }> = [
    {
      id: "bridge", icon: "link", title: "Bridge is unavailable", status: bridgeStatus,
      body: (
        <>
          The React UI reaches Keel&apos;s Python runtime only through the same-origin <code>/api/bridge</code> proxy.
          The proxy returns HTTP 502 <code>bridge_unavailable</code> when the bridge is not running, or when
          <code> KEEL_BRIDGE_URL</code> / <code>KEEL_BRIDGE_TOKEN</code> are not set on the Next.js server.
          No prompt, provider verification or trust decision can succeed in that state. This page cannot start a bridge,
          edit server environment variables or invent a token: start <code>keel fleet</code> in a terminal with a matching
          token, then use re-check to read the bridge again.
        </>
      ),
      actions: [
        { label: "Re-check connection", icon: "refresh", run: () => { void probe(); } },
        { label: "Open system diagnostics", icon: "settings", run: () => navigate("settings", "diagnostics") },
      ],
    },
    {
      id: "provider", icon: "spark", title: "No provider is configured", status: providerStatus,
      body: (
        <>
          Keel needs a provider key to answer. In setup, <b>Verify &amp; use for this session</b> calls
          <code> providers/credential</code> and fetches the provider&apos;s live model list; the key then lives in bridge
          process memory only. Saving is a separate step that writes an encrypted key to <code>~/.keel/settings.json</code>
          on this machine, and only a four-character hint is returned to the UI. The offline catalogue in setup is
          browsing information, not a connection test. No Keel account or paid plan is required.
        </>
      ),
      actions: [
        { label: "Open provider settings", icon: "spark", run: () => navigate("settings", "providers") },
        { label: "Open saved credentials", icon: "shield", run: () => navigate("settings", "credentials") },
      ],
    },
    {
      id: "workspace", icon: "folder", title: "Workspace is not trusted", status: workspaceStatus,
      body: (
        <>
          Code requires an explicit, per-project trust decision before it reads or writes files. Trust grants read,
          write and terminal execution starting inside that folder; it is <b>not a sandbox</b>, because a command itself
          can reach other paths. Keel never trusts a folder automatically. A trust grant can be revoked in Code or in
          Settings → Workspace trust, and this help page cannot grant or revoke one for you.
        </>
      ),
      actions: [
        { label: "Open Code workspace", icon: "code", run: () => navigate("code") },
        { label: "Open workspace trust", icon: "shield", run: () => navigate("settings", "trust") },
      ],
    },
  ];

  // Portal to body: the sidebar creates a stacking context, which would trap
  // this overlay below the wizard's own z-index and swallow every click.
  return createPortal(
    <div className={s.helpOverlay} onMouseDown={(e) => { if (e.target === e.currentTarget) closeRef.current(); }}>
      <div
        ref={panelRef}
        className={s.helpDialog}
        role="dialog"
        aria-modal="true"
        aria-labelledby="keel-help-title"
        tabIndex={-1}
      >
        <header className={s.helpHead}>
          <div className={s.helpBrand}>
            <Icon name="info" size={18} />
            <h2 id="keel-help-title">Help &amp; troubleshooting</h2>
          </div>
          <IconButton label="Close help" onClick={() => closeRef.current()}><Icon name="close" size={16} /></IconButton>
        </header>
        <div className={s.helpBody}>
          <p className={s.helpLead}>
            Three setup states explain most &ldquo;Keel isn&apos;t doing anything&rdquo; reports. The status lines below are
            read from the bridge when you open this page — they are not cached badges.
          </p>
          <div className={s.helpProbe} role="status">
            <Badge tone={bridgeTone}>{bridgeLabel}</Badge>
            <span>{probeState.loading ? "Reading bridge…" : probeState.detail || "No probe detail available."}</span>
          </div>

          {cards.map((card) => (
            <section key={card.id} className={s.helpCard} aria-label={card.title}>
              <div className={s.helpCardHead}>
                <Icon name={card.icon} size={17} />
                <h3>{card.title}</h3>
              </div>
              <p className={s.helpStatus}>{card.status}</p>
              <p className={s.helpCardBody}>{card.body}</p>
              <div className={s.helpActions}>
                {card.actions.map((action) => (
                  <Button key={action.label} size="sm" onClick={action.run}>
                    <Icon name={action.icon} size={14} /> {action.label}
                  </Button>
                ))}
              </div>
            </section>
          ))}

          <div className={s.helpFooter}>
            <p className={s.helpNote}>
              Every route above opens a real surface. Nothing here starts an agent, grants trust, writes a key or changes
              a server environment variable.
            </p>
            <Button size="sm" variant="ghost" onClick={replayTour}>
              <Icon name="play" size={14} /> Replay the tour
            </Button>
          </div>
        </div>
      </div>
    </div>,
    document.body,
  );
}
