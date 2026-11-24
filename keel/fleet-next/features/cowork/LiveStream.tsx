"use client";

// Streaming text is deliberately isolated from the durable transcript.
// Deltas are coalesced into one animation frame and delivered only to the live
// bubble's subscribers, so a token never re-renders the message history.

import React, { useSyncExternalStore } from "react";
import { Markdown } from "./Markdown";
import s from "./cowork.module.css";

type Listener = () => void;

export class StreamBuffer {
  private text = "";
  private live = false;
  private pending = "";
  private frame: number | null = null;
  private listeners = new Set<Listener>();

  subscribe = (listener: Listener): (() => void) => {
    this.listeners.add(listener);
    return () => { this.listeners.delete(listener); };
  };

  getSnapshot = (): string => this.text;
  getServerSnapshot = (): string => "";
  getLiveSnapshot = (): boolean => this.live;
  getServerLiveSnapshot = (): boolean => false;

  private emit(): void {
    for (const listener of [...this.listeners]) listener();
  }

  append(delta: string): void {
    if (!delta) return;
    this.live = true;
    if (typeof window === "undefined") { this.text += delta; this.emit(); return; }
    this.pending += delta;
    if (this.frame != null) return;
    this.frame = requestAnimationFrame(() => {
      this.frame = null;
      const chunk = this.pending;
      this.pending = "";
      if (!chunk) return;
      this.text += chunk;
      this.emit();
    });
  }

  clear(): void {
    if (this.frame != null) cancelAnimationFrame(this.frame);
    this.frame = null;
    this.pending = "";
    this.live = false;
    if (this.text) { this.text = ""; this.emit(); }
  }

  dispose(): void {
    this.clear();
    this.listeners.clear();
  }
}

export function useStreamText(stream: StreamBuffer): string {
  return useSyncExternalStore(stream.subscribe, stream.getSnapshot, stream.getServerSnapshot);
}

/** The only transcript node that re-renders for a streamed token. */
export function LiveBubble({ stream, active, botName }: {
  stream: StreamBuffer;
  active: boolean;
  botName: string;
}) {
  const text = useStreamText(stream);
  const live = useSyncExternalStore(stream.subscribe, stream.getLiveSnapshot, stream.getServerLiveSnapshot);
  if ((!active && !live) || !text) return null;
  return (
    <article className={`${s.bubble} ${s.bubbleAssistant} ${s.streamBubble}`} aria-live="polite" data-cowork-live="true">
      <header className={s.bubbleHead}>
        <span className={s.role}>{botName}</span><span className={s.streamingLabel}>streaming</span>
      </header>
      <Markdown text={text} /><span className={s.caret} aria-hidden="true" />
    </article>
  );
}
