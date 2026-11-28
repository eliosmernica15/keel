"use client";

// Settings navigation and functional preference panels. Unsupported controls
// stay out of the UI; General links to the settings this build actually provides.

import React, { useEffect, useMemo, useState } from "react";
import { Button, Card, EmptyState } from "@/components/ui";
import { Icon } from "@/components/icons";
import { bridge } from "@/lib/api";
import { useApp } from "@/lib/state";
import s from "./settings.module.css";
import { PanelState, SETTINGS_SECTIONS, useBridgeData, type SectionId } from "./settingsShared";
import { AgentModelsPanel, CredentialsPanel, ProvidersPanel } from "./ProvidersSettings";
import { AccessibilityPanel, AppearancePanel, ResetPanel } from "./PreferencesSettings";
import { DiagnosticsPanel, PrivacyPanel, UpdatesPanel } from "./SystemSettings";

const CATEGORY_ORDER = ["SETTINGS", "THIS COMPUTER", "CUSTOMIZE"] as const;

export default function Settings({ onClose }: { onClose: () => void }) {
  const { notify, setSurface } = useApp() as { notify: (message: string, kind?: "error" | "warning" | "info" | "success") => void; setSurface: (surface: "cowork" | "code" | "duet" | "fleet") => void };
  const [active, setActive] = useState<SectionId>("general");
  const [search, setSearch] = useState("");

  useEffect(() => {
    const applyHash = () => {
      const id = window.location.hash.replace(/^#settings-/, "");
      if (SETTINGS_SECTIONS.some((section) => section.id === id)) setActive(id as SectionId);
    };
    applyHash();
    window.addEventListener("hashchange", applyHash);
    return () => window.removeEventListener("hashchange", applyHash);
  }, []);

  const matches = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return SETTINGS_SECTIONS;
    return SETTINGS_SECTIONS.filter((section) =>
      [section.title, section.category, section.description, section.keywords]
        .join(" ").toLowerCase().includes(q));
  }, [search]);

  useEffect(() => {
    if (matches.length > 0 && !matches.some((section) => section.id === active)) {
      setActive(matches[0].id);
    }
  }, [matches, active]);

  const current = SETTINGS_SECTIONS.find((section) => section.id === active) ?? SETTINGS_SECTIONS[0];

  function select(id: SectionId) {
    setActive(id);
    try { window.history.replaceState(null, "", `#settings-${id}`); } catch { /* ignore */ }
  }

  function renderSection(id: SectionId) {
    switch (id) {
      case "providers": return <ProvidersPanel />;
      case "usage": return <UsagePanel />;
      case "appearance": return <AppearancePanel />;
      case "accessibility": return <AccessibilityPanel />;
      case "reset": return <ResetPanel />;
      case "privacy": return <PrivacyPanel />;
      case "import-export": return <StubPanel title="Import & export" note="Import and export routes are not exposed by this bridge build." />;
      case "keel-code": return <StubPanel title="Keel Code" note="Keel Code settings are managed on the Code surface." />;
      case "keel-desktop": return <StubPanel title="Keel Desktop" note="Keel Desktop is a separate application; its settings live in the desktop shell." />;
      case "policies": return <PoliciesPanel notify={notify} />;
      case "admin": return <AdminPanel notify={notify} onOpenProjects={() => setSurface("code")} />;
      case "system": return (
        <>
          <DiagnosticsPanel />
          <UpdatesPanel />
        </>
      );
      case "developer": return <StubPanel title="Developer" note="Developer options are not exposed in this build." />;
      case "skills": return <StubPanel title="Skills" note="Skills are managed on the Capabilities surface." />;
      case "commands": return <StubPanel title="Commands" note="Slash commands are listed in the command palette." />;
      case "workflows": return <StubPanel title="Workflows" note="Workflows are managed on the Fleet surface." />;
      case "mcp-servers": return <StubPanel title="MCP Servers" note="MCP server connections are managed on the Capabilities surface." />;
      case "plugins": return <StubPanel title="Plugins" note="Plugins are not supported in this build." />;
    }
  }

  const isGeneral = active === "general";

  return (
    <div className={s.settings}>
      <aside className={s.nav} aria-label="Settings navigation">
        <div className={s.searchWrap}>
          <Icon name="search" size={14} className={s.searchIcon} />
          <input
            className={s.searchInput}
            type="search"
            aria-label="Search settings"
            placeholder="Search settings"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>
        {matches.length === 0 ? (
          <p className={s.noMatches}>No settings match “{search}”.</p>
        ) : (
          <>
            {CATEGORY_ORDER.map((category) => {
              const items = matches.filter((section) => section.category === category);
              if (items.length === 0) return null;
              return (
                <section className={s.navGroup} key={category} aria-label={category}>
                  <div className={s.navGroupLabel}>{category}</div>
                  <ul>
                    {items.map((section) => (
                      <li key={section.id}>
                        <button
                          type="button"
                          className={`${s.navItem} ${active === section.id ? s.navItemActive : ""}`}
                          aria-current={active === section.id ? "page" : undefined}
                          onClick={() => select(section.id)}
                        >
                          <Icon name={section.icon} size={15} />
                          <span>{section.title}</span>
                        </button>
                      </li>
                    ))}
                  </ul>
                </section>
              );
            })}
            <button type="button" className={s.navClose} onClick={onClose}>
              <Icon name="close" size={15} /> Close settings
            </button>
          </>
        )}
      </aside>

      <main className={s.main}>
        <header className={s.header}>
          <h1>{current.title}</h1>
          <p>{current.description}</p>
        </header>
        <div className={s.content} aria-label={current.title}>
          {isGeneral && (
            <>
              <AccountCard />
              <SectionHeader label="LOCAL PREFERENCES" title="Make Keel yours" />
              <Card className={s.settingCard}>
                <h3>Appearance, accessibility and reset controls</h3>
                <p className={s.cardDesc}>Appearance and layout preferences stay on this device. Motion and keyboard behavior follow your operating system.</p>
                <div className={s.controls}>
                  <Button size="sm" variant="secondary" onClick={() => select("appearance")}>Appearance</Button>
                  <Button size="sm" variant="secondary" onClick={() => select("accessibility")}>Accessibility</Button>
                  <Button size="sm" variant="ghost" onClick={() => select("reset")}>Reset preferences</Button>
                </div>
              </Card>
            </>
          )}
          {!isGeneral && matches.length > 0 && (
            <>
              <SectionHeader label={current.category} title={current.title} />
              {renderSection(current.id)}
            </>
          )}
          {matches.length === 0 && !isGeneral && (
            <EmptyState icon={<Icon name="search" />} title="No matching settings" description="Try another term, or clear the search to see every category." />
          )}
        </div>
      </main>
    </div>
  );
}

// "You · this device" account card shown at the top of General settings.
function AccountCard() {
  return (
    <Card className={s.accountCard}>
      <div className={s.accountIcon}>
        <Icon name="user" size={20} />
      </div>
      <div className={s.accountBody}>
        <h2 className={s.accountName}>You · local</h2>
        <p className={s.accountSub}>No account. This machine is the account.</p>
      </div>
    </Card>
  );
}

function SectionHeader({ label, title }: { label: string; title: string }) {
  return (
    <div className={s.sectionHeader}>
      <span className={s.sectionLabel}>{label}</span>
      <h2 className={s.sectionTitle}>{title}</h2>
    </div>
  );
}

function StubPanel({ title, note }: { title: string; note: string }) {
  return (
    <Card className={s.settingCard}>
      <div className={s.settingHead}>
        <h3 className={s.cardTitle}>{title}</h3>
      </div>
      <p className={s.cardDesc}>{note}</p>
      <p className={s.muted}>No controls are rendered here until the bridge exposes a route for this section.</p>
    </Card>
  );
}

// Policies — permission mode (local preference).
function PoliciesPanel({ notify }: { notify: (message: string, kind?: "error" | "warning" | "info" | "success") => void }) {
  type PermissionMode = "build" | "acceptEdits" | "plan" | "autopilot";
  const [mode, setMode] = useState<PermissionMode>("build");
  const MODES: Array<{ value: PermissionMode; label: string }> = [
    { value: "build", label: "Build" },
    { value: "acceptEdits", label: "Accept edits" },
    { value: "plan", label: "Plan" },
    { value: "autopilot", label: "Autopilot" },
  ];
  useEffect(() => {
    try {
      const saved = localStorage.getItem("keel-mode");
      if (saved === "build" || saved === "acceptEdits" || saved === "plan" || saved === "autopilot") setMode(saved);
    } catch { /* local preferences remain optional */ }
  }, []);
  return (
    <Card className={s.settingCard}>
      <div className={s.settingHead}>
        <h3 className={s.cardTitle}>Permission mode</h3>
      </div>
      <p className={s.cardDesc}>Choose how much the agent may do before asking you. A local preference; the bridge retains its own allow/ask/deny checks.</p>
      <div className={s.controls}>
        {MODES.map((m) => (
          <button
            key={m.value}
            type="button"
            className={`${s.modeChip} ${mode === m.value ? s.modeChipActive : ""}`}
            onClick={() => {
              setMode(m.value);
              try { localStorage.setItem("keel-mode", m.value); } catch { /* local preferences remain optional */ }
              notify(`Permission mode set to ${m.label}.`, "success");
            }}
          >
            {m.label}
          </button>
        ))}
      </div>
    </Card>
  );
}

// Admin — workspace trust placeholder.
function AdminPanel({ notify, onOpenProjects }: { notify: (message: string, kind?: "error" | "warning" | "info" | "success") => void; onOpenProjects: () => void }) {
  return (
    <Card className={s.settingCard}>
      <div className={s.settingHead}>
        <h3 className={s.cardTitle}>Workspace trust</h3>
      </div>
      <p className={s.cardDesc}>Keel only reads and writes folders you have explicitly trusted. Trust is stored by the bridge and can be revoked here.</p>
      <div className={s.controls}>
        <Button size="sm" onClick={() => {
          onOpenProjects();
          notify("Open the project list in Code to manage folder trust.", "info");
        }}>Manage trusted folders</Button>
      </div>
    </Card>
  );
}

// Usage — totals come from the bridge, and unsupported metrics stay explicit.
function UsagePanel() {
  const query = useBridgeData(() => bridge.usage());
  return (
    <PanelState query={query}>
      {({ usage }) => {
        const value = (amount: number | undefined) =>
          typeof amount === "number" && Number.isFinite(amount) ? amount.toLocaleString() : "Not reported";
        return (
          <Card className={s.settingCard}>
            <div className={s.settingHead}>
              <h3 className={s.cardTitle}>Usage reported by the bridge</h3>
              <Button size="sm" variant="secondary" onClick={query.reload}>Refresh</Button>
            </div>
            <p className={s.cardDesc}>Aggregate token totals across this Keel install. They are not a per-project bill.</p>
            <div className={s.controls}>
              <dl className={s.usageGrid}>
                <div><dt>Input tokens</dt><dd>{value(usage?.input_tokens)}</dd></div>
                <div><dt>Output tokens</dt><dd>{value(usage?.output_tokens)}</dd></div>
                <div><dt>Cache read tokens</dt><dd>{value(usage?.cache_read_input_tokens)}</dd></div>
                <div><dt>Cache creation tokens</dt><dd>{value(usage?.cache_creation_input_tokens)}</dd></div>
                <div><dt>Cost</dt><dd>{value(usage?.cost)}</dd></div>
              </dl>
              <p className={s.muted}>Cost is shown only when the provider reports it. Keel does not estimate a price from token counts.</p>
            </div>
          </Card>
        );
      }}
    </PanelState>
  );
}


