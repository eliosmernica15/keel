import type { Page } from "@playwright/test";

/** Open the shell with first-run onboarding complete and a deterministic theme. */
export async function openAppThemed(
  page: Page,
  theme: "dark" | "light" = "dark",
  extraStorage: Record<string, string> = {},
): Promise<void> {
  await page.addInitScript(
    ({ theme, extraStorage }) => {
      try {
        localStorage.setItem("keel-onboarding-done", "true");
        localStorage.setItem("keel-theme-v2", JSON.stringify(theme));
        for (const [key, value] of Object.entries(extraStorage)) localStorage.setItem(key, value);
      } catch {
        /* storage disabled */
      }
    },
    { theme, extraStorage },
  );
  await page.goto("/", { waitUntil: "domcontentloaded" });
  await page.locator(".keel-app").waitFor({ state: "visible" });
  // AppProvider sets these only after its mount effect; without this gate a
  // themed interaction can race hydration (QA-G-002).
  await page.locator("html[data-reduced-motion]").waitFor({ state: "attached" });
  await page.locator(`html[data-theme="${theme}"]`).waitFor({ state: "attached" });
}

export interface ContrastFinding {
  tag: string;
  text: string;
  foreground: string;
  background: string;
  ratio: number;
  threshold: number;
  fontSize: string;
  fontWeight: string;
}

/**
 * Compute WCAG contrast for every element with its own visible text.
 * Background is obtained by compositing ancestor background colours; elements
 * painted by a background image or canvas are reported as `unknown` and
 * excluded (they cannot be computed from computed styles alone).
 */
export async function collectContrast(page: Page): Promise<{
  checked: number;
  unknown: number;
  violations: ContrastFinding[];
  minRatio: number;
}> {
  return page.evaluate(() => {
    type RGB = [number, number, number];
    const parse = (value: string): RGB | null => {
      const m = value.match(/rgba?\(([^)]+)\)/i);
      if (!m) return null;
      const parts = m[1].split(/[,\s/]+/).filter(Boolean).map(Number);
      if (parts.length < 3 || parts.slice(0, 3).some((n) => !Number.isFinite(n))) return null;
      return [parts[0], parts[1], parts[2]];
    };
    const alpha = (value: string): number => {
      const m = value.match(/rgba\([^,]+,[^,]+,[^,]+,\s*([\d.]+)\)/i);
      return m ? Number(m[1]) : 1;
    };
    const lum = ([r, g, b]: RGB): number => {
      const f = (v: number) => {
        const s = v / 255;
        return s <= 0.03928 ? s / 12.92 : Math.pow((s + 0.055) / 1.055, 2.4);
      };
      return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b);
    };
    const ratio = (a: RGB, b: RGB): number => {
      const l1 = lum(a), l2 = lum(b);
      return (Math.max(l1, l2) + 0.05) / (Math.min(l1, l2) + 0.05);
    };

    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
    const seen = new Set<Element>();
    const elements: Element[] = [];
    while (walker.nextNode()) {
      const node = walker.currentNode as Text;
      if (!node.nodeValue || !node.nodeValue.trim()) continue;
      const el = node.parentElement;
      if (el && !seen.has(el)) { seen.add(el); elements.push(el); }
    }

    const violations: ContrastFinding[] = [];
    let checked = 0, unknown = 0, minRatio = Number.POSITIVE_INFINITY;
    for (const el of elements) {
      if (el.closest("[aria-hidden='true'], script, style, .sr-only")) continue;
      const style = getComputedStyle(el);
      if (style.visibility === "hidden" || style.display === "none" || Number(style.opacity) === 0) continue;
      if (el.getClientRects().length === 0) continue;
      if (el.closest(":disabled")) continue;
      const fg = parse(style.color);
      if (!fg) { unknown++; continue; }

      // Composite ancestor backgrounds over white until an opaque layer is found.
      let bg: RGB = [255, 255, 255];
      let foundOpaque = false;
      let bgImage = false;
      let node: Element | null = el;
      while (node) {
        const s = getComputedStyle(node);
        if (s.backgroundImage && s.backgroundImage !== "none") bgImage = true;
        const c = parse(s.backgroundColor);
        const a = alpha(s.backgroundColor);
        if (c && a > 0) {
          bg = [c[0] * a + bg[0] * (1 - a), c[1] * a + bg[1] * (1 - a), c[2] * a + bg[2] * (1 - a)];
          if (a >= 0.999) { foundOpaque = true; break; }
        }
        node = node.parentElement;
      }
      if (!foundOpaque || bgImage) { unknown++; continue; }

      const size = parseFloat(style.fontSize) || 16;
      const weight = Number(style.fontWeight) || 400;
      const large = size >= 24 || (size >= 18.66 && weight >= 700);
      const threshold = large ? 3 : 4.5;
      const r = ratio(fg, bg as RGB);
      checked++;
      minRatio = Math.min(minRatio, r);
      if (r < threshold) {
        violations.push({
          tag: el.tagName.toLowerCase(),
          text: (el.textContent ?? "").trim().slice(0, 90),
          foreground: style.color,
          background: `rgb(${bg.map((v) => Math.round(v)).join(", ")})`,
          ratio: Math.round(r * 100) / 100,
          threshold,
          fontSize: style.fontSize,
          fontWeight: style.fontWeight,
        });
      }
    }
    return { checked, unknown, violations, minRatio: Number.isFinite(minRatio) ? Math.round(minRatio * 100) / 100 : null as unknown as number };
  });
}

export interface UnnamedControl { tag: string; html: string }

/** Scan the rendered accessibility-relevant controls for missing accessible names. */
export async function collectUnnamedControls(page: Page): Promise<UnnamedControl[]> {
  return page.evaluate(() => {
    const out: UnnamedControl[] = [];
    const controls = Array.from(
      document.querySelectorAll<HTMLElement>("button, input, select, textarea, [role='button'], [role='tab'], [role='dialog']"),
    );
    for (const el of controls) {
      if (el.closest("[aria-hidden='true']") || el.getClientRects().length === 0) continue;
      if (el instanceof HTMLInputElement && el.type === "hidden") continue;
      const labelled =
        (el.getAttribute("aria-label") ?? "").trim().length > 0 ||
        (el.getAttribute("title") ?? "").trim().length > 0 ||
        (el.getAttribute("aria-labelledby") ?? "").trim().length > 0 ||
        (el.textContent ?? "").trim().length > 0 ||
        (el instanceof HTMLInputElement || el instanceof HTMLTextAreaElement || el instanceof HTMLSelectElement
          ? !!document.querySelector(`label[for="${CSS.escape(el.id)}"]`) || !!el.closest("label")
          : false);
      if (!labelled) out.push({ tag: el.tagName.toLowerCase(), html: el.outerHTML.slice(0, 180) });
    }
    return out;
  });
}

export async function focusDescriptor(page: Page): Promise<{
  tag: string; label: string; text: string; tabindex: number | null; visible: boolean;
}> {
  return page.evaluate(() => {
    const el = document.activeElement as HTMLElement | null;
    if (!el || el === document.body) return { tag: "body", label: "", text: "", tabindex: null, visible: false };
    return {
      tag: el.tagName.toLowerCase(),
      label: el.getAttribute("aria-label") ?? "",
      text: (el.textContent ?? "").trim().slice(0, 60),
      tabindex: el.hasAttribute("tabindex") ? Number(el.getAttribute("tabindex")) : null,
      visible: el.getClientRects().length > 0,
    };
  });
}
