"use client";

// Settings — sidebar navigation + card-based main content matching the
// settings screenshot. Sidebar groups: SETTINGS · THIS COMPUTER · CUSTOMIZE.
// Each section renders as a card (title, description, toggle/button controls)
// in the main content area. "General" is selected by default.

import React, { useEffect, useMemo, useState } from "react";
import { Button, Card, EmptyState } from "@/components/ui";
import { Icon } from "@/components/icons";
import s from "./settings.module.css";
import { SETTINGS_SECTIONS, type SectionId } from "./settingsShared";
import { AgentModelsPanel, CredentialsPanel, ProvidersPanel } from "./ProvidersSettings";
import { AccessibilityPanel, AppearancePanel, ResetPanel } from "./PreferencesSettings";
import { NetworkPanel, PermissionsPanel, TrustPanel } from "./SecuritySettings";
import { DiagnosticsPanel, PrivacyPanel, UpdatesPanel } from "./SystemSettings";

const CATEGORY_ORDER = ["SETTINGS", "THIS COMPUTER", "CUSTOMIZE"] as const;

export default function Settings({ onClose }: { onClose: () => void }) {
  const [active, setActive] = useState<SectionId>("general");
  const [search, setSearch] = useState("");

  useEffect(() => {
    const applyHash = () => {
      const id = window.location.hash.replace(/^#settings-/, "");
      const aliases: Record<string, SectionId> = {
        diagnostics: "system",
        trust: "admin",
        permissions: "policies",
      };
      const target = aliases[id] ?? id;
      const section = SETTINGS_SECTIONS.find((candidate) => candidate.id === target);
      if (section) setActive(section.id);
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
      case "agent-models": return <AgentModelsPanel />;
      case "credentials": return <CredentialsPanel />;
      case "usage": return <UsagePanel />;
      case "appearance": return <AppearancePanel />;
      case "accessibility": return <AccessibilityPanel />;
      case "reset": return <ResetPanel />;
      case "privacy": return <PrivacyPanel />;
      case "import-export": return <StubPanel title="Import & export" note="Import and export routes are not exposed by this bridge build." />;
      case "keel-code": return <StubPanel title="Keel Code" note="Keel Code settings are managed on the Code surface." />;
      case "keel-desktop": return <StubPanel title="Keel Desktop" note="Keel Desktop is a separate application; its settings live in the desktop shell." />;
      case "policies": return <PermissionsPanel />;
      case "admin": return <TrustPanel />;
      case "network": return <NetworkPanel />;
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
          <nav className={s.breadcrumb} aria-label="Breadcrumb">
            <span>{current.id === "providers" || current.id === "agent-models" || current.id === "credentials"
              ? "Models & providers"
              : current.category}</span>
            <span aria-hidden="true">/</span>
            <span aria-current="page">{current.title}</span>
          </nav>
          <h1>{current.title}</h1>
          <p>{current.description}</p>
        </header>
        <section className={s.content} aria-label={current.title}>
          {isGeneral && (
            <>
              <AccountCard />
              <SectionHeader label="LOCAL PREFERENCES" title="Make Keel yours" />
              <Card className={s.settingCard}>
                <h3>Appearance and accessibility</h3>
                <p className={s.cardDesc}>These controls reflect preferences the app shell can apply. Unsupported controls are not shown.</p>
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
        </section>
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


