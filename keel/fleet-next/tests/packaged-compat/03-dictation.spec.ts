import type { Page } from "@playwright/test";
import { test, expect, openApp, findCall } from "./fixtures";

/**
 * FIXTURE — deterministic Web Speech API double. No microphone, no audio and
 * no recognition service: the test emits exactly the events a browser would.
 * This exercises the real production composer on the packaged origin.
 */
type SpeechMode = "standard" | "none";

async function installSpeechFixture(page: Page, mode: SpeechMode): Promise<void> {
  await page.addInitScript((fixtureMode: SpeechMode) => {
    interface ResultLike { isFinal: boolean; 0?: { transcript: string } }
    class FakeRecognition {
      static instances: FakeRecognition[] = [];
      lang = "en-US";
      continuous = false;
      interimResults = false;
      maxAlternatives = 1;
      startCalls = 0;
      onstart: (() => void) | null = null;
      onresult: ((e: { resultIndex: number; results: { length: number; [i: number]: ResultLike } }) => void) | null = null;
      onerror: ((e: { error: string }) => void) | null = null;
      onend: (() => void) | null = null;
      constructor() { FakeRecognition.instances.push(this); }
      start() { this.startCalls++; this.onstart?.(); }
      stop() { /* the browser will emit end */ }
      abort() { /* no-op in the fixture */ }
      emitFinal(text: string) {
        this.onresult?.({ resultIndex: 0, results: { length: 1, 0: { isFinal: true, 0: { transcript: text } } } });
      }
      emitError(error: string) { this.onerror?.({ error }); }
      end() { this.onend?.(); }
    }
    const scope = window as unknown as {
      SpeechRecognition?: typeof FakeRecognition;
      webkitSpeechRecognition?: typeof FakeRecognition;
      __speechFixture?: { latest: () => FakeRecognition | null };
    };
    delete scope.SpeechRecognition;
    delete scope.webkitSpeechRecognition;
    if (fixtureMode === "standard") scope.SpeechRecognition = FakeRecognition;
    scope.__speechFixture = { latest: () => FakeRecognition.instances.at(-1) ?? null };
  }, mode);
}

async function startCalls(page: Page): Promise<number | null> {
  return page.evaluate(() => (window as unknown as {
    __speechFixture?: { latest: () => { startCalls: number } | null };
  }).__speechFixture?.latest()?.startCalls ?? null);
}

async function emitFinal(page: Page, text: string): Promise<void> {
  await page.evaluate((value) => (window as unknown as {
    __speechFixture?: { latest: () => { emitFinal(v: string): void } | null };
  }).__speechFixture?.latest()?.emitFinal(value), text);
}

async function emitError(page: Page, code: string): Promise<void> {
  await page.evaluate((value) => (window as unknown as {
    __speechFixture?: { latest: () => { emitError(v: string): void } | null };
  }).__speechFixture?.latest()?.emitError(value), code);
}

async function openSession(page: Page): Promise<void> {
  await openApp(page);
  await page.locator('select[aria-label="Open an existing task"]').selectOption("bot-1");
  await expect(page.getByRole("button", { name: "Back to Cowork home" })).toBeVisible();
}

test("FIXTURE: dictation inserts a final transcript at the caret and never sends it", async ({ page, request, consoleErrors }) => {
  await installSpeechFixture(page, "standard");
  await openSession(page);

  const mic = page.getByRole("button", { name: "Dictate message" });
  await expect(mic).toBeEnabled();
  expect(await startCalls(page)).toBeNull(); // detection must not open a microphone

  const textarea = page.getByRole("textbox", { name: "Message Keel" });
  await textarea.fill("Hello world");
  await textarea.evaluate((el: HTMLTextAreaElement) => { el.focus(); el.setSelectionRange(5, 5); });
  await mic.click();
  await expect.poll(() => startCalls(page)).toBe(1);
  await expect(page.getByRole("status").filter({ hasText: "Listening…" })).toBeVisible();

  await emitFinal(page, "brave");
  await expect(textarea).toHaveValue("Hello brave world");
  await expect(page.getByRole("status").filter({ hasText: "Transcript received" })).toBeVisible();
  expect(await findCall(request, "POST", "bots/bot-1/messages")).toBeUndefined();

  // The inserted words are a normal draft and survive a reload.
  await page.reload({ waitUntil: "domcontentloaded" });
  await expect(page.getByRole("textbox", { name: "Message Keel" })).toHaveValue("Hello brave world");
  expect(consoleErrors).toEqual([]);
});

test("FIXTURE: denied microphone permission is reported without changing the draft", async ({ page, request, consoleErrors }) => {
  await installSpeechFixture(page, "standard");
  await openSession(page);

  const textarea = page.getByRole("textbox", { name: "Message Keel" });
  await textarea.fill("draft stays here");
  await page.getByRole("button", { name: "Dictate message" }).click();
  await expect.poll(() => startCalls(page)).toBe(1);
  await emitError(page, "not-allowed");

  await expect(page.getByRole("alert").filter({ hasText: "Microphone permission was denied" }).first()).toBeVisible();
  await expect(textarea).toHaveValue("draft stays here");
  expect(await findCall(request, "POST", "bots/bot-1/messages")).toBeUndefined();
  expect(consoleErrors).toEqual([]);
});

test("FIXTURE: unsupported browsers get an honest disabled control", async ({ page, consoleErrors }) => {
  await installSpeechFixture(page, "none");
  await openSession(page);

  await expect(page.getByRole("button", { name: /Dictation unavailable/ })).toBeDisabled();
  await expect(page.getByText("Dictation unavailable in this browser.")).toBeVisible();
  await expect(page.getByRole("button", { name: "Dictate message" })).toHaveCount(0);
  expect(consoleErrors).toEqual([]);
});
