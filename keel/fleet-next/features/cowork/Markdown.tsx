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

function cells(line: string): string[] {
  const parts = line.trim().replace(/^\|/, "").replace(/\|$/, "").split("|");
  return parts.map((p) => p.trim());
}

const SEPARATOR = /^\s*:?-{3,}:?\s*$/;

function isTable(lines: string[]): boolean {
  if (lines.length < 2 || !lines[0].includes("|")) return false;
  const divider = cells(lines[1]);
  return divider.length > 0 && divider.every((c) => SEPARATOR.test(c));
}

function tableBlock(lines: string[], key: string): React.ReactNode {
  const head = cells(lines[0]);
  const aligns = cells(lines[1]).map((c) => c.startsWith(":") && c.endsWith(":") ? "center" : c.endsWith(":") ? "right" : c.startsWith(":") ? "left" : undefined);
  const rows = lines.slice(2).map(cells);
  return (
    <div className={s.tableWrap} key={key}>
      <table className={s.mdTable}>
        <thead><tr>{head.map((cell, i) => <th key={i} style={aligns[i] ? { textAlign: aligns[i] } : undefined}>{inline(cell, `${key}h${i}`)}</th>)}</tr></thead>
        <tbody>
          {rows.map((row, ri) => (
            <tr key={ri}>{head.map((_, ci) => <td key={ci} style={aligns[ci] ? { textAlign: aligns[ci] } : undefined}>{inline(row[ci] ?? "", `${key}r${ri}c${ci}`)}</td>)}</tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Prose({ text }: { text: string }) {
  if (!text.trim()) return null;
  const blocks = text.split(/\n{2,}/);
  return (
    <>
      {blocks.map((block, bi) => {
        const lines = block.split("\n");
        const key = `b${bi}`;
        if (isTable(lines)) return tableBlock(lines, key);
        if (lines.every((l) => /^\s*[-*]\s+/.test(l))) {
          return (
            <ul key={key} className={s.list}>
              {lines.map((l, li) => <li key={li}>{inline(l.replace(/^\s*[-*]\s+/, ""), `${key}l${li}`)}</li>)}
            </ul>
          );
        }
        if (lines.every((l) => /^\s*\d+[.)]\s+/.test(l))) {
          return (
            <ol key={key} className={s.list}>
              {lines.map((l, li) => <li key={li}>{inline(l.replace(/^\s*\d+[.)]\s+/, ""), `${key}l${li}`)}</li>)}
            </ol>
          );
        }
        if (lines.every((l) => /^\s*>\s?/.test(l))) {
          return (
            <blockquote key={key} className={s.quote}>
              {lines.map((l, li) => <React.Fragment key={li}>{li > 0 && <br />}{inline(l.replace(/^\s*>\s?/, ""), `${key}l${li}`)}</React.Fragment>)}
            </blockquote>
          );
        }
        const heading = /^\s*(#{1,4})\s+(.*)$/.exec(lines[0]);
        if (heading && lines.length === 1) {
          return <h4 key={key} className={s.mdHeading}>{inline(heading[2], key)}</h4>;
        }
        return (
          <p key={key} className={s.para}>
            {lines.map((l, li) => (
              <React.Fragment key={li}>{li > 0 && <br />}{inline(l, `${key}l${li}`)}</React.Fragment>
            ))}
          </p>
        );
      })}
    </>
  );
}
