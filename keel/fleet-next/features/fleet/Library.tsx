"use client";

import React, { useCallback, useMemo, useState } from "react";
import { Badge, Button, Dialog, EmptyState, IconButton, TextField } from "@/components/ui";
import { Icon } from "@/components/icons";
import { bridge, errMessage } from "@/lib/api";
import { useApp } from "@/lib/state";
import type { Bot, LibraryItem } from "@/lib/types";
import s from "./fleet.module.css";
import { ResourceNotice } from "./Bits";
import { fmtBytes, fmtDate, number, text, wrapped, type Resource } from "./support";

const MAX_FILE_BYTES = 2 * 1024 * 1024; // verified in keel/src/keel/fleet/library.py:18

function mimeOf(item: LibraryItem): string {
  return text((item as Record<string, unknown>).mime, text(item.type, "application/octet-stream"));
}
export default function Library({ libraryResource, bots, tasks }: {
  libraryResource: Resource<LibraryItem[] | { files?: LibraryItem[] }>;
  bots: Bot[];
  tasks: Array<{ id: string; title?: string }>;
}) {
  const { notify } = useApp();
  const [agentFilter, setAgentFilter] = useState("");
  const [taskFilter, setTaskFilter] = useState("");
  const [typeFilter, setTypeFilter] = useState("all");
  const [view, setView] = useState<"grid" | "list">("grid");
  const [previewId, setPreviewId] = useState<string | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<LibraryItem | null>(null);
  const [uploadOpen, setUploadOpen] = useState(false);
  const [busy, setBusy] = useState(false);

  const raw = libraryResource.data;
  const files = useMemo(() => wrapped<LibraryItem>(raw as Record<string, unknown>, "files"), [raw]);
  const usage = raw && !Array.isArray(raw) ? (raw as Record<string, unknown>).usage_bytes : undefined;
  const filtered = files.filter((f) => {
    if (agentFilter && text(f.bot_id) !== agentFilter) return false;
    if (taskFilter && text(f.task_id) !== taskFilter) return false;
    if (typeFilter !== "all") {
      const m = mimeOf(f);
      if (typeFilter === "image" && !m.startsWith("image/")) return false;
      if (typeFilter === "text" && !m.startsWith("text/")) return false;
      if (typeFilter === "pdf" && m !== "application/pdf") return false;
      if (typeFilter === "other" && (m.startsWith("image/") || m.startsWith("text/") || m === "application/pdf")) return false;
    }
    return true;
  });
  const preview = files.find((f) => f.id === previewId) ?? null;
  const viewResource = { ...libraryResource, data: raw === null ? null : files } as unknown as Resource<LibraryItem[]>;

  async function remove(file: LibraryItem) {
    setBusy(true);
    try {
      await bridge.deleteLibrary(file.id);
      notify(`Deleted ${text(file.name) || file.id} from the library.`, "success");
      setDeleteTarget(null);
      if (previewId === file.id) setPreviewId(null);
      libraryResource.reload();
    } catch (e) { notify(errMessage(e), "error"); }
    finally { setBusy(false); }
  }

  const totalBytes = files.reduce((sum, f) => sum + number(f.size, 0), 0);

  return (
    <div className={s.stack}>
      <div className={s.panelHead}>
        <div>
          <h3 className={s.panelTitle}>Library</h3>
          <p className={s.panelHint}>Files saved by agents or uploaded by you. Previews and downloads are served by the bridge; deletion is recoverable only if the bridge offers a restore route (it does not).</p>
        </div>
        <div className={s.row}>
          <Button size="sm" variant="secondary" aria-pressed={view === "grid"} onClick={() => setView("grid")}>Grid</Button>
          <Button size="sm" variant="secondary" aria-pressed={view === "list"} onClick={() => setView("list")}>List</Button>
          <Button variant="primary" disabled={bots.length === 0} onClick={() => setUploadOpen(true)}><Icon name="plus" size={16} /> Upload</Button>
        </div>
      </div>

      <ResourceNotice resource={viewResource} emptyTitle="Library is empty" emptyDescription="Upload a file, or let an agent save an artifact to the Fleet Library."
        emptyAction={<Button variant="primary" disabled={bots.length === 0} onClick={() => setUploadOpen(true)}><Icon name="plus" size={16} /> Upload file</Button>}>
        {(data) => (
          <div className={s.stack}>
            <div className={s.filters}>
              <select aria-label="Filter by agent" value={agentFilter} onChange={(e) => setAgentFilter(e.target.value)}>
                <option value="">All agents</option>
                {bots.map((b) => <option key={b.id} value={b.id}>{b.name || b.id}</option>)}
              </select>
              <select aria-label="Filter by task" value={taskFilter} onChange={(e) => setTaskFilter(e.target.value)}>
                <option value="">All tasks</option>
                {tasks.map((t) => <option key={t.id} value={t.id}>{t.title || t.id}</option>)}
              </select>
              <select aria-label="Filter by type" value={typeFilter} onChange={(e) => setTypeFilter(e.target.value)}>
                <option value="all">All types</option>
                <option value="image">Images</option>
                <option value="text">Text / code</option>
                <option value="pdf">PDF</option>
                <option value="other">Other</option>
              </select>
              <span className={s.hintNote}>{filtered.length} of {files.length} files · {fmtBytes(totalBytes)} shown{typeof usage === "number" ? ` · bridge quota usage ${fmtBytes(usage)}` : " · bridge quota not reported for this unfiltered view"}</span>
            </div>

            {filtered.length === 0 ? (
              <EmptyState title="No files match these filters" description="Clear a filter to see more files." />
            ) : view === "grid" ? (
              <div className={s.fileGrid}>
                {filtered.map((f) => (
                  <div className={s.fileCard} key={f.id}>
                    <div className={s.fileCardHead}>
                      <Icon name={mimeOf(f).startsWith("image/") ? "file" : "file"} size={16} />
                      <span className={s.fileName}>{text(f.name) || f.id}</span>
                    </div>
                    <div className={s.itemMeta}>{fmtBytes(number(f.size, 0))} · {fmtDate(f.created)}</div>
                    <div className={s.itemMeta}>{bots.find((b) => b.id === f.bot_id)?.name || text(f.bot_id, "unknown agent")}</div>
                    <div className={s.row}>
                      <Button size="sm" variant="ghost" onClick={() => setPreviewId(f.id)}>Preview</Button>
                      <a className="keel-btn keel-btn--ghost keel-btn--sm" href={bridge.downloadUrl(f.id)} download>Download</a>
                      <IconButton label={`Delete ${text(f.name) || f.id}`} onClick={() => setDeleteTarget(f)}><Icon name="trash" size={14} /></IconButton>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <div className={s.stack}>
                {filtered.map((f) => (
                  <div className={s.item} key={f.id}>
                    <Icon name="file" size={16} />
                    <div className={s.grow}>
                      <div className={s.itemTitle}>{text(f.name) || f.id}</div>
                      <div className={s.itemMeta}>{fmtBytes(number(f.size, 0))} · {fmtDate(f.created)} · {bots.find((b) => b.id === f.bot_id)?.name || text(f.bot_id, "unknown agent")}{f.task_id ? ` · task ${text(f.task_id)}` : ""}</div>
                    </div>
                    <div className={s.actions}>
                      <Button size="sm" variant="ghost" onClick={() => setPreviewId(f.id)}>Preview</Button>
                      <a className="keel-btn keel-btn--ghost keel-btn--sm" href={bridge.downloadUrl(f.id)} download>Download</a>
                      <Button size="sm" variant="danger" onClick={() => setDeleteTarget(f)}>Delete</Button>
                    </div>
                  </div>
                ))}
              </div>
            )}
            <p className={s.hintNote}>The bridge enforces {fmtBytes(MAX_FILE_BYTES)} per file and a per-agent quota; quota figures are shown only when the bridge reports them.</p>
          </div>
        )}
      </ResourceNotice>

      <UploadDialog open={uploadOpen} bots={bots} busy={busy} onClose={() => setUploadOpen(false)}
        onUpload={async (payload) => {
          setBusy(true);
          try {
            await bridge.uploadLibrary(payload);
            notify("File uploaded to the library.", "success");
            setUploadOpen(false);
            libraryResource.reload();
          } catch (e) { notify(errMessage(e), "error"); }
          finally { setBusy(false); }
        }} />

      <Dialog open={!!preview} onClose={() => setPreviewId(null)} title={text(preview?.name) || "Preview"} size="lg">
        {preview && (
          <div className={s.stack}>
            <iframe className={s.preview} src={bridge.previewUrl(preview.id)} title={`Preview of ${text(preview.name) || preview.id}`} sandbox="" />
            <div className={s.hintNote}>Every library file has a real preview route. The bridge serves images/PDFs inline and all other types as <code>text/plain</code> with a restrictive CSP, so active content cannot execute. If your browser cannot render a type inline, use Download.</div>
            <div className={s.row}>
              <a className="keel-btn keel-btn--secondary keel-btn--sm" href={bridge.previewUrl(preview.id)} target="_blank" rel="noopener noreferrer"><Icon name="external" size={14} /> Open preview in tab</a>
              <a className="keel-btn keel-btn--secondary keel-btn--sm" href={bridge.downloadUrl(preview.id)} download><Icon name="download" size={14} /> Download</a>
            </div>
          </div>
        )}
      </Dialog>

      <Dialog open={!!deleteTarget} onClose={() => setDeleteTarget(null)} title="Delete library file?"
        footer={<><Button variant="ghost" onClick={() => setDeleteTarget(null)}>Cancel</Button><Button variant="danger" loading={busy} onClick={() => deleteTarget && void remove(deleteTarget)}>Delete file</Button></>}>
        <p className={s.hintNote}>“{text(deleteTarget?.name)}” is removed by the bridge. This build has no restore endpoint for library deletions, so the action is permanent.</p>
      </Dialog>

    </div>
  );
}

function UploadDialog({ open, bots, busy, onClose, onUpload }: {
  open: boolean; bots: Bot[]; busy: boolean; onClose: () => void;
  onUpload: (payload: Record<string, unknown>) => void;
}) {
  const [bot, setBot] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [error, setError] = useState<string | null>(null);
  async function pick(f: File | null) {
    setError(null);
    if (!f) { setFile(null); return; }
    if (f.size > MAX_FILE_BYTES) { setError(`File exceeds the bridge limit of ${fmtBytes(MAX_FILE_BYTES)}.`); setFile(null); return; }
    setFile(f);
  }
  async function submit() {
    if (!file || !bot) return;
    try {
      const base64 = await new Promise<string>((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => resolve(String(reader.result).split(",")[1] ?? "");
        reader.onerror = () => reject(new Error("Could not read the file."));
        reader.readAsDataURL(file);
      });
      onUpload({ filename: file.name, bot_id: bot, content_base64: base64, mime: file.type || undefined });
    } catch (e) { setError(errMessage(e)); }
  }
  return (
    <Dialog open={open} onClose={onClose} title="Upload to library"
      footer={<><Button variant="ghost" onClick={onClose}>Cancel</Button><Button variant="primary" loading={busy} disabled={!file || !bot} onClick={() => void submit()}>Upload</Button></>}>
      <div className={s.stack}>
        <div className={s.field}><label htmlFor="upload-bot">Agent (required by bridge)</label><select id="upload-bot" value={bot} onChange={(e) => setBot(e.target.value)}><option value="">Choose an agent…</option>{bots.map((b) => <option key={b.id} value={b.id}>{b.name || b.id}</option>)}</select></div>
        <div className={s.field}><label htmlFor="upload-file">File</label><input id="upload-file" type="file" onChange={(e) => void pick(e.target.files?.[0] ?? null)} /></div>
        {error && <div className={s.errorText} role="alert">{error}</div>}
        <p className={s.hintNote}>Maximum {fmtBytes(MAX_FILE_BYTES)} per file. Content is base64-encoded in memory and sent to the bridge; nothing is stored by this browser.</p>
      </div>
    </Dialog>
  );
}
