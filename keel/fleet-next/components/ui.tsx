"use client";

// Shared primitives. Build each control once with documented variants,
// keyboard behaviour, focus/disabled/loading states and responsive rules.
// Feature modules must use these instead of one-off styles.

import React, { useEffect, useRef, useState } from "react";

type ButtonVariant = "primary" | "secondary" | "ghost" | "danger";

export function Button({
  children, variant = "secondary", size = "md", loading = false, disabled = false,
  className = "", ...rest
}: React.ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: ButtonVariant; size?: "sm" | "md" | "lg"; loading?: boolean;
}) {
  return (
    <button
      {...rest}
      disabled={disabled || loading}
      aria-busy={loading || undefined}
      className={`keel-btn keel-btn--${variant} keel-btn--${size} ${className}`.trim()}
    >
      {loading && <span className="keel-spinner" aria-hidden="true" />}
      {children}
    </button>
  );
}

export function IconButton({
  label, children, className = "", active = false, ...rest
}: React.ButtonHTMLAttributes<HTMLButtonElement> & { label: string; active?: boolean }) {
  return (
    <button
      {...rest}
      aria-label={label}
      title={rest.title ?? label}
      aria-pressed={active || undefined}
      className={`keel-icon-btn ${active ? "is-active" : ""} ${className}`.trim()}
    >
      {children}
    </button>
  );
}

export function SegmentedControl<T extends string>({
  value, options, onChange, label,
}: {
  value: T; options: Array<{ value: T; label: string; icon?: React.ReactNode }>;
  onChange: (v: T) => void; label?: string;
}) {
  return (
    <div className="keel-segmented" role="tablist" aria-label={label}>
      {options.map((o) => (
        <button
          key={o.value}
          role="tab"
          aria-selected={value === o.value}
          className={value === o.value ? "is-active" : ""}
          onClick={() => onChange(o.value)}
          type="button"
        >
          {o.icon}{o.label}
        </button>
      ))}
    </div>
  );
}

export function Badge({
  children, tone = "neutral", dot = false,
}: { children: React.ReactNode; tone?: "neutral" | "success" | "warning" | "danger" | "info" | "accent"; dot?: boolean }) {
  return <span className={`keel-badge keel-badge--${tone}`}>{dot && <span className="keel-dot" aria-hidden="true" />}{children}</span>;
}

export function StatusDot({ tone = "neutral", label }: { tone?: "neutral" | "success" | "warning" | "danger" | "info"; label?: string }) {
  return <span className={`keel-status-dot keel-status-dot--${tone}`} role="img" aria-label={label ?? tone}>{label && <span className="sr-only">{label}</span>}</span>;
}

export function Card({ children, className = "", as: Tag = "div", ...rest }: React.HTMLAttributes<HTMLDivElement> & { as?: "div" | "section" | "article" }) {
  return <Tag className={`keel-card ${className}`.trim()} {...rest}>{children}</Tag>;
}

export function EmptyState({
  icon, title, description, action,
}: { icon?: React.ReactNode; title: string; description?: string; action?: React.ReactNode }) {
  return (
    <div className="keel-empty">
      {icon && <div className="keel-empty__icon" aria-hidden="true">{icon}</div>}
      <h3>{title}</h3>
      {description && <p>{description}</p>}
      {action && <div className="keel-empty__action">{action}</div>}
    </div>
  );
}

export function Skeleton({ width, height = 14, className = "" }: { width?: number | string; height?: number | string; className?: string }) {
  return <span className={`keel-skeleton ${className}`.trim()} style={{ width, height }} aria-hidden="true" />;
}

export function Spinner({ label = "Loading" }: { label?: string }) {
  return <span className="keel-spinner keel-spinner--lg" role="status" aria-label={label} />;
}

export function Toggle({
  checked, onChange, label, description, disabled = false,
}: { checked: boolean; onChange: (v: boolean) => void; label: string; description?: string; disabled?: boolean }) {
  return (
    <label className={`keel-toggle ${disabled ? "is-disabled" : ""}`}>
      <input type="checkbox" checked={checked} disabled={disabled} onChange={(e) => onChange(e.target.checked)} />
      <span className="keel-toggle__track" aria-hidden="true"><span className="keel-toggle__thumb" /></span>
      <span className="keel-toggle__text"><span className="keel-toggle__label">{label}</span>{description && <span className="keel-toggle__desc">{description}</span>}</span>
    </label>
  );
}

export function TextField({
  label, hint, error, className = "", ...rest
}: React.InputHTMLAttributes<HTMLInputElement> & { label?: string; hint?: string; error?: string }) {
  const id = rest.id ?? React.useId();
  return (
    <div className={`keel-field ${className}`}>
      {label && <label htmlFor={id}>{label}</label>}
      <input id={id} {...rest} aria-invalid={error ? true : undefined} aria-describedby={error ? `${id}-err` : hint ? `${id}-hint` : undefined} />
      {error ? <span id={`${id}-err`} className="keel-field__err" role="alert">{error}</span> : hint ? <span id={`${id}-hint`} className="keel-field__hint">{hint}</span> : null}
    </div>
  );
}

export function Textarea({
  label, className = "", ...rest
}: React.TextareaHTMLAttributes<HTMLTextAreaElement> & { label?: string }) {
  const id = rest.id ?? React.useId();
  return (
    <div className={`keel-field ${className}`}>
      {label && <label htmlFor={id}>{label}</label>}
      <textarea id={id} {...rest} />
    </div>
  );
}

export function Tabs<T extends string>({
  tabs, value, onChange, label,
}: { tabs: Array<{ value: T; label: string; icon?: React.ReactNode }>; value: T; onChange: (v: T) => void; label?: string }) {
  return (
    <div className="keel-tabs" role="tablist" aria-label={label}>
      {tabs.map((t) => (
        <button key={t.value} role="tab" aria-selected={value === t.value} className={value === t.value ? "is-active" : ""} onClick={() => onChange(t.value)} type="button">
          {t.icon}{t.label}
        </button>
      ))}
    </div>
  );
}

export function Dialog({
  open, onClose, title, children, footer, size = "md",
}: { open: boolean; onClose: () => void; title: string; children: React.ReactNode; footer?: React.ReactNode; size?: "sm" | "md" | "lg" }) {
  const panel = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const prev = document.activeElement as HTMLElement | null;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
      if (e.key === "Tab" && panel.current) {
        const items = panel.current.querySelectorAll<HTMLElement>('button, [href], input, textarea, select, [tabindex]:not([tabindex="-1"])');
        if (!items.length) return;
        const first = items[0], last = items[items.length - 1];
        if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
        else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
      }
    };
    document.addEventListener("keydown", onKey);
    panel.current?.querySelector<HTMLElement>("button, [href], input, textarea")?.focus();
    return () => { document.removeEventListener("keydown", onKey); prev?.focus?.(); };
  }, [open, onClose]);
  if (!open) return null;
  return (
    <div className="keel-overlay" onMouseDown={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div className={`keel-dialog keel-dialog--${size}`} role="dialog" aria-modal="true" aria-label={title} ref={panel}>
        <header className="keel-dialog__head"><h2>{title}</h2><IconButton label="Close dialog" onClick={onClose}>✕</IconButton></header>
        <div className="keel-dialog__body">{children}</div>
        {footer && <footer className="keel-dialog__foot">{footer}</footer>}
      </div>
    </div>
  );
}

export function Tooltip({ label, children }: { label: string; children: React.ReactNode }) {
  return <span className="keel-tooltip" tabIndex={0} aria-label={label}><span className="keel-tooltip__bubble" role="tooltip">{label}</span>{children}</span>;
}

export function Progress({ value, label }: { value: number; label?: string }) {
  const pct = Math.max(0, Math.min(100, value));
  return (
    <div className="keel-progress" role="progressbar" aria-valuenow={pct} aria-valuemin={0} aria-valuemax={100} aria-label={label}>
      <span style={{ width: `${pct}%` }} />
    </div>
  );
}

export function SectionTitle({ children, action }: { children: React.ReactNode; action?: React.ReactNode }) {
  return <div className="keel-section-title"><h4>{children}</h4>{action}</div>;
}

/** Resizable divider used by the shell and multi-pane workspaces. */
export function ResizeHandle({ onDrag, orientation = "vertical", label = "Resize panel" }: {
  onDrag: (delta: number) => void; orientation?: "vertical" | "horizontal"; label?: string;
}) {
  const start = useRef<number | null>(null);
  return (
    <div
      className={`keel-resize keel-resize--${orientation}`}
      role="separator"
      aria-orientation={orientation === "vertical" ? "vertical" : "horizontal"}
      aria-label={label}
      tabIndex={0}
      onKeyDown={(e) => {
        const step = e.shiftKey ? 24 : 8;
        if (orientation === "vertical" && (e.key === "ArrowLeft" || e.key === "ArrowRight")) {
          e.preventDefault(); onDrag(e.key === "ArrowRight" ? step : -step);
        } else if (orientation === "horizontal" && (e.key === "ArrowUp" || e.key === "ArrowDown")) {
          e.preventDefault(); onDrag(e.key === "ArrowDown" ? step : -step);
        }
      }}
      onPointerDown={(e) => {
        e.currentTarget.setPointerCapture(e.pointerId);
        start.current = orientation === "vertical" ? e.clientX : e.clientY;
      }}
      onPointerMove={(e) => {
        if (start.current === null) return;
        const cur = orientation === "vertical" ? e.clientX : e.clientY;
        onDrag(cur - start.current);
        start.current = cur;
      }}
      onPointerUp={() => { start.current = null; }}
      onPointerCancel={() => { start.current = null; }}
    />
  );
}
