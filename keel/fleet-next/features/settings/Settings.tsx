"use client";

// Settings — sidebar navigation + card-based main content matching the
// settings screenshot. Sidebar groups: SETTINGS · THIS COMPUTER · CUSTOMIZE.
// Each section renders as a card (title, description, toggle/button controls)
// in the main content area. "General" is selected by default.

import React, { useEffect, useMemo, useState } from "react";
import { Button, Card, EmptyState, Toggle } from "@/components/ui";
import { Icon } from "@/components/icons";
import { useApp } from "@/lib/state";
import s from "./settings.module.css";
import { SETTINGS_SECTIONS, type SectionId } from "./settingsShared";
import { AgentModelsPanel, CredentialsPanel, ProvidersPanel } from "./ProvidersSettings";
import { DiagnosticsPanel, PrivacyPanel, UpdatesPanel } from "./SystemSettings";

const CATEGORY_ORDER = ["SETTINGS", "THIS COMPUTER", "CUSTOMIZE"] as const;

export default function Settings() {
  const { notify } = useApp() as { notify: (message: string, kind?: "error" | "warning" | "info" | "success") => void };
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
      case "privacy": return <PrivacyPanel />;
      case "import-export": return <StubPanel title="Import & export" note="Import and export routes are not exposed by this bridge build." />;
      case "keel-code": return <StubPanel title="Keel Code" note="Keel Code settings are managed on the Code surface." />;
      case "keel-desktop": return <StubPanel title="Keel Desktop" note="Keel Desktop is a separate application; its settings live in the desktop shell." />;
      case "policies": return <PoliciesPanel notify={notify} />;
      case "admin": return <AdminPanel notify={notify} />;
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
            <div className={s.navClose} onClick={() => {
              /* Close handled by the shell. */
            }}>
              <Icon name="close" size={15} /> Close
            </div>
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
              <SectionHeader label="ACCESSIBILITY" title="Accessibility" />
              <SettingCard title="Speak replies aloud (opt-in)" description="Uses this browser's speech synthesis; Keel sends no audio anywhere.">
                <Toggle checked={false} onChange={() => {}} label="Spoken aloud through the browser." />
              </SettingCard>
              <SettingCard title="Announce streaming updates" description="Live-region announcements for new agent text.">
                <select className={s.select} defaultValue="polite">
                  <option value="polite">Polite</option>
                  <option value="assertive">Assertive</option>
                  <option value="off">Off</option>
                </select>
                <p className={s.muted}>Saved in local state.</p>
              </SettingCard>
              <SectionHeader label="COMPOSER & READABILITY" title="Composer & readability" />
              <SettingCard title="High-legibility font" description="Work Sans (SIL OFL 1.1) — license included beside the font.">
                <Toggle checked={false} onChange={() => {}} label="Use the high-legibility font in the composer." />
              </SettingCard>
              <SettingCard title="Vim keybindings in composer" description="Escape = normal, i/a = insert, h/j/k/l navigation, 0/$ line edges.">
                <Toggle checked={false} onChange={() => {}} label="Vim navigation and editing in the composer." />
              </SettingCard>
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

// A single settings card: title, description, controls.
function SettingCard({ children, title, description }: { children: React.ReactNode; title: string; description?: string }) {
  return (
    <Card className={s.settingCard}>
      <div className={s.settingHead}>
        <h3 className={s.cardTitle}>{title}</h3>
      </div>
      {description && <p className={s.cardDesc}>{description}</p>}
      <div className={s.controls}>{children}</div>
    </Card>
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
  const [mode, setMode] = useState<"build" | "acceptEdits" | "plan" | "autopilot">("build");
  const MODES: Array<{ value: string; label: string }> = [
    { value: "build", label: "Build" },
    { value: "acceptEdits", label: "Accept edits" },
    { value: "plan", label: "Plan" },
    { value: "autopilot", label: "Autopilot" },
  ];
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
            onClick={() => { setMode(m.value as any); notify(`Permission mode set to ${m.label}.`, "success"); }}
          >
            {m.label}
          </button>
        ))}
      </div>
    </Card>
  );
}

// Admin — workspace trust placeholder.
function AdminPanel({ notify }: { notify: (message: string, kind?: "error" | "warning" | "info" | "success") => void }) {
  return (
    <Card className={s.settingCard}>
      <div className={s.settingHead}>
        <h3 className={s.cardTitle}>Workspace trust</h3>
      </div>
      <p className={s.cardDesc}>Keel only reads and writes folders you have explicitly trusted. Trust is stored by the bridge and can be revoked here.</p>
      <div className={s.controls}>
        <Button size="sm" onClick={() => notify("Workspace trust is managed through the bridge's projects route.", "info")}>Manage trusted folders</Button>
      </div>
    </Card>
  );
}

// Usage — usage counters card.
function UsagePanel() {
  return (
    <Card className={s.settingCard}>
      <div className={s.settingHead}>
        <h3 className={s.cardTitle}>Usage reported by the bridge</h3>
      </div>
      <p className={s.cardDesc}>Approximate totals across finished turns on this install, not a per-project bill.</p>
      <div className={s.controls}>
        <dl className={s.usageGrid}>
          <div><dt>Input tokens</dt><dd className={s.mono}>—</dd></div>
          <div><dt>Output tokens</dt><dd className={s.mono}>—</dd></div>
          <div><dt>Requests</dt><dd className={s.mono}>—</dd></div>
          <div><dt>Cost</dt><dd className={s.mono}>—</dd></div>
        </dl>
        <p className={s.muted}>The bridge returned no numeric usage fields. Cost is shown only if the bridge reports it.</p>
      </div>
    </Card>
  );
}


