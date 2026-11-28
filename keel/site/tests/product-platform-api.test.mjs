/* Design/QA contract for the /platform/api page.
 * Run: node --test keel/site/tests/product-platform-api.test.mjs
 *
 * Pure static checks: no server, no browser, no network.
 */
import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const SITE = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const HTML_FILES = [
  path.join(SITE, "platform", "api.html"),
  path.join(SITE, "platform", "api", "index.html"),
];
const CSS = path.join(SITE, "ui", "platform-api.css");
const JS = path.join(SITE, "ui", "platform-api.js");

const html = HTML_FILES.map((file) => fs.readFileSync(file, "utf8"));
const css = fs.readFileSync(CSS, "utf8");
const js = fs.readFileSync(JS, "utf8");

/* Every required section in the owner's screenshot, in document order. */
const SECTIONS = [
  ["sticky nav + four-column product mega menu", /class="pa-header"/, /id="pa-menu-product"/],
  ["hero", /class="pa-hero pa-section"/, /Build with Keel/],
  ["models comparison table", /id="pa-models"/, /Keel models for every job/],
  ["APIs designed for Keel", /id="pa-design"/, /APIs designed for Keel/],
  ["Managed Agents", /id="pa-agents"/, /Power your most ambitious workloads with Keel Managed Agents/],
  ["connect tabs", /id="pa-connect"/, /Connect to your systems and knowledge/],
  ["enterprise cloud providers", /id="pa-enterprise"/, /Built for enterprise workloads/],
  ["cost controls tabs", /id="pa-cost"/, /Control cost and performance/],
  ["dark console section", /class="pa-console dark-scope"/, /Observe and manage your agents with the Keel Console/],
  ["dark footer", /<footer class="pa-footer/, /class="pa-lang"/],
];

test("both HTML entry points exist and are identical", () => {
  assert.ok(HTML_FILES.every((file) => fs.existsSync(file)));
  assert.equal(html[0], html[1], "api.html and api/index.html must match");
});

test("all ten designed sections exist in order in both HTML files", () => {
  for (let copy = 0; copy < html.length; copy += 1) {
    let cursor = 0;
    for (const [name, startPattern, detailPattern] of SECTIONS) {
      const start = html[copy].search(startPattern);
      assert.ok(start >= cursor, `${copy}: ${name} missing or out of order`);
      assert.match(html[copy].slice(start), detailPattern, `${copy}: ${name} detail missing`);
      cursor = start + 1;
    }
  }
});

test("product mega menu has four columns and all Keel model names", () => {
  for (const source of html) {
    for (const heading of ["Products", "Build", "Platform", "Models"]) {
      assert.ok(source.includes(`<p class="pa-mega-heading">${heading}</p>`),
        `mega menu is missing the ${heading} column`);
    }
    assert.match(source, /data-pa-nav="product"/);
    assert.match(source, /aria-controls="pa-menu-product"/);
    for (const name of ["Mythos (Fable)", "Opus", "Sonnet", "Haiku"]) {
      assert.ok(source.includes(name), `mega menu is missing ${name}`);
    }
    for (const label of ["Log in", "Contact sales", "Get Keel"]) {
      assert.ok(source.includes(`>${label} <span aria-hidden="true">`), `nav action missing: ${label}`);
    }
  }
});

test("hero has the serif headline, subtitle, CTAs and local block illustration", () => {
  for (const source of html) {
    assert.ok(source.includes("Build with Keel"), "serif hero headline missing");
    assert.ok(source.includes("Build with the models your users already love."));
    assert.ok(source.includes("Read the docs"));
    assert.ok(source.includes("Get API key"));
    assert.match(source, /src="\/assets\/img\/platform\/pa-hero-blocks\.svg"/);
    assert.match(source, /data-pa-parallax/);
  }
});

test("model table lists the four Keel models, spec rows, prices and access CTAs", () => {
  for (const source of html) {
    assert.match(source, /<table class="pa-model-table">/);
    for (const row of [
      "Input tokens", "Output tokens", "Prompt caching", "Batch API", "Extended thinking", "Context window",
    ]) {
      assert.ok(source.includes(`<th scope="row">${row}</th>`), `comparison row missing: ${row}`);
    }
    for (const price of [
      "$8 / MTok", "$40 / MTok", "$4 / MTok", "$20 / MTok", "$2 / MTok", "$10 / MTok",
      "$0.10 / MTok", "$0.50 / MTok", "$0.20", "$2.50", "$0.125", "50% savings",
    ]) {
      assert.ok(source.includes(price), `spec number missing: ${price}`);
    }
    assert.equal((source.match(/Get API access/g) || []).length, 4);
    assert.ok(source.includes("Prompt caching prices reflect a 5-minute TTL."));
    assert.ok(source.includes("See all models and pricing"));
  }
});

test("eight API feature cards plus the function-calling illustration are present", () => {
  for (const source of html) {
    assert.equal((source.match(/class="pa-feature-card"/g) || []).length, 8);
    for (const name of [
      "Messages", "Tool use", "Prompt caching", "Extended thinking",
      "Code execution", "MCP connector", "Files API", "Web search",
    ]) {
      assert.ok(source.includes(`<h3>${name}</h3>`), `feature card missing: ${name}`);
    }
    assert.ok(source.includes("Function calling with Websearch tool"));
    assert.match(source, /data-pa-copy="pa-code-function"/);
  }
});

test("Managed Agents has a video card, four accordion rows and a CTA", () => {
  for (const source of html) {
    assert.ok(source.includes("Built with the same tools that power Keel Code and Cowork."));
    assert.match(source, /data-pa-video/);
    assert.ok(source.includes("Introducing Keel Managed Agents"));
    for (const id of ["pa-agent-durable", "pa-agent-tools", "pa-agent-sandbox", "pa-agent-multi"]) {
      assert.ok(source.includes(`aria-controls="${id}"`), `accordion row missing: ${id}`);
    }
    for (const label of ["Durable execution", "Built-in tools", "Sandbox with compute", "Multi-agent coordination"]) {
      assert.ok(source.includes(label), `accordion label missing: ${label}`);
    }
    assert.ok(source.includes("Get started with Managed Agents"));
  }
});

test("connect section has three tabs, a logo grid and the MCP connector card", () => {
  for (const source of html) {
    assert.match(source, /data-pa-connect-tab="mcp"[\s\S]*data-pa-connect-tab="skills"[\s\S]*data-pa-connect-tab="websearch"/);
    for (const id of ["pa-panel-mcp", "pa-panel-skills", "pa-panel-websearch"]) {
      assert.ok(source.includes(`id="${id}"`), `connect panel missing: ${id}`);
    }
    assert.ok(source.includes("class=\"pa-logo-grid\""));
    assert.ok(source.includes("Keel MCP connector"));
    assert.ok(source.includes("Build an MCP server"));
  }
});

test("enterprise section names the three first-party cloud providers", () => {
  for (const source of html) {
    assert.ok(source.includes("Customize your enterprise-grade applications with our first-party cloud providers."));
    for (const name of ["Amazon Bedrock", "Microsoft Foundry", "Google Cloud Vertex AI"]) {
      assert.ok(source.includes(name), `cloud card missing: ${name}`);
    }
    assert.ok(source.includes("Available on all major cloud providers"));
    for (const logo of ["pa-logo-aws.svg", "pa-logo-azure.svg", "pa-logo-gcp.svg"]) {
      assert.ok(source.includes(logo), `cloud logo missing: ${logo}`);
    }
    assert.ok((source.match(/Learn more/g) || []).length >= 3);
  }
});

test("cost section has four tabs and four copyable static JSON configs", () => {
  for (const source of html) {
    assert.ok(source.includes("Run large-scale workloads with predictable performance."));
    assert.match(source, /data-pa-cost-tab="controls"[\s\S]*data-pa-cost-tab="caching"[\s\S]*data-pa-cost-tab="limits"[\s\S]*data-pa-cost-tab="batch"/);
    for (const id of ["pa-code-controls", "pa-code-caching", "pa-code-limits", "pa-code-batch"]) {
      assert.ok(source.includes(`id="${id}"`), `config code missing: ${id}`);
    }
    assert.equal((source.match(/class="pa-copy"/g) || []).length, 6);
    assert.match(source, /class="pa-tok-key"/);
  }
});

test("console section is dark and shows two local screenshots", () => {
  for (const source of html) {
    assert.ok(source.includes("class=\"pa-console dark-scope\""));
    assert.match(source, /src="\/assets\/img\/keel-settings-general\.jpg"/);
    assert.match(source, /src="\/assets\/img\/keel-settings-providers\.jpg"/);
    assert.ok(source.includes("Explore the console"));
  }
});

test("footer has all columns and a working language selector", () => {
  for (const source of html) {
    for (const column of ["Products", "Build", "Models", "Enterprise", "Resources", "Company"]) {
      assert.ok(source.includes(`<h3>${column}</h3>`), `footer column missing: ${column}`);
    }
    assert.match(source, /<select class="pa-lang" id="pa-lang">/);
    assert.match(source, /<option value="en" selected>English<\/option>/);
  }
});

test("no Claude branding remains in any of the four owned files", () => {
  for (const source of [...html, css, js]) {
    assert.ok(!/claude/i.test(source), "owner requires Keel branding only");
  }
});

test("no /app links are used anywhere in the owned files", () => {
  for (const source of [...html, css, js]) {
    assert.ok(!/\/app(?:\/|"|'|\s|>|$)/.test(source), "use /login instead of /app");
  }
});

test("internal links and anchors resolve to real routes or ids", () => {
  for (let copy = 0; copy < html.length; copy += 1) {
    const ids = new Set([...html[copy].matchAll(/\sid="([^"]+)"/g)].map((m) => m[1]));
    const hrefs = [...html[copy].matchAll(/\shref="([^"]+)"/g)].map((m) => m[1]);
    assert.ok(hrefs.length > 60, "expected a fully linked page");
    for (const href of hrefs) {
      if (href.startsWith("mailto:") || /^https?:/.test(href)) continue;
      const [rawPath, hash] = href.split("#");
      if (hash) assert.ok(ids.has(hash), `${copy}: anchor #${hash} has no target`);
      if (!rawPath) continue;
      assert.ok(rawPath.startsWith("/"), `${copy}: internal link must be site-absolute: ${href}`);
      const target = path.join(SITE, rawPath.replace(/^\/+/, ""));
      const candidates = [target, `${target}.html`, path.join(target, "index.html")];
      assert.ok(candidates.some((candidate) => {
        try { return fs.statSync(candidate).isFile(); } catch { return false; }
      }), `${copy}: link points to a missing route: ${href}`);
    }
  }
});

test("all referenced local artwork exists", () => {
  for (let copy = 0; copy < html.length; copy += 1) {
    const images = [...html[copy].matchAll(/src="(\/assets\/[^"]+)"/g)].map((m) => m[1]);
    assert.ok(images.length >= 20, "expected the local platform artwork");
    for (const image of images) {
      assert.ok(fs.existsSync(path.join(SITE, image.replace(/^\/+/, ""))),
        `${copy}: missing image ${image}`);
    }
  }
});

test("script is deferred and nothing uses inline handlers or huge data URIs", () => {
  for (const source of html) {
    assert.match(source, /<script src="\/ui\/platform-api\.js" defer><\/script>/);
    assert.ok(!/<script(?![^>]*\bsrc=)/i.test(source), "no inline scripts");
    assert.ok(!/\son(?:click|load|error|mouseover|change|input|submit|scroll)\s*=/i.test(source),
      "no inline event handlers");
    assert.ok(!/data:[^;"']{200,}/.test(source), "no large inline data URIs");
  }
});

test("CSS has a reduced-motion kill switch, reveal primitives and smooth states", () => {
  assert.match(css, /@media\s*\(prefers-reduced-motion:\s*reduce\)/);
  assert.match(css, /transition:\s*none\s*!important/);
  assert.match(css, /\[data-reveal\][\s\S]*translateY\(16px\)/);
  assert.match(css, /--pa-reveal-delay/);
  assert.match(css, /cubic-bezier\(\.22,\s*\.61,\s*\.36,\s*1\)/);
  assert.match(css, /\.is-scrolled[\s\S]*box-shadow/);
  assert.match(css, /pa-accordion-a[\s\S]*max-height:\s*0[\s\S]*transition:\s*max-height/);
  assert.match(css, /pa-mega-in[\s\S]*160ms/);
});

test("JS uses IntersectionObserver, passive rAF scroll and no busy loops", () => {
  assert.match(js, /IntersectionObserver/);
  assert.match(js, /observer\.unobserve/);
  assert.match(js, /addEventListener\("scroll",\s*frame,\s*\{\s*passive:\s*true\s*\}\)/);
  assert.match(js, /window\.requestAnimationFrame/);
  assert.match(js, /prefersReducedMotion\(\)/);
  assert.ok(!/setInterval\s*\(/.test(js), "no polling interval");
  assert.ok(!/while\s*\(/.test(js), "no busy loop");
});

test("every interactive control family has a real handler in the script", () => {
  const hooks = [
    "pa-nav-trigger", "pa-hamburger", "pa-mega", "pa-connect-tab", "pa-cost-tab",
    "pa-accordion-q", "pa-copy", "pa-lang", "pa-modal-close", "pa-modal-backdrop",
    "pa-video-card", "pa-toast", "pa-hero-art",
  ];
  for (const hook of hooks) {
    assert.match(js, new RegExp(`\\.${hook}\\b`), `no handler for .${hook}`);
  }
  assert.match(js, /data-pa-modal/);
  assert.match(js, /data-pa-info-title/);
  assert.match(js, /data-pa-parallax/);
  assert.match(js, /data-pa-copy/);
});
