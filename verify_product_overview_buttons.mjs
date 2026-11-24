#!/usr/bin/env node
/**
 * verify_product_overview_buttons.mjs
 * -----------------------------------
 * Dependency-free static wiring verifier for the Keel product-overview page.
 * It checks that every interactive control in keel/site/product-overview.html
 * is wired by keel/site/ui/product-overview.js.
 *
 * USAGE (from the workspace root, or from any directory):
 *   node verify_product_overview_buttons.mjs
 *
 * No npm packages are used. Input paths are resolved relative to this script,
 * so the command works regardless of the current working directory.
 *
 * A control is considered WIRED when at least one of these is true:
 *   1. A class, #id, [data-*] or [aria-*] token that belongs to the control is
 *      referenced in a string literal in the JavaScript (selectors such as
 *      ".po-faq-q", "#po-ask-form", "data-cap-tab", "aria-expanded", ...).
 *   2. It is an <a> with a real href (href present, not empty, not bare "#").
 *      Fragment links such as href="#capabilities" count as real navigation.
 *   3. It is a type="submit" button inside a <form> that has a JS submit
 *      listener (or an action attribute).
 *
 * NOTE: generic element selectors such as "button", "a[href]" or
 * "button:not([disabled])" are deliberately NOT counted as wiring. They do not
 * target a specific control, and counting them would hide genuinely dead
 * controls (for example a decorative button with a unique class and no handler).
 *
 * Additional integrity checks: no bare href="#", every <form> has a JS submit
 * handler or an action, every aria-controls target id exists, and no duplicate
 * ids.
 *
 * EXIT CODES:
 *   0 - all controls wired and all integrity checks pass
 *   1 - one or more unwired controls and/or integrity failures (details printed)
 */

import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = dirname(fileURLToPath(import.meta.url));
const HTML_PATH = join(ROOT, "keel", "site", "product-overview.html");
const JS_PATH = join(ROOT, "keel", "site", "ui", "product-overview.js");

let html;
let js;
try {
  html = readFileSync(HTML_PATH, "utf8");
  js = readFileSync(JS_PATH, "utf8");
} catch (error) {
  console.error("Unable to read input files: " + error.message);
  process.exit(1);
}

/* ------------------------------------------------------------------ */
/* Helpers                                                             */
/* ------------------------------------------------------------------ */

function lineAt(index) {
  return html.slice(0, index).split("\n").length;
}

function attrsOf(tagText) {
  const attrs = {};
  const re = /([\w:-]+)(?:\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s>]+)))?/g;
  let match;
  while ((match = re.exec(tagText))) {
    const name = match[1].toLowerCase();
    const value = match[2] !== undefined ? match[2]
      : match[3] !== undefined ? match[3]
        : match[4] !== undefined ? match[4] : "";
    attrs[name] = value;
  }
  return attrs;
}

function classTokens(attrs) {
  return attrs.class ? String(attrs.class).trim().split(/\s+/).filter(Boolean) : [];
}

function realHref(href) {
  if (href === undefined) return false;
  const value = String(href).trim();
  return value !== "" && value !== "#";
}

/* ------------------------------------------------------------------ */
/* 1. Parse the HTML with regular expressions                          */
/* ------------------------------------------------------------------ */

const controls = [];
const forms = [];
const openForms = [];
const tagRe = /<(\/?)(form|button|a)\b([^>]*)>/gi;

let m;
while ((m = tagRe.exec(html))) {
  const closing = m[1] === "/";
  const tag = m[2].toLowerCase();
  const full = m[0];
  const line = lineAt(m.index);

  if (closing) {
    if (tag === "form" && openForms.length) openForms.pop();
    continue;
  }

  const attrs = attrsOf(full);
  const classes = classTokens(attrs);

  if (tag === "form") {
    const form = { attrs, classes, line };
    forms.push(form);
    openForms.push(form);
    continue;
  }

  const dataAttrs = Object.keys(attrs).filter((key) => key.startsWith("data-"));
  const ariaAttrs = Object.keys(attrs).filter((key) => key.startsWith("aria-"));
  controls.push({
    tag,
    attrs,
    classes,
    dataAttrs,
    ariaAttrs,
    line,
    snippet: full.length > 160 ? full.slice(0, 157) + "..." : full,
    form: tag === "button" ? openForms[openForms.length - 1] || null : null
  });
}

/* ------------------------------------------------------------------ */
/* 2. Mine selectors / attribute references out of the JavaScript      */
/* ------------------------------------------------------------------ */

function stringLiterals(source) {
  const found = [];
  // Double- and single-quoted JS strings (escapes respected).
  for (const re of [/"((?:\\.|[^"\\])*)"/g, /'((?:\\.|[^'\\])*)'/g]) {
    let literal;
    while ((literal = re.exec(source))) found.push(literal[1]);
  }
  return found;
}

const jsClasses = new Set();
const jsIds = new Set();
const jsDataAttrs = new Set();
const jsAriaAttrs = new Set();

for (const literal of stringLiterals(js)) {
  let token;
  const classRe = /\.([_A-Za-z][\w-]*)/g;
  while ((token = classRe.exec(literal))) jsClasses.add(token[1]);
  const idRe = /#([_A-Za-z][\w-]*)/g;
  while ((token = idRe.exec(literal))) jsIds.add(token[1]);
  const dataRe = /data-[a-z0-9-]+/gi;
  while ((token = dataRe.exec(literal))) jsDataAttrs.add(token[0].toLowerCase());
  const ariaRe = /aria-[a-z0-9-]+/gi;
  while ((token = ariaRe.exec(literal))) jsAriaAttrs.add(token[0].toLowerCase());
}

const hasSubmitListener = /\.addEventListener\(\s*["']submit["']/.test(js);

function formHasHandler(form) {
  if (String(form.attrs.action || "").trim()) return true;
  if (!hasSubmitListener) return false;
  if (form.attrs.id && jsIds.has(form.attrs.id)) return true;
  return form.classes.some((name) => jsClasses.has(name));
}

/* ------------------------------------------------------------------ */
/* 3. Decide whether each control is wired                             */
/* ------------------------------------------------------------------ */

function wiringReasons(control) {
  const reasons = [];

  if (control.tag === "a" && realHref(control.attrs.href)) {
    reasons.push('navigation href="' + control.attrs.href + '"');
  }
  for (const name of control.classes) {
    if (jsClasses.has(name)) reasons.push("JS class ." + name);
  }
  if (control.attrs.id && jsIds.has(control.attrs.id)) {
    reasons.push("JS id #" + control.attrs.id);
  }
  for (const name of control.dataAttrs) {
    if (jsDataAttrs.has(name)) reasons.push("JS attribute [" + name + "]");
  }
  for (const name of control.ariaAttrs) {
    if (jsAriaAttrs.has(name)) reasons.push("JS attribute [" + name + "]");
  }
  if (control.tag === "button" && String(control.attrs.type || "").toLowerCase() === "submit" &&
      control.form && formHasHandler(control.form)) {
    reasons.push("submit button of JS-handled form #" + (control.form.attrs.id || "(class-based)"));
  }

  return reasons;
}

for (const control of controls) {
  control.reasons = wiringReasons(control);
  control.wired = control.reasons.length > 0;
}
const unwired = controls.filter((control) => !control.wired);
const wiredCount = controls.length - unwired.length;

/* ------------------------------------------------------------------ */
/* 5. Integrity checks                                                 */
/* ------------------------------------------------------------------ */

const hashIssues = [];
const formIssues = [];
const ariaIssues = [];
const duplicateIssues = [];

// No bare href="#".
for (const control of controls) {
  if (control.attrs.href !== undefined && String(control.attrs.href).trim() === "#") {
    hashIssues.push('line ' + control.line + ': ' + control.snippet);
  }
}

// Every form has a JS submit handler or an action.
for (const form of forms) {
  if (!formHasHandler(form)) {
    formIssues.push("line " + form.line + ': <form id="' + (form.attrs.id || "") +
      '" class="' + (form.attrs.class || "") + '">');
  }
}

// Track every id (used for duplicate detection and aria-controls targets).
const idLines = new Map();
const idRe = /\bid\s*=\s*["']([^"']+)["']/gi;
let idMatch;
while ((idMatch = idRe.exec(html))) {
  const id = idMatch[1].trim();
  if (!id) continue;
  if (!idLines.has(id)) idLines.set(id, []);
  idLines.get(id).push(lineAt(idMatch.index));
}
for (const [id, lines] of idLines) {
  if (lines.length > 1) duplicateIssues.push('id "' + id + '" at lines ' + lines.join(", "));
}
const knownIds = new Set(idLines.keys());

// Every aria-controls target id exists (space-separated ids are allowed).
const controlsAttrRe = /\baria-controls\s*=\s*["']([^"']+)["']/gi;
let ariaMatch;
while ((ariaMatch = controlsAttrRe.exec(html))) {
  const line = lineAt(ariaMatch.index);
  for (const target of ariaMatch[1].trim().split(/\s+/).filter(Boolean)) {
    if (!knownIds.has(target)) {
      ariaIssues.push('aria-controls="' + target + '" at line ' + line + ' has no matching id');
    }
  }
}

const integrityIssueCount = hashIssues.length + formIssues.length + ariaIssues.length + duplicateIssues.length;

/* ------------------------------------------------------------------ */
/* 4 + 6. Report and exit                                              */
/* ------------------------------------------------------------------ */

const buttonCount = controls.filter((control) => control.tag === "button").length;
const linkCount = controls.filter((control) => control.tag === "a").length;
const failed = unwired.length > 0 || integrityIssueCount > 0;

const report = [];
report.push("Keel product-overview - static control wiring verification");
report.push("=".repeat(62));
report.push("HTML : " + HTML_PATH);
report.push("JS   : " + JS_PATH);
report.push("");
report.push("Collected controls : " + controls.length +
  " (buttons: " + buttonCount + ", links: " + linkCount + ")");
report.push("Collected forms    : " + forms.length);
report.push("JS selectors mined : classes=" + jsClasses.size + ", #ids=" + jsIds.size +
  ", [data-*]=" + jsDataAttrs.size + ", [aria-*]=" + jsAriaAttrs.size);
report.push("Submit listeners   : " + (hasSubmitListener ? "present" : "absent"));
report.push("");

if (unwired.length) {
  report.push("UNWIRED CONTROLS (" + unwired.length + "):");
  for (const control of unwired) {
    report.push("  line " + control.line + "  <" + control.tag + ">  " + control.snippet);
    report.push("     reason: no matching JS selector, no navigation href, and not a handled form submit");
  }
} else {
  report.push("UNWIRED CONTROLS: none");
}

report.push("");
report.push("INTEGRITY CHECKS:");
report.push("  " + (hashIssues.length ? "FAIL" : "PASS") + '  no href="#"' +
  (hashIssues.length ? " (" + hashIssues.length + " found)" : ""));
for (const issue of hashIssues) report.push("       - " + issue);
report.push("  " + (formIssues.length ? "FAIL" : "PASS") + "  every form has a JS submit handler or action" +
  (formIssues.length ? " (" + formIssues.length + " failed)" : ""));
for (const issue of formIssues) report.push("       - " + issue);
report.push("  " + (ariaIssues.length ? "FAIL" : "PASS") + "  every aria-controls target id exists" +
  (ariaIssues.length ? " (" + ariaIssues.length + " broken)" : ""));
for (const issue of ariaIssues) report.push("       - " + issue);
report.push("  " + (duplicateIssues.length ? "FAIL" : "PASS") + "  no duplicate ids" +
  (duplicateIssues.length ? " (" + duplicateIssues.length + " duplicated)" : ""));
for (const issue of duplicateIssues) report.push("       - " + issue);

report.push("");
report.push("SUMMARY: " + controls.length + " controls, " + wiredCount + " wired, " +
  unwired.length + " unwired; " + integrityIssueCount + " integrity issue(s)");
report.push("RESULT: " + (failed ? "FAIL" : "PASS"));

console.log(report.join("\n"));
process.exitCode = failed ? 1 : 0;
