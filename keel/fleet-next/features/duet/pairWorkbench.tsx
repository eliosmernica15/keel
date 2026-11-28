"use client";

// Keel Duet = two modes sharing one workspace: Live Pair (hand-off + follow)
// and Review Pair (builder + independent comment-only reviewer). The mode
// buttons are plain toggles so they never shadow the Duet workspace tabs.

import React, { useState } from "react";
import type { Notice } from "@/lib/types";
import { Icon } from "@/components/icons";
import LivePairView from "./livePair";
import ReviewPairView from "./reviewPair";
import s from "./duet.module.css";

type Mode = "live" | "review";

interface Props {
  projectId: string | null;
  trusted: boolean;
  notify?: (message: string, kind?: Notice["kind"]) => void;
}

export default function PairWorkbench({ projectId, trusted, notify }: Props) {
  const [mode, setMode] = useState<Mode>("review");
  return (
    <div className={s.pairWorkbench} data-duet-pair-mode={mode}>
      <div className={s.pairModeBar} role="group" aria-label="Duet pair mode">
        <button type="button" className={s.pairModeButton}
          aria-pressed={mode === "live"} data-pair-mode-button="live"
          onClick={() => setMode("live")}>
          <Icon name="duet" size={14} /> Live Pair
        </button>
        <button type="button" className={s.pairModeButton}
          aria-pressed={mode === "review"} data-pair-mode-button="review"
          onClick={() => setMode("review")}>
          <Icon name="shield" size={14} /> Review Pair
        </button>
      </div>
      {mode === "live"
        ? <LivePairView projectId={projectId} notify={notify} onReviewPair={() => setMode("review")} />
        : <ReviewPairView projectId={projectId} trusted={trusted} notify={notify} />}
    </div>
  );
}
