"use client";

// Cowork composer: autosize, multiline, per-bot draft, real File chips that
// are uploaded into the agent's library before the message is sent, paste/drop,
// slash-command insertion, send/stop/retry. Upload state is never optimistic.
// Optional browser-native dictation: the microphone is only touched after an
// explicit click, final transcripts are inserted at the caret, and nothing is
// ever auto-sent. There is no audio upload and no backend dependency.

import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Icon, IconButton } from "@/components/icons";
import { Button } from "@/components/ui";
import { errMessage, SLASH_COMMANDS } from "@/lib/api";
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
  /** Percent of bytes actually sent, reported by XMLHttpRequest. */
  progress?: number;
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

// Structural types for the browser-native Web Speech API. lib.dom does not
// ship these interfaces and adding a type package would be a new dependency,
// so the small surface this composer consumes is described locally.
interface SpeechAlternativeLike { transcript: string; }
interface SpeechResultLike { isFinal: boolean; 0?: SpeechAlternativeLike; }
interface SpeechResultListLike { length: number; [index: number]: SpeechResultLike | undefined; }
interface SpeechResultEventLike { resultIndex: number; results: SpeechResultListLike; }
interface SpeechErrorEventLike { error: string; }
interface SpeechRecognitionLike {
  lang: string;
  continuous: boolean;
  interimResults: boolean;
  maxAlternatives: number;
  onstart: (() => void) | null;
  onresult: ((event: SpeechResultEventLike) => void) | null;
  onerror: ((event: SpeechErrorEventLike) => void) | null;
  onend: (() => void) | null;
  start(): void;
  stop(): void;
  abort(): void;
}
type SpeechRecognitionConstructor = new () => SpeechRecognitionLike;
type DictationState = "idle" | "listening" | "processing" | "stopped" | "error";

function getSpeechRecognitionConstructor(): SpeechRecognitionConstructor | null {
  if (typeof window === "undefined") return null;
  const scope = window as unknown as {
    SpeechRecognition?: SpeechRecognitionConstructor;
    webkitSpeechRecognition?: SpeechRecognitionConstructor;
  };
  // Standard name first, prefixed fallback for WebKit-based browsers.
  return scope.SpeechRecognition ?? scope.webkitSpeechRecognition ?? null;
}

function dictationErrorMessage(code: string): string {
  switch (code) {
    case "not-allowed":
    case "service-not-allowed":
    case "permission-denied":
      return "Microphone permission was denied. Allow microphone access for this page in your browser settings, then try again.";
    case "no-speech":
      return "No speech was detected. Try again and speak clearly into your microphone.";
    case "audio-capture":
      return "No microphone was found or it could not be used. Check your device and try again.";
    case "network":
      return "Speech recognition could not reach its service. Check your connection and try again.";
    case "aborted":
      return "Dictation was cancelled before a transcript was produced.";
    default:
      return `Dictation failed${code ? ` (${code})` : ""}. Nothing was inserted into your draft.`;
  }
}

/** Original 24px line glyph, drawn in the same style as components/icons.tsx. */
function MicIcon({ size = 17 }: { size?: number }) {
  return (
    <svg viewBox="0 0 24 24" width={size} height={size} fill="none" stroke="currentColor"
      strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" className="keel-icon">
      <rect x="9" y="3" width="6" height="11" rx="3" />
      <path d="M5.5 11a6.5 6.5 0 0 0 13 0M12 17.5V21M9 21h6" />
    </svg>
  );
}

function readDataUrl(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result ?? ""));
    reader.onerror = () => reject(new Error(`Could not read ${file.name}`));
    reader.readAsDataURL(file);
  });
}

/** POST the real library body with XHR so upload progress is measured from
 *  bytes actually sent. A percentage is only shown when the browser reports a
 *  computable total; server confirmation still decides the final state. */
function postLibrary(payload: Record<string, string>, onProgress: (percent: number) => void): Promise<unknown> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", "/api/bridge/library");
    xhr.setRequestHeader("Content-Type", "application/json");
    xhr.upload.onprogress = (event) => {
      if (event.lengthComputable && event.total > 0) {
        onProgress(Math.max(0, Math.min(99, Math.round((event.loaded / event.total) * 100))));
      }
    };
    xhr.onload = () => {
      let body: unknown = null;
      try { body = JSON.parse(xhr.responseText); } catch { /* non-JSON error body */ }
      if (xhr.status < 200 || xhr.status >= 300) {
        reject(new Error(errMessage(body) !== "Request failed" ? errMessage(body) : `Upload failed (HTTP ${xhr.status}).`));
        return;
      }
      resolve(body);
    };
    xhr.onerror = () => reject(new Error("Upload failed — the local bridge could not be reached."));
    xhr.onabort = () => reject(new Error("Upload was cancelled."));
    xhr.send(JSON.stringify(payload));
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
  /** Offline model ids reported by the bridge's provider catalog. */
  models?: string[];
  modelSaving?: boolean;
  onModelChange?: (model: string) => void;
  error?: string | null;
  onRetry?: () => void;
  seed?: { text: string; nonce: number };
  focusSignal?: number;
  large?: boolean;
  placeholder?: string;
  notify: (message: string, kind?: Notice["kind"]) => void;
}

const draftKey = (id: string | null) => `keel-draft:${id ?? "home"}`;

function readDraft(id: string | null): string {
  try { return localStorage.getItem(draftKey(id)) ?? ""; } catch { return ""; }
}

export default function Composer({
  botId, busy, onSend, ensureBot, onStop, mode, onModeChange, modelLabel, providerLabel,
  models, modelSaving, onModelChange,
  error, onRetry, seed, focusSignal, large, placeholder, notify,
}: ComposerProps) {
  // Initialise from storage during render (the Cowork parent keys this
  // component by session). An effect-based hydration raced the persist effect
  // under React StrictMode and silently erased the draft on remount.
  const [text, setText] = useState(() => readDraft(botId));
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

  // Dictation support is detected after mount so server HTML and the first
  // client render agree; no microphone is requested during that detection.
  const [dictationSupported, setDictationSupported] = useState<boolean | null>(null);
  const [dictationState, setDictationState] = useState<DictationState>("idle");
  const [dictationMessage, setDictationMessage] = useState("");
  const ctorRef = useRef<SpeechRecognitionConstructor | null>(null);
  const recognitionRef = useRef<SpeechRecognitionLike | null>(null);
  const cursorRef = useRef<{ start: number; end: number } | null>(null);
  const finalizedRef = useRef(false);
  const insertedRef = useRef(false);
  const tearingDownRef = useRef(false);
  const dictationStateRef = useRef<DictationState>("idle");
  const textRef = useRef(text);

  const setDictation = useCallback((next: DictationState, message: string) => {
    dictationStateRef.current = next;
    setDictationState(next);
    setDictationMessage(message);
  }, []);

  const setChipsList = useCallback((next: Chip[]) => {
    chipsRef.current = next;
    setChips(next);
  }, []);

  const patchChip = useCallback((id: number, patch: Partial<Chip>) => {
    setChipsList(chipsRef.current.map((c) => c.id === id ? { ...c, ...patch } : c));
  }, [setChipsList]);

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

  useEffect(() => { textRef.current = text; }, [text]);

  useEffect(() => {
    const ctor = getSpeechRecognitionConstructor();
    ctorRef.current = ctor;
    setDictationSupported(Boolean(ctor));
  }, []);

  // The parent keys this composer by session, but stop explicitly here too so
  // a bot switch or an unmount can never leave a live microphone behind.
  useEffect(() => () => {
    tearingDownRef.current = true;
    const rec = recognitionRef.current;
    recognitionRef.current = null;
    if (rec) {
      rec.onstart = null;
      rec.onresult = null;
      rec.onerror = null;
      rec.onend = null;
      try { rec.abort(); } catch { /* already ended */ }
    }
    cursorRef.current = null;
  }, [botId]);

  /** Insert recognized words into the existing draft at the caret captured
   *  when dictation started. Sending is deliberately not part of this path. */
  const insertTranscript = useCallback((transcript: string) => {
    const ta = taRef.current;
    const current = ta?.value ?? textRef.current;
    const cursor = cursorRef.current;
    const start = Math.min(Math.max(cursor?.start ?? current.length, 0), current.length);
    const end = Math.min(Math.max(cursor?.end ?? start, start), current.length);
    const before = current.slice(0, start);
    const after = current.slice(end);
    const needsSpace = before.length > 0 && !/\s$/.test(before) && !/^\s/.test(transcript);
    const insertion = `${needsSpace ? " " : ""}${transcript}`;
    const next = before + insertion + after;
    textRef.current = next;
    setText(next);
    setSlashDismissed(false);
    const caret = before.length + insertion.length;
    requestAnimationFrame(() => {
      const el = taRef.current;
      if (!el) return;
      el.focus();
      el.setSelectionRange(caret, caret);
      resize();
    });
  }, [resize]);

  const startDictation = useCallback(() => {
    const Ctor = ctorRef.current;
    if (!Ctor || recognitionRef.current) return;

    // Capture the caret on the explicit click, before focus moves to the
    // microphone button, so text on both sides of it is preserved.
    const ta = taRef.current;
    cursorRef.current = {
      start: ta?.selectionStart ?? textRef.current.length,
      end: ta?.selectionEnd ?? ta?.selectionStart ?? textRef.current.length,
    };
    finalizedRef.current = false;
    insertedRef.current = false;
    tearingDownRef.current = false;

    let recognition: SpeechRecognitionLike;
    try {
      recognition = new Ctor();
      recognition.lang = typeof navigator !== "undefined" && navigator.language ? navigator.language : "en-US";
      recognition.continuous = false;
      recognition.interimResults = false; // only final, confirmed words are inserted
      recognition.maxAlternatives = 1;
    } catch {
      setDictation("error", "Dictation could not start in this browser.");
      return;
    }

    recognition.onstart = () => {
      if (tearingDownRef.current) return;
      setDictation("listening", "Listening… speak now. Press Stop dictation when you are done.");
    };

    recognition.onresult = (event) => {
      if (tearingDownRef.current || finalizedRef.current) return;
      let transcript = "";
      for (let i = event.resultIndex; i < event.results.length; i++) {
        const result = event.results[i];
        if (result?.isFinal) transcript += result[0]?.transcript ?? "";
      }
      const words = transcript.trim();
      finalizedRef.current = true;
      if (words) {
        insertTranscript(words);
        insertedRef.current = true;
        setDictation("processing", "Transcript received — adding it to your draft…");
      } else {
        setDictation("stopped", "Dictation stopped — no words were recognized.");
      }
      try { recognition.stop(); } catch { /* the browser will still emit end */ }
    };

    recognition.onerror = (event) => {
      if (tearingDownRef.current) return;
      finalizedRef.current = true;
      recognitionRef.current = null;
      const message = dictationErrorMessage(String(event?.error ?? ""));
      setDictation("error", message);
      notify(message, "error");
    };

    recognition.onend = () => {
      if (tearingDownRef.current) return;
      recognitionRef.current = null;
      if (dictationStateRef.current === "error") return;
      setDictation(
        "stopped",
        insertedRef.current
          ? "Dictation stopped — transcript inserted at the cursor. Nothing was sent."
          : "Dictation stopped — no transcript was inserted.",
      );
    };

    recognitionRef.current = recognition;
    try {
      // The microphone is requested here and nowhere else: this function is
      // only reachable from the mic button's click handler.
      recognition.start();
    } catch (err) {
      recognitionRef.current = null;
      finalizedRef.current = true;
      const message = `Dictation could not start: ${errMessage(err)}`;
      setDictation("error", message);
      notify(message, "error");
    }
  }, [insertTranscript, notify, setDictation]);

  const stopDictation = useCallback(() => {
    const rec = recognitionRef.current;
    if (!rec) return;
    setDictation("processing", "Stopping dictation…");
    try {
      rec.stop();
    } catch {
      recognitionRef.current = null;
      setDictation("stopped", "Dictation stopped — no transcript was inserted.");
    }
  }, [setDictation]);

  const toggleDictation = useCallback(() => {
    if (!ctorRef.current) return; // unsupported control is disabled, never a no-op start
    if (recognitionRef.current) stopDictation();
    else startDictation();
  }, [startDictation, stopDictation]);

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
    patchChip(chip.id, { status: "uploading", error: undefined, progress: undefined });
    try {
      const payload = await buildUploadPayload(chip.file, targetBotId);
      const response = await postLibrary(payload, (percent) => patchChip(chip.id, { progress: percent }));
      const record = (response && typeof response === "object" ? ((response as Record<string, unknown>).file ?? response) : null) as Record<string, unknown> | null;
      const id = textOf(record?.id);
      if (!id) throw new Error("The bridge did not return a library file id.");
      const name = textOf(record?.name) || chip.file.name;
      patchChip(chip.id, { status: "done", libraryId: id, libraryName: name, progress: 100 });
      return { id, name };
    } catch (err) {
      patchChip(chip.id, { status: "failed", error: errMessage(err), progress: undefined });
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
  const dictating = dictationState === "listening" || dictationState === "processing";

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
                  <span className={`${s.uploadStatus} ${STATUS_CLASS[chip.status]}`}>
                    {STATUS_LABEL[chip.status]}{chip.status === "uploading" && typeof chip.progress === "number" ? ` ${chip.progress}%` : ""}
                  </span>
                  {chip.status === "uploading" && (
                    <span className={s.uploadMeter} role="progressbar" aria-label={`Uploading ${chip.file.name}`}
                      aria-valuemin={0} aria-valuemax={100} aria-valuenow={chip.progress ?? 0}>
                      <span style={{ width: `${chip.progress ?? 0}%` }} />
                    </span>
                  )}
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
          onChange={(e) => { textRef.current = e.target.value; setText(e.target.value); setSlashDismissed(false); }}
          onKeyDown={onKeyDown}
          onPaste={(e) => {
            if (e.clipboardData.files.length) { e.preventDefault(); addFiles(e.clipboardData.files); }
          }}
        />

        {dictationSupported === false && (
          <p className={`${s.dictationStatus} ${s.dictationUnavailable}`}>
            <Icon name="info" size={13} />
            <span>Dictation unavailable in this browser.</span>
          </p>
        )}
        {dictationSupported === true && dictationState !== "idle" && (
          <div
            className={`${s.dictationStatus} ${dictationState === "error" ? s.dictationError : ""}`}
            role={dictationState === "error" ? "alert" : "status"}
            aria-live={dictationState === "error" ? "assertive" : "polite"}
            aria-atomic="true"
          >
            <Icon name={dictationState === "error" ? "error" : dictationState === "stopped" ? "check" : "info"} size={13} />
            <span>{dictationMessage}</span>
          </div>
        )}

        <div className={s.toolbar}>
          <input
            ref={fileRef} type="file" multiple hidden tabIndex={-1}
            onChange={(e) => { addFiles(e.target.files); e.target.value = ""; }}
          />
          <IconButton label="Attach files" onClick={() => fileRef.current?.click()} title="Add files to the agent's library">
            <Icon name="attach" size={17} />
          </IconButton>
          {dictationSupported === true && (
            <IconButton
              label={dictating ? "Stop dictation" : "Dictate message"}
              className={`${s.micButton} ${dictationState === "listening" ? s.micActive : ""}`}
              active={dictationState === "listening"}
              title={dictating ? "Stop dictation" : "Dictate into the composer — nothing is sent automatically"}
              onClick={toggleDictation}
            >
              {dictating ? <Icon name="stop" size={17} /> : <MicIcon size={17} />}
            </IconButton>
          )}
          {dictationSupported === false && (
            <IconButton
              label="Dictation unavailable — speech recognition is not supported in this browser"
              className={s.micButton}
              title="Speech recognition is not supported in this browser"
              disabled
            >
              <MicIcon size={17} />
            </IconButton>
          )}
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
          {models && models.length > 0 && onModelChange ? (
            <label className={s.modelSelect} title="Model saved on this task by the bridge">
              <Icon name="spark" size={13} />
              <select className={s.select} value={modelLabel || models[0]}
                disabled={modelSaving} aria-label="Model for this task"
                onChange={(e) => onModelChange(e.target.value)}>
                {modelLabel && !models.includes(modelLabel) && <option value={modelLabel}>{modelLabel} (current)</option>}
                {models.map((m) => <option key={m} value={m}>{m}</option>)}
              </select>
            </label>
          ) : (modelLabel || providerLabel) ? (
            <span className={s.infoChip} title="No model catalog was reported by the bridge; change the model in settings">
              <Icon name="spark" size={13} />
              <span className={s.infoText}>{[providerLabel, modelLabel].filter(Boolean).join(" · ")}</span>
            </span>
          ) : null}
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
