"use client";

// Client-side search over the rows already loaded for this session. It never
// calls the bridge, and every action is reachable with the keyboard: Ctrl/⌘+F
// opens it, Enter/Shift+Enter or arrows move between matches, Escape closes.

import React, { useEffect, useRef } from "react";
import { Icon } from "@/components/icons";
import type { RowMatch } from "./shared";
import s from "./cowork.module.css";

export interface SearchPanelProps {
  query: string;
  matches: RowMatch[];
  active: number;
  focusTick: number;
  onQuery: (query: string) => void;
  onClose: () => void;
  onStep: (delta: number) => void;
  onSelect: (index: number) => void;
}

const SHOWN = 30;

export default function SearchPanel({
  query, matches, active, focusTick, onQuery, onClose, onStep, onSelect,
}: SearchPanelProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  useEffect(() => { inputRef.current?.focus(); }, [focusTick]);

  const hasQuery = query.trim().length > 0;
  const count = matches.length;
  const shown = matches.slice(0, SHOWN);

  return (
    <section className={s.searchPanel} aria-label="Conversation search">
      <div className={s.searchInputRow}>
        <Icon name="search" size={15} />
        <input
          ref={inputRef}
          className={s.searchInput}
          value={query}
          placeholder="Search loaded messages…"
          aria-label="Search conversation"
          aria-keyshortcuts="Control+F Meta+F"
          onChange={(e) => onQuery(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Escape") { e.preventDefault(); e.stopPropagation(); onClose(); }
            else if (e.key === "Enter") { e.preventDefault(); onStep(e.shiftKey ? -1 : 1); }
            else if (e.key === "ArrowDown") { e.preventDefault(); onStep(1); }
            else if (e.key === "ArrowUp") { e.preventDefault(); onStep(-1); }
          }}
        />
        <span className={s.searchCount} role="status">
          {!hasQuery ? "Type to search this session" : count === 0 ? "No matches" : `${count} match${count === 1 ? "" : "es"}`}
        </span>
        <button type="button" className={s.searchNav} aria-label="Previous match" title="Previous match (Shift+Enter)" disabled={!count} onClick={() => onStep(-1)}>
          <Icon name="chevron" size={14} />
        </button>
        <button type="button" className={s.searchNav} aria-label="Next match" title="Next match (Enter)" disabled={!count} onClick={() => onStep(1)}>
          <Icon name="chevron" size={14} />
        </button>
        <button type="button" className={s.searchNav} aria-label="Close search" title="Close search (Escape)" onClick={onClose}>
          <Icon name="close" size={14} />
        </button>
      </div>
      {hasQuery && (
        <ol className={s.searchResults} aria-label="Search results">
          {shown.map((match, i) => (
            <li key={`${match.seq}-${match.index}`}>
              <button
                type="button"
                className={`${s.searchResult} ${i === active ? s.searchResultActive : ""}`}
                aria-current={i === active ? "true" : undefined}
                onClick={() => onSelect(i)}
              >
                <span className={s.resultLabel}>{match.label}</span>
                <span className={s.resultSnippet}>{match.snippet}</span>
              </button>
            </li>
          ))}
          {count > shown.length && <li className={s.resultMore}>Showing the first {shown.length} of {count} matches</li>}
        </ol>
      )}
    </section>
  );
}
