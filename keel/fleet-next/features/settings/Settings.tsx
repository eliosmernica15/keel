"use client";

// Settings — searchable navigation with a visible breadcrumb. Each section
// calls only real bridge routes or real app-shell state.

import React, { useEffect, useMemo, useState } from "react";
import { EmptyState, TextField } from "@/components/ui";
import { Icon } from "@/components/icons";
import { useApp } from "@/lib/state";
import s from "./settings.module.css";
import { SETTINGS_SECTIONS, type SectionId } from "./settingsShared";
import { AgentModelsPanel, CredentialsPanel, ProvidersPanel } from "./ProvidersSettings";
import { NetworkPanel, PermissionsPanel, TrustPanel } from "./SecuritySettings";
import { DiagnosticsPanel, PrivacyPanel, UpdatesPanel } from "./SystemSettings";
import { AccessibilityPanel, AppearancePanel, ResetPanel } from "./PreferencesSettings";

const CATEGORY_ORDER = ["Models & providers", "Security & trust", "Privacy & system", "Preferences"];

export default function Settings() {
  const [active, setActive] = useState<SectionId>("providers");
  const [search, setSearch] = useState("");
  const { registerCommands } = useApp();

  useEffect(() => {
    const applyHash = () => {
      const id = window.location.hash.replace(/^#settings-/, "");
      if (SETTINGS_SECTIONS.some((section) => section.id === id)) setActive(id as SectionId);
    };
    applyHash();
    window.addEventListener("hashchange", applyHash);
    return () => window.removeEventListener("hashchange", applyHash);
  }, []);

  useEffect(() => {
    registerCommands(SETTINGS_SECTIONS.map((section) => ({
      id: `settings-open-${section.id}`,
      label: `Open ${section.title} settings`,
      group: "Settings",
      hint: section.category,
      run: () => select(section.id),
    })));
    // select only uses a stable state setter and history API
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [registerCommands]);

  function select(id: SectionId) {
    setActive(id);
    try { window.history.replaceState(null, "", `#settings-${id}`); } catch { /* ignore */ }
  }

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

  function renderSection(id: SectionId) {
    switch (id) {
      case "providers": return <ProvidersPanel />;
      case "agent-models": return <AgentModelsPanel />;
      case "credentials": return <CredentialsPanel />;
      case "permissions": return <PermissionsPanel />;
      case "trust": return <TrustPanel />;
      case "network": return <NetworkPanel />;
      case "privacy": return <PrivacyPanel />;
      case "diagnostics": return <DiagnosticsPanel />;
      case "updates": return <UpdatesPanel />;
      case "appearance": return <AppearancePanel />;
      case "accessibility": return <AccessibilityPanel />;
      case "reset": return <ResetPanel />;
    }
  }

  return (
    <div className={s.settings}>
      <aside className={s.nav} aria-label="Settings navigation">
        <TextField type="search" label="Search settings" placeholder="Search all settings" value={search}
          onChange={(e) => setSearch(e.target.value)} className={s.search} />
        {matches.length === 0 ? (
          <p className={s.noMatches}>No settings match “{search}”.</p>
        ) : CATEGORY_ORDER.map((category) => {
          const items = matches.filter((section) => section.category === category);
          if (items.length === 0) return null;
          return (
            <section className={s.navGroup} key={category} aria-label={category}>
              <h2>{category}</h2>
              <ul>
                {items.map((section) => (
                  <li key={section.id}>
                    <button type="button" className={`${s.navItem} ${active === section.id ? s.navItemActive : ""}`}
                      aria-current={active === section.id ? "page" : undefined} onClick={() => select(section.id)}>
                      <Icon name={section.icon} size={15} />
                      <span>{section.title}</span>
                    </button>
                  </li>
                ))}
              </ul>
            </section>
          );
        })}
      </aside>

      <main className={s.main}>
        <header className={s.header}>
          <nav aria-label="Breadcrumb" className={s.breadcrumb}>
            <span>Settings</span><Icon name="chevron" size={12} /><span>{current.category}</span><Icon name="chevron" size={12} />
            <span aria-current="page">{current.title}</span>
          </nav>
          <h1>{current.title}</h1>
          <p>{current.description}</p>
        </header>
        {matches.length === 0 ? (
          <EmptyState icon={<Icon name="search" />} title="No matching settings" description="Try another term, or clear the search to see every category." />
        ) : (
          <section className={s.content} aria-label={current.title} key={current.id}>{renderSection(current.id)}</section>
        )}
      </main>
    </div>
  );
}
