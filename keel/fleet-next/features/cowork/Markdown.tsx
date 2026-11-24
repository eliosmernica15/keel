"use client";

// Small, dependency-free Markdown-ish renderer for durable agent messages.
// It produces React nodes (never innerHTML), so row content cannot inject HTML.

import React from "react";
import s from "./cowork.module.css";

const INLINE = /(`[^`]+`|\*\*[^*]+\*\*|\*[^*]+\*|\[[^\]]+\]\([^)]+\))/g;

function inline(text: string, keyPrefix: string): React.ReactNode[] {
  const out: React.ReactNode[] = [];
  let cursor = 0;
  let m: RegExpExecArray | null;
  INLINE.lastIndex = 0;
  while ((m = INLINE.exec(text)) !== null) {
    if (m.index > cursor) out.push(text.slice(cursor, m.index));
    const token = m[0];
    const k = `${keyPrefix}-${m.index}`;
    if (token.startsWith("`") && token.endsWith("`")) {
      out.push(<code key={k} className={s.inlineCode}>{token.slice(1, -1)}</code>);
    } else if (token.startsWith("**")) {
      out.push(<strong key={k}>{token.slice(2, -2)}</strong>);
    } else if (token.startsWith("*")) {
      out.push(<em key={k}>{token.slice(1, -1)}</em>);
    } else {
      const link = /^\[([^\]]+)\]\(([^)]+)\)$/.exec(token);
      if (link) {
        const href = link[2];
        const safe = /^(https?:\/\/|\/|#)/i.test(href) ? href : "#";
        out.push(<a key={k} href={safe} target="_blank" rel="noreferrer" className={s.link}>{link[1]}</a>);
      } else out.push(token);
    }
    cursor = m.index + token.length;
  }
  if (cursor < text.length) out.push(text.slice(cursor));
  return out;
}

export function Markdown({ text }: { text: string }) {
  const segments: React.ReactNode[] = [];
  const fence = /```([^\n`]*)\n?([\s\S]*?)```/g;
  let last = 0;
  let match: RegExpExecArray | null;
  let blockIndex = 0;
  while ((match = fence.exec(text)) !== null) {
    if (match.index > last) {
      segments.push(<Prose key={`p-${blockIndex++}`} text={text.slice(last, match.index)} />);
    }
    const lang = match[1].trim();
    const code = match[2];
    segments.push(
      <div className={s.codeBlock} key={`c-${blockIndex++}`}>
        <div className={s.codeHead}>
          <span>{lang || "code"}</span>
          <button
            type="button"
            className={s.codeCopy}
            aria-label="Copy code block"
            onClick={() => { void navigator.clipboard?.writeText(code); }}
          >Copy</button>
        </div>
        <pre><code>{code.replace(/\n$/, "")}</code></pre>
      </div>,
    );
    last = match.index + match[0].length;
  }
  if (last < text.length) segments.push(<Prose key={`p-${blockIndex++}`} text={text.slice(last)} />);
  return <div className={s.markdown}>{segments}</div>;
}

function Prose({ text }: { text: string }) {
  if (!text.trim()) return null;
  const blocks = text.split(/\n{2,}/);
  return (
    <>
      {blocks.map((block, bi) => {
        const lines = block.split("\n");
        if (lines.every((l) => /^\s*[-*]\s+/.test(l))) {
          return (
            <ul key={bi} className={s.list}>
              {lines.map((l, li) => <li key={li}>{inline(l.replace(/^\s*[-*]\s+/, ""), `b${bi}l${li}`)}</li>)}
            </ul>
          );
        }
        const heading = /^\s*(#{1,4})\s+(.*)$/.exec(lines[0]);
        if (heading && lines.length === 1) {
          return <h4 key={bi} className={s.mdHeading}>{inline(heading[2], `b${bi}`)}</h4>;
        }
        return (
          <p key={bi} className={s.para}>
            {lines.map((l, li) => (
              <React.Fragment key={li}>{li > 0 && <br />}{inline(l, `b${bi}l${li}`)}</React.Fragment>
            ))}
          </p>
        );
      })}
    </>
  );
}
