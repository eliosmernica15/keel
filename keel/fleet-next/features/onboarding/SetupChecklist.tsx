"use client";

// Small sidebar checklist. Informational only: an incomplete item never
// disables Cowork, Code, Duet or Fleet. Completed and deferred items are
// hidden; the whole checklist can be reopened from here or from Settings.

import React from "react";
import { Badge, Button, SectionTitle } from "@/components/ui";
import { Icon } from "@/components/icons";
import { useApp } from "@/lib/state";
import {
  CHECKLIST_ITEMS, requiredDone, requiredTotal, restartAtStep, useChecklist,
  writeStep, type ItemId,
} from "./progress";
import s from "./onboarding.module.css";

export type ChecklistDestination =
  | "cowork" | "code" | "duet" | "fleet" | "capabilities" | "settings";

export interface SetupChecklistProps {
  onNavigate: (d: ChecklistDestination) => void;
}

export default function SetupChecklist({ onNavigate }: SetupChecklistProps) {
  const { restartOnboarding } = useApp();
  const list = useChecklist();
  const done = requiredDone(list);
  const total = requiredTotal();

  const destination = (id: ItemId): ChecklistDestination => {
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
        {done}/{total} required
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
              <button type="button" className={s.checklistLink} onClick={() => onNavigate(destination(item.id))}>
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
      </div>
      <p className={s.checklistNote}>Local use is never blocked by this list.</p>
    </section>
  );
}
