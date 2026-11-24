"use client";

// Cowork composer: autosize, multiline, per-bot draft, real File chips that
// are uploaded into the agent's library before the message is sent, paste/drop,
// slash-command insertion, send/stop/retry. Upload state is never optimistic.

import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Icon, IconButton } from "@/components/icons";
import { Button } from "@/components/ui";
import { bridge, errMessage, SLASH_COMMANDS } from "@/lib/api";
import type { Notice } from "@/lib/types";
import { textOf } from "./shared";
import s from "./cowork.module.css";

export type ComposerMode = "build" | "plan" | "autopilot" | "acceptEdits";

const MODES: Array<{ value: ComposerMode; label: string }> = [
  { value: "build", label: "Build" },
  { value: "plan", label: "Plan" },
  { value: "autopilot", label: "Autopilot" },
  { value: "acceptEdits", label: "Accept edits" },
];

export interface UploadedFile { id: string; name: string; }

type ChipStatus = "pending" | "uploading" | "done" | "failed";

interface Chip {
  id: number;
  file: File;
  status: ChipStatus;
  libraryId?: string;
  libraryName?: string;
  error?: string;
}

const STATUS_LABEL: Record<ChipStatus, string> = {
  pending: "Pending", uploading: "Uploading…", done: "In library", failed: "Failed",
};
const STATUS_CLASS: Record<ChipStatus, string> = {
  pending: s.status_pending, uploading: s.status_uploading,
  done: s.status_done, failed: s.status_failed,
};

// The bridge reads this JSON body with a 6 MB limit.
const MAX_BODY_BYTES = 6_000_000;
const TEXT_EXT = /\.(txt|md|markdown|json|csv|log|py|js|jsx|ts|tsx|css|scss|html|htm|xml|ya?ml|toml|ini|sh|bat|sql|rst)$/i;

function readDataUrl(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result ?? ""));
    reader.onerror = () => reject(new Error(`Could not read ${file.name}`));
    reader.readAsDataURL(file);
  });
}

async function buildUploadPayload(file: File, botId: string): Promise<Record<string, string>> {
  const isText = file.type.startsWith("text/") || TEXT_EXT.test(file.name);
  if (isText) {
    const content = await file.text();
    if (content.length + file.name.length + botId.length + 256 > MAX_BODY_BYTES) {
      throw new Error("File exceeds the bridge's 6 MB request limit.");
    }
    return { filename: file.name, bot_id: botId, content, mime: file.type || "text/plain" };
  }
  const dataUrl = await readDataUrl(file);
  const comma = dataUrl.indexOf(",");
  const base64 = comma >= 0 ? dataUrl.slice(comma + 1) : dataUrl;
  if (base64.length + file.name.length + botId.length + 256 > MAX_BODY_BYTES) {
    throw new Error("File is too large for the bridge's 6 MB request limit (base64 adds about 33%).");
  }
  return { filename: file.name, bot_id: botId, content_base64: base64, mime: file.type || "application/octet-stream" };
}

export interface ComposerProps {
  botId: string | null;
  busy: boolean;
  onSend: (text: string, uploaded: UploadedFile[], targetBotId: string) => Promise<boolean>;
  ensureBot: () => Promise<string | null>;
  onStop: () => void;
  mode: ComposerMode;
  onModeChange: (m: ComposerMode) => void;
  modelLabel?: string;
  providerLabel?: string;
  error?: string | null;
  onRetry?: () => void;
  seed?: { text: string; nonce: number };
  focusSignal?: number;
  large?: boolean;
  placeholder?: string;
  notify: (message: string, kind?: Notice["kind"]) => void;
}

const draftKey = (id: string | null) => `keel-draft:${id ?? "home"}`;

export default function Composer({
  botId, busy, onSend, ensureBot, onStop, mode, onModeChange, modelLabel, providerLabel,
  error, onRetry, seed, focusSignal, large, placeholder, notify,
}: ComposerProps) {
  const [text, setText] = useState("");
  const [chips, setChips] = useState<Chip[]>([]);
  const [dragOver, setDragOver] = useState(false);
  const [slashDismissed, setSlashDismissed] = useState(false);
  const [sending, setSending] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const taRef = useRef<HTMLTextAreaElement>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const chipSeq = useRef(0);
  const chipsRef = useRef<Chip[]>([]);
  const sendingRef = useRef(false);

  const setChipsList = useCallback((next: Chip[]) => {
    chipsRef.current = next;
    setChips(next);
  }, []);

  const patchChip = useCallback((id: number, patch: Partial<Chip>) => {
    setChipsList(chipsRef.current.map((c) => c.id === id ? { ...c, ...patch } : c));
  }, [setChipsList]);

  // hydrate the draft for the selected bot; never share drafts across bots
  useEffect(() => {
    let stored = "";
    try { stored = localStorage.getItem(draftKey(botId)) ?? ""; } catch { /* storage disabled */ }
    setText(stored);
    if (!sendingRef.current) setChipsList([]);
    setSlashDismissed(false);
  }, [botId, setChipsList]);

  useEffect(() => {
    try {
      if (text) localStorage.setItem(draftKey(botId), text);
      else localStorage.removeItem(draftKey(botId));
    } catch { /* storage disabled */ }
  }, [text, botId]);

  const resize = useCallback(() => {
    const ta = taRef.current;
    if (!ta) return;
    ta.style.height = "auto";
    ta.style.height = `${Math.min(ta.scrollHeight, large ? 320 : 220)}px`;
  }, [large]);

  useEffect(() => { resize(); }, [text, resize]);

  useEffect(() => {
    if (seed && seed.nonce > 0) {
      setText(seed.text);
      setSlashDismissed(false);
      requestAnimationFrame(() => { taRef.current?.focus(); resize(); });
    }
    // seed.nonce is the change signal; seed.text travels with it
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [seed?.nonce]);

  useEffect(() => {
    if (focusSignal && focusSignal > 0) taRef.current?.focus();
  }, [focusSignal]);

  const addFiles = useCallback((list: FileList | File[] | null) => {
    if (!list) return;
    const files = Array.from(list).filter((f): f is File => f instanceof File);
    if (!files.length) return;
    setChipsList([
      ...chipsRef.current,
      ...files.map((file) => ({ id: ++chipSeq.current, file, status: "pending" as ChipStatus })),
    ]);
    setUploadError(null);
    notify(`${files.length} file${files.length === 1 ? "" : "s"} selected — uploaded to the library when you send.`, "info");
  }, [notify, setChipsList]);

  const slashQuery = text.startsWith("/") && !/\s/.test(text) ? text.slice(1).toLowerCase() : null;
  const slashMatches = useMemo(
    () => slashQuery === null || slashDismissed ? [] : SLASH_COMMANDS.filter((c) => c.name.toLowerCase().includes(slashQuery)).slice(0, 7),
    [slashQuery, slashDismissed],
  );

  const insertCommand = (usage: string) => {
    setText(`${usage} `);
    setSlashDismissed(false);
    taRef.current?.focus();
  };

  const resolveBot = useCallback(async (): Promise<string | null> => botId ?? await ensureBot(), [botId, ensureBot]);

  /** Upload one real file. State changes only after the bridge responds. */
  const uploadOne = useCallback(async (chip: Chip, targetBotId: string): Promise<UploadedFile | null> => {
    patchChip(chip.id, { status: "uploading", error: undefined });
    try {
      const payload = await buildUploadPayload(chip.file, targetBotId);
      const response = await bridge.uploadLibrary(payload) as { file?: Record<string, unknown> } | null;
      const record = (response && typeof response === "object" ? (response.file ?? response) : null) as Record<string, unknown> | null;
      const id = textOf(record?.id);
      if (!id) throw new Error("The bridge did not return a library file id.");
      const name = textOf(record?.name) || chip.file.name;
      patchChip(chip.id, { status: "done", libraryId: id, libraryName: name });
      return { id, name };
    } catch (err) {
      patchChip(chip.id, { status: "failed", error: errMessage(err) });
      return null;
    }
  }, [patchChip]);

  const retryChip = useCallback(async (chip: Chip) => {
    if (chip.status === "uploading") return;
    const target = await resolveBot();
    if (!target) { setUploadError("No task is available — the file was not uploaded."); return; }
    setUploadError(null);
    await uploadOne(chip, target);
  }, [resolveBot, uploadOne]);

  const submit = async () => {
    const value = text.trim();
    if (!value || busy || sendingRef.current) return;
    sendingRef.current = true;
    setSending(true);
    setUploadError(null);
    try {
      const target = await resolveBot();
      if (!target) {
        setUploadError("Could not create a task — nothing was uploaded or sent.");
        return;
      }
      const uploaded: UploadedFile[] = [];
      for (const chip of chipsRef.current) {
        if (chip.status === "failed") continue; // failed uploads are not "will be sent"
        if (chip.status === "done" && chip.libraryId) {
          uploaded.push({ id: chip.libraryId, name: chip.libraryName ?? chip.file.name });
          continue;
        }
        const result = await uploadOne(chip, target);
        if (result) uploaded.push(result);
      }
      const ok = await onSend(value, uploaded, target);
      if (ok) {
        setText("");
        // Keep failed files visible so they can be retried; nothing vanishes silently.
        setChipsList(chipsRef.current.filter((c) => c.status === "failed"));
        setSlashDismissed(false);
      }
    } finally {
      sendingRef.current = false;
      setSending(false);
    }
  };

  const onKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Escape" && slashMatches.length) {
      e.preventDefault(); e.stopPropagation(); setSlashDismissed(true); return;
    }
    if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault();
      void submit();
    }
  };

  const working = busy || sending;

  return (
    <div className={`${s.composer} ${large ? s.composerLarge : ""}`}>
      {error && (
        <div className={s.composerError} role="alert">
          <Icon name="error" size={15} />
          <span>{error}</span>
          {onRetry && <button type="button" className={s.retryLink} onClick={onRetry}>Retry</button>}
        </div>
      )}
      {uploadError && (
        <div className={s.composerError} role="alert">
          <Icon name="error" size={15} /><span>{uploadError}</span>
        </div>
      )}

      {slashMatches.length > 0 && (
        <div className={s.slashPalette} role="listbox" aria-label="Slash commands">
          {slashMatches.map((c) => (
            <button key={c.name} type="button" role="option" aria-selected={false} className={s.slashRow} onClick={() => insertCommand(c.usage ?? `/${c.name}`)}>
              <span className={s.slashName}>/{c.name}</span>
              <span className={s.slashDesc}>{c.description ?? "Insert command"}</span>
            </button>
          ))}
        </div>
      )}

      <div
        className={`${s.composerBox} ${dragOver ? s.composerDragging : ""}`}
        onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
        onDragLeave={(e) => { if (e.currentTarget === e.target) setDragOver(false); }}
        onDrop={(e) => {
          e.preventDefault(); setDragOver(false);
          addFiles(e.dataTransfer.files);
        }}
      >
        {chips.length > 0 && (
          <div className={s.uploadArea} aria-label="Files for this message">
            <div className={s.uploadList}>
              {chips.map((chip) => (
                <div className={s.uploadItem} key={chip.id}>
                  <Icon
                    name={chip.status === "done" ? "check" : chip.status === "failed" ? "error" : chip.status === "uploading" ? "clock" : "attach"}
                    size={14}
                  />
                  <span className={s.uploadName} title={chip.file.name}>{chip.file.name}</span>
                  <span className={`${s.uploadStatus} ${STATUS_CLASS[chip.status]}`}>{STATUS_LABEL[chip.status]}</span>
                  {chip.status === "failed" && (
                    <button type="button" className={s.uploadRetry} onClick={() => void retryChip(chip)}>Retry</button>
                  )}
                  <IconButton
                    label={`Remove ${chip.file.name}`}
                    className={s.chipRemove}
                    onClick={() => setChipsList(chipsRef.current.filter((c) => c.id !== chip.id))}
                  >
                    <Icon name="close" size={12} />
                  </IconButton>
                  {chip.error && <span className={s.uploadError} role="alert">{chip.error}</span>}
                </div>
              ))}
            </div>
            <p className={s.attachNote} role="note">
              Files are uploaded to this agent&apos;s library before the message is sent and referenced by name. They are not attached directly to the model prompt.
            </p>
          </div>
        )}

        <textarea
          ref={taRef}
          className={s.textarea}
          value={text}
          rows={1}
          placeholder={placeholder ?? (large ? "Describe a task, ask a question, or paste something to work on…" : "Message Keel…  (/ for commands)")}
          aria-label="Message Keel"
          onChange={(e) => { setText(e.target.value); setSlashDismissed(false); }}
          onKeyDown={onKeyDown}
          onPaste={(e) => {
            if (e.clipboardData.files.length) { e.preventDefault(); addFiles(e.clipboardData.files); }
          }}
        />

        <div className={s.toolbar}>
          <input
            ref={fileRef} type="file" multiple hidden tabIndex={-1}
            onChange={(e) => { addFiles(e.target.files); e.target.value = ""; }}
          />
          <IconButton label="Attach files" onClick={() => fileRef.current?.click()} title="Add files to the agent's library">
            <Icon name="attach" size={17} />
          </IconButton>
          <span className={s.divider} aria-hidden="true" />
          <select
            className={s.select}
            value={mode}
            onChange={(e) => onModeChange(e.target.value as ComposerMode)}
            aria-label="Permission mode"
            title="Permission mode sent with the message"
          >
            {MODES.map((m) => <option key={m.value} value={m.value}>{m.label}</option>)}
          </select>
          {(modelLabel || providerLabel) && (
            <span className={s.infoChip} title="Active model reported by the bridge">
              <Icon name="spark" size={13} />
              <span className={s.infoText}>{[providerLabel, modelLabel].filter(Boolean).join(" · ")}</span>
            </span>
          )}
          <span className={s.spacer} />
          {working ? (
            busy ? (
              <Button variant="danger" size="sm" onClick={onStop} aria-label="Stop the current turn">
                <Icon name="stop" size={13} /> Stop
              </Button>
            ) : (
              <span className={s.uploadingPill} role="status">
                <Icon name="clock" size={13} /> Uploading…
              </span>
            )
          ) : (
            <button
              type="button" className={s.send}
              onClick={() => void submit()}
              disabled={!text.trim() || sending}
              aria-label="Send message"
              title="Send message (Enter)"
            >
              <Icon name="send" size={17} />
            </button>
          )}
        </div>
      </div>

      <p className={s.hints}>
        <span><b>Enter</b> send</span><span><b>Shift+Enter</b> newline</span><span><b>/</b> commands</span>
      </p>
    </div>
  );
}
