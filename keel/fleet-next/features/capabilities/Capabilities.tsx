"use client";

// Capability Hub — one discoverable place for everything the bridge actually
// exposes. Each panel owns its own loading, empty and error states.

import React, { useEffect, useState } from "react";
import { Badge, Tabs } from "@/components/ui";
import { Icon, type IconName } from "@/components/icons";
import { useApp } from "@/lib/state";
import s from "./capabilities.module.css";
import SkillsPanel from "./SkillsPanel";
import { ConnectorsPanel, McpPanel } from "./McpPanel";
import { CommandsPanel, ToolsPanel } from "./ToolsCommandsPanel";
import { ExtensionsPanel, WorkflowsPanel } from "./WorkflowsExtensionsPanel";

type Tab = "skills" | "mcp" | "connectors" | "tools" | "commands" | "workflows" | "extensions";

const TABS: Array<{ value: Tab; label: string; icon: IconName }> = [
  { value: "skills", label: "Skills", icon: "spark" },
  { value: "mcp", label: "MCP servers", icon: "link" },
  { value: "connectors", label: "Connectors", icon: "capabilities" },
  { value: "tools", label: "Tools", icon: "terminal" },
  { value: "commands", label: "Commands", icon: "command" },
  { value: "workflows", label: "Workflows", icon: "routine" },
  { value: "extensions", label: "Extensions", icon: "folder" },
];

export default function Capabilities() {
  const [tab, setTab] = useState<Tab>("skills");
  const { registerCommands } = useApp();

  useEffect(() => {
    registerCommands(TABS.map((t) => ({
      id: `capabilities-open-${t.value}`,
      label: `Open ${t.label}`,
      group: "Capabilities",
      hint: "Capability Hub",
      run: () => setTab(t.value),
    })));
  }, [registerCommands]);

  const active = TABS.find((t) => t.value === tab) ?? TABS[0];

  return (
    <div className={s.hub}>
      <header className={s.head}>
        <div className={s.headTop}>
          <div className={s.titleWrap}>
            <span className={s.titleIcon} aria-hidden="true"><Icon name="capabilities" size={20} /></span>
            <div>
              <h1>Capabilities</h1>
              <p className={s.subtitle}>What Keel can do on this machine. Status is shown only when the local bridge reports it; unavailable systems are labelled explicitly.</p>
            </div>
          </div>
          <Badge tone="neutral">Local-first</Badge>
        </div>
        <div className={s.tabsBar}>
          <Tabs tabs={TABS.map((t) => ({ ...t, icon: <Icon name={t.icon} size={14} /> }))}
            value={tab} onChange={setTab} label="Capability categories" />
        </div>
      </header>

      <div className={s.content}>
        <section role="tabpanel" aria-label={`${active.label} capabilities`} className={s.tabPanel}>
          {tab === "skills" && <SkillsPanel />}
          {tab === "mcp" && <McpPanel />}
          {tab === "connectors" && <ConnectorsPanel />}
          {tab === "tools" && <ToolsPanel />}
          {tab === "commands" && <CommandsPanel />}
          {tab === "workflows" && <WorkflowsPanel />}
          {tab === "extensions" && <ExtensionsPanel />}
        </section>
      </div>
    </div>
  );
}
