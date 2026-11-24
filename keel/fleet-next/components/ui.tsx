"use client";

// Shared primitives. Build each control once with documented variants,
// keyboard behaviour, focus/disabled/loading states and responsive rules.
// Feature modules must use these instead of one-off styles.
//
// Accessibility notes: native controls are used wherever possible; every
// control exposes a programmatic name, custom widgets expose their state via
// ARIA, and composite widgets implement the keyboard behaviour from the ARIA
// authoring practices (roving tabindex, focus trap, arrow-key adjustment).

import React, { useEffect, useRef, useState } from "react";

type ButtonVariant = "primary" | "secondary" | "ghost" | "danger";

/** Elements that can receive keyboard focus inside a modal or other widget. */
const FOCUSABLE_SELECTOR = [
  "a[href]",
  "button:not([disabled])",
  "input:not([disabled])",
  "textarea:not([disabled])",
  "select:not([disabled])",
  '[tabindex]:not([tabindex="-1"])',
].join(", ");

function getFocusable(root: HTMLElement): HTMLElement[] {
  return Array.from(root.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR)).filter((el) =>
    el.getAttribute("aria-hidden") !== "true" &&
    (el.getClientRects().length > 0 || el.offsetParent !== null)
  );
}

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
      {/* Loading is a state change, not just a colour/spinner change. */}
      {loading && <span className="sr-only">Loading</span>}
    </button>
  );
}

export function IconButton({
  label, children, className = "", active = false, ...rest
}: React.ButtonHTMLAttributes<HTMLButtonElement> & { label: string; active?: boolean }) {
  return (
    <button
      {...rest}
      type={rest.type ?? "button"}
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
  const refs = useRef<Array<HTMLButtonElement | null>>([]);
  const selectedIndex = options.findIndex((o) => o.value === value);
  const activeIndex = selectedIndex >= 0 ? selectedIndex : 0;

  const selectAt = (index: number) => {
    if (!options.length) return;
    const next = (index + options.length) % options.length;
    const option = options[next];
    if (!option) return;
    onChange(option.value);
    refs.current[next]?.focus();
  };

  return (
    <div className="keel-segmented" role="tablist" aria-label={label ?? "Options"}>
      {options.map((o, i) => (
        <button
          key={o.value}
          ref={(el) => { refs.current[i] = el; }}
          role="tab"
          aria-selected={value === o.value}
          tabIndex={i === activeIndex ? 0 : -1}
          className={value === o.value ? "is-active" : ""}
          onClick={() => onChange(o.value)}
          onKeyDown={(e) => {
            if (e.key === "ArrowRight" || e.key === "ArrowDown") { e.preventDefault(); selectAt(i + 1); }
            else if (e.key === "ArrowLeft" || e.key === "ArrowUp") { e.preventDefault(); selectAt(i - 1); }
            else if (e.key === "Home") { e.preventDefault(); selectAt(0); }
            else if (e.key === "End") { e.preventDefault(); selectAt(options.length - 1); }
          }}
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
  // The status is always carried by the text children; the dot is decorative.
  return <span className={`keel-badge keel-badge--${tone}`}>{dot && <span className="keel-dot" aria-hidden="true" />}{children}</span>;
}

export function StatusDot({ tone = "neutral", label }: { tone?: "neutral" | "success" | "warning" | "danger" | "info"; label?: string }) {
  // role="img" makes descendants presentational, so the visible name lives in
  // aria-label rather than in a second, hidden copy of the text.
  return (
    <span
      className={`keel-status-dot keel-status-dot--${tone}`}
      role="img"
      aria-label={label ?? `${tone} status`}
      title={label}
    />
  );
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
  return (
    <span
      className="keel-spinner keel-spinner--lg"
      role="status"
      aria-live="polite"
      aria-atomic="true"
      aria-label={label}
    />
  );
}

export function Toggle({
  checked, onChange, label, description, disabled = false, id: idProp,
}: {
  checked: boolean; onChange: (v: boolean) => void; label: string;
  description?: string; disabled?: boolean; id?: string;
}) {
  const generatedId = React.useId();
  const id = idProp ?? generatedId;
  const descId = `${id}-desc`;
  return (
    <label className={`keel-toggle ${disabled ? "is-disabled" : ""}`}>
      <input
        id={id}
        type="checkbox"
        checked={checked}
        disabled={disabled}
        onChange={(e) => onChange(e.target.checked)}
        aria-label={label}
        aria-describedby={description ? descId : undefined}
      />
      <span className="keel-toggle__track" aria-hidden="true"><span className="keel-toggle__thumb" /></span>
      <span className="keel-toggle__text">
        {/* The input already carries this accessible name; do not duplicate it. */}
        <span className="keel-toggle__label" aria-hidden="true">{label}</span>
        {description && <span id={descId} className="keel-toggle__desc">{description}</span>}
      </span>
    </label>
  );
}

export function TextField({
  label, hint, error, className = "", ...rest
}: React.InputHTMLAttributes<HTMLInputElement> & { label?: string; hint?: string; error?: string }) {
  const generatedId = React.useId();
  const id = rest.id ?? generatedId;
  const hintId = `${id}-hint`;
  const errId = `${id}-err`;
  const describedBy = [
    rest["aria-describedby"],
    hint ? hintId : undefined,
    error ? errId : undefined,
  ].filter(Boolean).join(" ") || undefined;
  return (
    <div className={`keel-field ${className}`}>
      {label && <label htmlFor={id}>{label}</label>}
      <input
        {...rest}
        id={id}
        aria-invalid={error ? true : rest["aria-invalid"]}
        aria-describedby={describedBy}
      />
      {hint && <span id={hintId} className="keel-field__hint">{hint}</span>}
      {error && <span id={errId} className="keel-field__err" role="alert">{error}</span>}
    </div>
  );
}

export function Textarea({
  label, hint, error, className = "", ...rest
}: React.TextareaHTMLAttributes<HTMLTextAreaElement> & { label?: string; hint?: string; error?: string }) {
  const generatedId = React.useId();
  const id = rest.id ?? generatedId;
  const hintId = `${id}-hint`;
  const errId = `${id}-err`;
  const describedBy = [
    rest["aria-describedby"],
    hint ? hintId : undefined,
    error ? errId : undefined,
  ].filter(Boolean).join(" ") || undefined;
  return (
    <div className={`keel-field ${className}`}>
      {label && <label htmlFor={id}>{label}</label>}
      <textarea
        {...rest}
        id={id}
        aria-invalid={error ? true : rest["aria-invalid"]}
        aria-describedby={describedBy}
      />
      {hint && <span id={hintId} className="keel-field__hint">{hint}</span>}
      {error && <span id={errId} className="keel-field__err" role="alert">{error}</span>}
    </div>
  );
}

export function Tabs<T extends string>({
  tabs, value, onChange, label,
}: { tabs: Array<{ value: T; label: string; icon?: React.ReactNode }>; value: T; onChange: (v: T) => void; label?: string }) {
  const refs = useRef<Array<HTMLButtonElement | null>>([]);
  const selectedIndex = tabs.findIndex((t) => t.value === value);
  const activeIndex = selectedIndex >= 0 ? selectedIndex : 0;

  const selectAt = (index: number) => {
    if (!tabs.length) return;
    const next = (index + tabs.length) % tabs.length;
    const tab = tabs[next];
    if (!tab) return;
    onChange(tab.value);
    refs.current[next]?.focus();
  };

  return (
    <div className="keel-tabs" role="tablist" aria-label={label ?? "Tabs"}>
      {tabs.map((t, i) => (
        <button
          key={t.value}
          ref={(el) => { refs.current[i] = el; }}
          role="tab"
          aria-selected={value === t.value}
          tabIndex={i === activeIndex ? 0 : -1}
          className={value === t.value ? "is-active" : ""}
          onClick={() => onChange(t.value)}
          onKeyDown={(e) => {
            if (e.key === "ArrowRight" || e.key === "ArrowDown") { e.preventDefault(); selectAt(i + 1); }
            else if (e.key === "ArrowLeft" || e.key === "ArrowUp") { e.preventDefault(); selectAt(i - 1); }
            else if (e.key === "Home") { e.preventDefault(); selectAt(0); }
            else if (e.key === "End") { e.preventDefault(); selectAt(tabs.length - 1); }
          }}
          type="button"
        >
          {t.icon}{t.label}
        </button>
      ))}
    </div>
  );
}

export function Dialog({
  open, onClose, title, description, children, footer, size = "md",
}: {
  open: boolean; onClose: () => void; title: string; children: React.ReactNode;
  description?: string; footer?: React.ReactNode; size?: "sm" | "md" | "lg";
}) {
  const panel = useRef<HTMLDivElement>(null);
  // Keep the latest callback without re-running the focus-trap effect on every
  // render (call sites usually pass a fresh inline arrow function).
  const closeRef = useRef(onClose);
  const restoreRef = useRef<HTMLElement | null>(null);
  const titleId = React.useId();
  const descId = React.useId();

  useEffect(() => { closeRef.current = onClose; }, [onClose]);

  useEffect(() => {
    if (!open) return;
    restoreRef.current = document.activeElement as HTMLElement | null;
    const root = panel.current;

    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.preventDefault();
        e.stopPropagation();
        closeRef.current();
        return;
      }
      if (e.key !== "Tab" || !root) return;
      const items = getFocusable(root);
      if (!items.length) { e.preventDefault(); root.focus(); return; }
      const first = items[0];
      const last = items[items.length - 1];
      const active = document.activeElement as HTMLElement | null;
      if (!root.contains(active)) {
        e.preventDefault();
        (e.shiftKey ? last : first).focus();
      } else if (e.shiftKey && active === first) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && active === last) {
        e.preventDefault();
        first.focus();
      }
    };

    document.addEventListener("keydown", onKey, true);
    const focusTimer = window.setTimeout(() => {
      const items = root ? getFocusable(root) : [];
      (items[0] ?? root)?.focus();
    }, 0);

    return () => {
      window.clearTimeout(focusTimer);
      document.removeEventListener("keydown", onKey, true);
      const previous = restoreRef.current;
      if (previous && document.contains(previous)) previous.focus();
      restoreRef.current = null;
    };
  }, [open]);

  if (!open) return null;
  return (
    <div className="keel-overlay" onMouseDown={(e) => { if (e.target === e.currentTarget) closeRef.current(); }}>
      <div
        className={`keel-dialog keel-dialog--${size}`}
        role="dialog"
        aria-modal="true"
        aria-label={title}
        aria-labelledby={titleId}
        aria-describedby={description ? descId : undefined}
        ref={panel}
        tabIndex={-1}
      >
        <header className="keel-dialog__head"><h2 id={titleId}>{title}</h2><IconButton label="Close dialog" onClick={() => closeRef.current()}>✕</IconButton></header>
        <div className="keel-dialog__body">
          {description && <p id={descId} className="sr-only">{description}</p>}
          {children}
        </div>
        {footer && <footer className="keel-dialog__foot">{footer}</footer>}
      </div>
    </div>
  );
}

export function Tooltip({ label, children }: { label: string; children: React.ReactNode }) {
  const [visible, setVisible] = useState(false);
  const id = React.useId();
  const bubble = (
    <span className="keel-tooltip__bubble" role="tooltip" id={id} aria-hidden={!visible}>{label}</span>
  );
  let trigger: React.ReactNode;
  if (React.isValidElement(children)) {
    const child = children as React.ReactElement<{ "aria-describedby"?: string }>;
    const existing = child.props["aria-describedby"];
    trigger = React.cloneElement(child, {
      "aria-describedby": [existing, id].filter(Boolean).join(" ") || undefined,
    });
  } else {
    trigger = <span tabIndex={0} aria-label={label} aria-describedby={id}>{children}</span>;
  }
  return (
    <span
      className={`keel-tooltip ${visible ? "is-visible" : ""}`.trim()}
      onMouseEnter={() => setVisible(true)}
      onMouseLeave={() => setVisible(false)}
      onFocus={() => setVisible(true)}
      onBlur={(e) => {
        if (!e.currentTarget.contains(e.relatedTarget as Node | null)) setVisible(false);
      }}
    >
      {bubble}
      {trigger}
    </span>
  );
}

export function Progress({ value, label }: { value: number; label?: string }) {
  const pct = Math.max(0, Math.min(100, value));
  return (
    <div
      className="keel-progress"
      role="progressbar"
      aria-valuenow={pct}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuetext={`${Math.round(pct)}%`}
      aria-label={label ?? "Progress"}
    >
      <span style={{ width: `${pct}%` }} aria-hidden="true" />
    </div>
  );
}

export function SectionTitle({ children, action }: { children: React.ReactNode; action?: React.ReactNode }) {
  return <div className="keel-section-title"><h4>{children}</h4>{action}</div>;
}

/** Resizable divider used by the shell and multi-pane workspaces. */
export function ResizeHandle({
  onDrag, orientation = "vertical", label = "Resize panel", value, min, max,
}: {
  onDrag: (delta: number) => void; orientation?: "vertical" | "horizontal"; label?: string;
  value?: number; min?: number; max?: number;
}) {
  const start = useRef<number | null>(null);
  const hasRange = typeof value === "number" && typeof min === "number" && typeof max === "number";
  const release = (e: React.PointerEvent<HTMLDivElement>) => {
    start.current = null;
    try { e.currentTarget.releasePointerCapture(e.pointerId); } catch { /* pointer already released */ }
  };
  return (
    <div
      className={`keel-resize keel-resize--${orientation}`}
      role="separator"
      aria-orientation={orientation === "vertical" ? "vertical" : "horizontal"}
      aria-label={label}
      aria-valuenow={value}
      aria-valuemin={min}
      aria-valuemax={max}
      tabIndex={0}
      onKeyDown={(e) => {
        const step = e.shiftKey ? 24 : 8;
        if (orientation === "vertical" && (e.key === "ArrowLeft" || e.key === "ArrowRight")) {
          e.preventDefault(); onDrag(e.key === "ArrowRight" ? step : -step);
        } else if (orientation === "horizontal" && (e.key === "ArrowUp" || e.key === "ArrowDown")) {
          e.preventDefault(); onDrag(e.key === "ArrowDown" ? step : -step);
        } else if (hasRange && e.key === "Home") {
          e.preventDefault(); onDrag(min - value);
        } else if (hasRange && e.key === "End") {
          e.preventDefault(); onDrag(max - value);
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
      onPointerUp={release}
      onPointerCancel={release}
      onLostPointerCapture={() => { start.current = null; }}
    />
  );
}
