"use client";

// Original, minimal line icons drawn for Keel. No third-party icon set, no
// branding copied from reference products. 24x24 stroke glyphs, currentColor.

import React from "react";

// Compatibility re-export: some feature modules import IconButton alongside
// Icon from this module. The single implementation lives in components/ui.tsx.
export { IconButton } from "./ui";

export type IconName =
  | "cowork" | "code" | "duet" | "fleet" | "settings" | "capabilities"
  | "plus" | "search" | "chevron" | "close" | "menu" | "panel" | "send"
  | "stop" | "attach" | "folder" | "file" | "terminal" | "browser"
  | "check" | "warning" | "error" | "info" | "clock" | "spark" | "refresh"
  | "more" | "trash" | "edit" | "download" | "play" | "pause" | "agents"
  | "tasks" | "library" | "routine" | "shield" | "sun" | "moon" | "command"
  | "user" | "bell" | "pin" | "link" | "copy" | "external" | "filter";

const PATHS: Record<IconName, React.ReactNode> = {
  cowork: <><path d="M4 5h16v11H9l-5 4V5Z" /><path d="M8 9h8M8 12h5" /></>,
  code: <><path d="m8 8-4 4 4 4M16 8l4 4-4 4M14 5l-4 14" /></>,
  duet: <><rect x="3" y="4" width="18" height="16" rx="2" /><path d="M12 4v16" /></>,
  fleet: <><circle cx="8" cy="8" r="3" /><circle cx="17" cy="7" r="2.4" /><path d="M3 20c0-3.3 2.2-5.5 5-5.5s5 2.2 5 5.5M14 14.8c3.8-.4 7 1.6 7 5.2" /></>,
  settings: <><circle cx="12" cy="12" r="3" /><path d="M19.4 15a1.6 1.6 0 0 0 .3 1.8l.1.1-2 2-1.1-.3a1.6 1.6 0 0 0-1.8.3l-.1.1-.2 2.8h-2.8l-.2-2.8a1.6 1.6 0 0 0-1.8-.3l-1.1.3-2-2 .1-.1a1.6 1.6 0 0 0 .3-1.8l-.1-.1L3 13.9V11l2.8-.2a1.6 1.6 0 0 0 .3-1.8l-.1-1.1 2-2 1.1.3a1.6 1.6 0 0 0 1.8-.3l.1-.1L11.2 3h2.8l.2 2.8a1.6 1.6 0 0 0 1.8.3l1.1-.3 2 2-.1 1.1a1.6 1.6 0 0 0-.3 1.8l.1.1L21 11v2.9Z" /></>,
  capabilities: <><path d="m12 3 2.1 5.6L20 9l-4.3 3.6L17 19l-5-3-5 3 1.3-6.4L4 9l5.9-.4L12 3Z" /></>,
  plus: <path d="M12 5v14M5 12h14" />,
  search: <><circle cx="11" cy="11" r="6.5" /><path d="m16 16 4.5 4.5" /></>,
  chevron: <path d="m9 6 6 6-6 6" />,
  close: <path d="M6 6l12 12M18 6 6 18" />,
  menu: <path d="M4 7h16M4 12h16M4 17h16" />,
  panel: <><rect x="3" y="4" width="18" height="16" rx="2" /><path d="M15 4v16" /></>,
  send: <path d="m4 12 16-8-6 16-2.5-6L4 12Z" />,
  stop: <rect x="6" y="6" width="12" height="12" rx="2" />,
  attach: <path d="M20 11.5 12.5 19a5 5 0 0 1-7-7l8-8a3.5 3.5 0 0 1 5 5l-8 8a2 2 0 0 1-3-3l7.5-7.5" />,
  folder: <path d="M3 7a2 2 0 0 1 2-2h5l2 2h7a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7Z" />,
  file: <><path d="M6 3h8l5 5v13H6V3Z" /><path d="M14 3v5h5" /></>,
  terminal: <><rect x="3" y="4" width="18" height="16" rx="2" /><path d="m7 9 3 3-3 3M13 15h4" /></>,
  browser: <><rect x="3" y="4" width="18" height="16" rx="2" /><path d="M3 9h18M6 6.5h.01M9 6.5h.01" /></>,
  check: <path d="m5 12 5 5L20 7" />,
  warning: <><path d="M12 4 2.5 20h19L12 4Z" /><path d="M12 10v4M12 17h.01" /></>,
  error: <><circle cx="12" cy="12" r="9" /><path d="M12 7v6M12 16h.01" /></>,
  info: <><circle cx="12" cy="12" r="9" /><path d="M12 11v6M12 7.5h.01" /></>,
  clock: <><circle cx="12" cy="12" r="9" /><path d="M12 7v5l3 2" /></>,
  spark: <path d="M12 3v5M12 16v5M3 12h5M16 12h5M6 6l3 3M15 15l3 3M18 6l-3 3M9 15l-3 3" />,
  refresh: <><path d="M20 6v5h-5M4 18v-5h5" /><path d="M6.5 9A7 7 0 0 1 18 7l2 4M17.5 15A7 7 0 0 1 6 17l-2-4" /></>,
  more: <><circle cx="5" cy="12" r="1.4" /><circle cx="12" cy="12" r="1.4" /><circle cx="19" cy="12" r="1.4" /></>,
  trash: <><path d="M4 7h16M9 7V4h6v3M6 7l1 14h10l1-14M10 11v6M14 11v6" /></>,
  edit: <><path d="m4 20 4-1 12-12-3-3L5 16l-1 4Z" /><path d="m14 6 3 3" /></>,
  download: <path d="M12 3v12m0 0 4-4m-4 4-4-4M4 19h16" />,
  play: <path d="m8 5 11 7-11 7V5Z" />,
  pause: <path d="M8 5h3v14H8zM14 5h3v14h-3z" />,
  agents: <><circle cx="12" cy="7" r="3" /><path d="M5 21c0-4 3-6 7-6s7 2 7 6" /></>,
  tasks: <><rect x="4" y="4" width="16" height="16" rx="2" /><path d="m8 12 2.5 2.5L16 9" /></>,
  library: <><path d="M4 4h5v16H4zM10 4h5v16h-5zM17 5l3 1-3 13-2-.7" /></>,
  routine: <><circle cx="12" cy="12" r="9" /><path d="M12 7v5l4 2" /></>,
  shield: <path d="M12 3 4.5 6v6c0 4.5 3 7.8 7.5 9 4.5-1.2 7.5-4.5 7.5-9V6L12 3Z" />,
  sun: <><circle cx="12" cy="12" r="4" /><path d="M12 2v3M12 19v3M2 12h3M19 12h3M5 5l2 2M17 17l2 2M19 5l-2 2M7 17l-2 2" /></>,
  moon: <path d="M20 14.5A8.5 8.5 0 0 1 9.5 4 8.5 8.5 0 1 0 20 14.5Z" />,
  command: <path d="M9 7a3 3 0 1 0-3 3h12a3 3 0 1 0-3-3v10a3 3 0 1 0 3-3H6a3 3 0 1 0 3 3V7Z" />,
  user: <><circle cx="12" cy="8" r="4" /><path d="M4 21c0-4.5 3.6-7 8-7s8 2.5 8 7" /></>,
  bell: <><path d="M6 9a6 6 0 0 1 12 0c0 6 2 7 2 7H4s2-1 2-7Z" /><path d="M10 19a2 2 0 0 0 4 0" /></>,
  pin: <path d="M9 3h6l-1 6 3 3v2H7v-2l3-3-1-6ZM12 14v7" />,
  link: <><path d="M10 14a4 4 0 0 0 6 .5l2-2a4 4 0 0 0-5.7-5.7l-1.2 1.2" /><path d="M14 10a4 4 0 0 0-6-.5l-2 2A4 4 0 0 0 11.7 17l1.2-1.2" /></>,
  copy: <><rect x="8" y="8" width="12" height="12" rx="2" /><path d="M16 8V5a2 2 0 0 0-2-2H5a2 2 0 0 0-2 2v9a2 2 0 0 0 2 2h3" /></>,
  external: <><path d="M14 4h6v6M20 4l-9 9" /><path d="M20 14v5a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h5" /></>,
  filter: <path d="M3 5h18l-7 8v6l-4 2v-8L3 5Z" />,
};

export function Icon({ name, size = 18, className = "", ...rest }: React.SVGAttributes<SVGSVGElement> & { name: IconName; size?: number }) {
  return (
    <svg
      viewBox="0 0 24 24" width={size} height={size} fill="none" stroke="currentColor"
      strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"
      className={`keel-icon ${className}`.trim()} {...rest}
    >
      {PATHS[name]}
    </svg>
  );
}

export function KeelMark({ size = 28 }: { size?: number }) {
  return (
    <svg viewBox="0 0 32 32" width={size} height={size} aria-hidden="true" className="keel-mark">
      <path d="M8 4 4 16l4 12" fill="none" stroke="currentColor" strokeWidth="2.6" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M18 5 9 27" fill="none" stroke="currentColor" strokeWidth="2.6" strokeLinecap="round" />
      <circle cx="24" cy="8" r="2" fill="currentColor" />
    </svg>
  );
}
