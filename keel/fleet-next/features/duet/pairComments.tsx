"use client";

// A small, in-session bridge between the two Duet modes: Review Pair reads
// real reviewer rows and publishes its comments so the Review tab can show the
// same findings inline. Nothing is cached to disk or invented when empty.

import React, { createContext, useContext, useMemo, useState } from "react";
import type { ReviewComment } from "./pairSupport";

export type CommentResolution = "resolved" | "dismissed";
export interface SharedReviewComment extends ReviewComment {
  resolution?: CommentResolution;
  sentTaskId?: string;
}

interface PairCommentsContextValue {
  comments: SharedReviewComment[];
  setComments: (comments: SharedReviewComment[]) => void;
}

const PairCommentsContext = createContext<PairCommentsContextValue | null>(null);

export function PairCommentsProvider({ children }: { children: React.ReactNode }) {
  const [comments, setComments] = useState<SharedReviewComment[]>([]);
  const value = useMemo(() => ({ comments, setComments }), [comments]);
  return <PairCommentsContext.Provider value={value}>{children}</PairCommentsContext.Provider>;
}

export function usePairComments(): PairCommentsContextValue {
  const ctx = useContext(PairCommentsContext);
  if (!ctx) throw new Error("usePairComments must be used inside PairCommentsProvider");
  return ctx;
}
