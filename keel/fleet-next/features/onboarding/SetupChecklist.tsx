"use client";

// Small sidebar checklist. Informational only: an incomplete item never
// disables Cowork, Code, Duet or Fleet. Completed and deferred items are
// hidden; the whole checklist can be reopened from here or from Settings.
// This module is always mounted in the shell, so it also owns the in-app help
// entry point (button + command) and the real event the wizard uses to open it.

import React, { useCallback, useEffect, useState } from "react";
import { Badge, Button, SectionTitle } from "@/components/ui";
import { Icon } from "@/components/icons";
import { useApp } from "@/lib/state";
import HelpCenter, { type HelpDestination } from "./HelpCenter";
import {
  CHECKLIST_ITEMS, requiredDone, requiredTotal, restartAtStep, useChecklist,
  writeStep,
} from "./progress";
import s from "./onboarding.module.css";

export type ChecklistDestination = HelpDestination;

export interface SetupChecklistProps {
  onNavigate: (d: ChecklistDestination) => void;
}

/** The wizard cannot reach the sidebar behind its overlay; it asks for help
 *  through this event and the always-mounted checklist opens the dialog with
 *  the shell's real navigation callback. */
export const OPEN_HELP_EVENT = "keel-onboarding-help";

export default function SetupChecklist({ onNavigate }: SetupChecklistProps) {
  const { restartOnboarding, registerCommands } = useApp();
  const list = useChecklist();
  const done = requiredDone(list);
  const total = requiredTotal();
  const [helpOpen, setHelpOpen] = useState(false);

  const openHelp = useCallback(() => setHelpOpen(true), []);
  const closeHelp = useCallback(() => setHelpOpen(false), []);

  useEffect(() => {
    window.addEventListener(OPEN_HELP_EVENT, openHelp);
    return () => window.removeEventListener(OPEN_HELP_EVENT, openHelp);
  }, [openHelp]);

  useEffect(() => {
    registerCommands([{
      id: "help-center",
      label: "Open help & troubleshooting",
      group: "Help",
      run: openHelp,
    }]);
  }, [registerCommands, openHelp]);

  const destination = (id: (typeof CHECKLIST_ITEMS)[number]["id"]): ChecklistDestination => {
    const target = CHECKLIST_ITEMS.find((i) => i.id === id)?.target;
    if (target === "cowork" || target === "code" || target === "capabilities") return target;
    // "channels" has no dedicated destination in this build; Settings owns it.
    return "settings";
  };

  const visible = CHECKLIST_ITEMS.filter((i) => list[i.id] === "pending");
  const allRequiredDone = done === total;

  return (
    <section className={s.checklist} aria-label="Setup checklist">
      <SectionTitle action={<Badge tone={allRequiredDone ? "success" : "warning"}>
        {allRequiredDone ? "Setup complete" : `${done}/${total} required`}
      </Badge>}>
        Setup checklist
      </SectionTitle>

      {visible.length === 0 ? (
        <p className={s.checklistDone}>
          <Icon name="check" size={14} /> Setup reviewed. Everything else is optional.
        </p>
      ) : (
        <ul className={s.checklistList}>
          {visible.map((item) => (
            <li key={item.id} className={s.checklistItem}>
              <Icon name={item.required ? "warning" : "info"} size={14} className={s.checklistIcon} />
              <button type="button" className={s.checklistLink} onClick={() => {
                // The tour item is an action, not a page: replay it at its own
                // step instead of silently navigating to Cowork.
                if (item.id === "tour") { restartAtStep("tour"); restartOnboarding(); }
                else onNavigate(destination(item.id));
              }}>
                <span>{item.label}</span>
                <small>{item.required ? "Required" : "Optional"}</small>
              </button>
            </li>
          ))}
        </ul>
      )}

      <div className={s.checklistActions}>
        <Button
          size="sm"
          variant="ghost"
          onClick={() => { writeStep("welcome"); restartOnboarding(); }}
        >
          Review setup
        </Button>
        <Button
          size="sm"
          variant="ghost"
          onClick={() => { restartAtStep("tour"); restartOnboarding(); }}
        >
          Take the tour
        </Button>
        <Button size="sm" variant="ghost" onClick={openHelp}>
          <Icon name="info" size={13} /> Help
        </Button>
      </div>
      <p className={s.checklistNote}>Local use is never blocked by this list.</p>

      <HelpCenter open={helpOpen} onClose={closeHelp} onNavigate={onNavigate} />
    </section>
  );
}
