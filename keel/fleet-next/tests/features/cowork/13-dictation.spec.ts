import type { Page } from "@playwright/test";
import { test, expect, mockBridge, openSession, BOT } from "./fixtures";

/**
 * FIXTURE — deterministic Web Speech API double.
 *
 * This is a test-only stand-in for `window.SpeechRecognition` /
 * `window.webkitSpeechRecognition`. It captures no audio and performs no
 * recognition by itself: tests explicitly emit the browser events the
 * composer is expected to handle (final result, error, end). Keeping `end()`
 * under test control makes the `processing` -> `stopped` transition
 * observable without timers.
 */
type SpeechFixtureMode = "standard" | "webkit" | "none";

async function installSpeechFixture(page: Page, mode: SpeechFixtureMode): Promise<void> {
  await page.addInitScript((fixtureMode: SpeechFixtureMode) => {
    interface SpeechResultLike { isFinal: boolean; 0?: { transcript: string }; }
    interface SpeechResultEventLike {
      resultIndex: number;
      results: { length: number; [index: number]: SpeechResultLike };
    }
    class FakeRecognition {
      static instances: FakeRecognition[] = [];
      lang = "en-US";
      continuous = false;
      interimResults = false;
      maxAlternatives = 1;
      startCalls = 0;
      stopCalls = 0;
      abortCalls = 0;
      onstart: (() => void) | null = null;
      onresult: ((event: SpeechResultEventLike) => void) | null = null;
      onerror: ((event: { error: string }) => void) | null = null;
      onend: (() => void) | null = null;

      constructor() { FakeRecognition.instances.push(this); }
      start() { this.startCalls++; this.onstart?.(); }
      stop() { this.stopCalls++; }
      abort() { this.abortCalls++; }
      emitFinal(transcript: string) {
        const result: SpeechResultLike = { isFinal: true, 0: { transcript } };
        this.onresult?.({ resultIndex: 0, results: { length: 1, 0: result } });
      }
      emitError(error: string) { this.onerror?.({ error }); }
      end() { this.onend?.(); }
    }

    const scope = window as unknown as {
      SpeechRecognition?: typeof FakeRecognition;
      webkitSpeechRecognition?: typeof FakeRecognition;
      __speechFixture?: {
        latest: () => FakeRecognition | null;
        count: () => number;
      };
    };
    delete scope.SpeechRecognition;
    delete scope.webkitSpeechRecognition;
    if (fixtureMode === "standard") scope.SpeechRecognition = FakeRecognition;
    if (fixtureMode === "webkit") scope.webkitSpeechRecognition = FakeRecognition;
    scope.__speechFixture = {
      latest: () => FakeRecognition.instances[FakeRecognition.instances.length - 1] ?? null,
      count: () => FakeRecognition.instances.length,
    };
  }, mode);
}

interface SpeechCounts { startCalls: number; stopCalls: number; abortCalls: number; }

/** Read the most recent fixture instance without exposing it across the wire. */
async function speechCounts(page: Page): Promise<SpeechCounts | null> {
  return page.evaluate(() => {
    const scope = window as unknown as {
      __speechFixture?: { latest: () => SpeechCounts | null };
    };
    return scope.__speechFixture?.latest() ?? null;
  });
}

async function emitFinal(page: Page, transcript: string): Promise<void> {
  await page.evaluate((words: string) => {
    const scope = window as unknown as {
      __speechFixture?: { latest: () => { emitFinal(text: string): void } | null };
    };
    scope.__speechFixture?.latest()?.emitFinal(words);
  }, transcript);
}

async function emitError(page: Page, code: string): Promise<void> {
  await page.evaluate((error: string) => {
    const scope = window as unknown as {
      __speechFixture?: { latest: () => { emitError(value: string): void } | null };
    };
    scope.__speechFixture?.latest()?.emitError(error);
  }, code);
}

async function endSpeech(page: Page): Promise<void> {
  await page.evaluate(() => {
    const scope = window as unknown as {
      __speechFixture?: { latest: () => { end(): void } | null };
    };
    scope.__speechFixture?.latest()?.end();
  });
}

test("an unsupported browser shows an honest disabled control and never requests a microphone", async ({ page, consoleErrors }) => {
  await installSpeechFixture(page, "none");
  await mockBridge(page, { rows: [] });
  await openSession(page);

  await expect(page.getByRole("button", { name: /Dictation unavailable/ })).toBeDisabled();
  await expect(page.getByText("Dictation unavailable in this browser.")).toBeVisible();
  await expect(page.getByRole("button", { name: "Dictate message" })).toHaveCount(0);
  expect(consoleErrors).toEqual([]);
});

test("the microphone is requested only on click, and the same control stops it", async ({ page, consoleErrors }) => {
  await installSpeechFixture(page, "standard");
  const bridge = await mockBridge(page, { rows: [] });
  await openSession(page);

  const mic = page.getByRole("button", { name: "Dictate message" });
  await expect(mic).toBeEnabled();
  // Support detection must not construct a recognizer or open a microphone.
  expect(await speechCounts(page)).toBeNull();

  await mic.click();
  await expect.poll(async () => (await speechCounts(page))?.startCalls).toBe(1);
  await expect(page.getByRole("status").filter({ hasText: "Listening…" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Stop dictation" })).toBeVisible();

  await page.getByRole("button", { name: "Stop dictation" }).click();
  await expect.poll(async () => (await speechCounts(page))?.stopCalls).toBe(1);
  await expect(page.getByRole("status").filter({ hasText: "Stopping dictation…" })).toBeVisible();

  await endSpeech(page);
  await expect(page.getByRole("status").filter({ hasText: "no transcript was inserted" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Dictate message" })).toBeVisible();
  expect(bridge.count("POST", /\/messages$/)).toBe(0);
  expect(consoleErrors).toEqual([]);
});

test("the webkitSpeechRecognition prefix is accepted as a fallback", async ({ page, consoleErrors }) => {
  await installSpeechFixture(page, "webkit");
  await mockBridge(page, { rows: [] });
  await openSession(page);

  await page.getByRole("button", { name: "Dictate message" }).click();
  await expect.poll(async () => (await speechCounts(page))?.startCalls).toBe(1);
  await expect(page.getByRole("status").filter({ hasText: "Listening…" })).toBeVisible();
  expect(consoleErrors).toEqual([]);
});

test("the mic button is keyboard operable", async ({ page, consoleErrors }) => {
  await installSpeechFixture(page, "standard");
  await mockBridge(page, { rows: [] });
  await openSession(page);

  const mic = page.getByRole("button", { name: "Dictate message" });
  await mic.focus();
  expect(await mic.evaluate((el) => document.activeElement === el)).toBe(true);
  await page.keyboard.press("Enter");
  await expect.poll(async () => (await speechCounts(page))?.startCalls).toBe(1);
  expect(consoleErrors).toEqual([]);
});

test("a final transcript lands at the caret, preserves the draft and is never sent", async ({ page, consoleErrors }) => {
  await installSpeechFixture(page, "standard");
  const bridge = await mockBridge(page, { rows: [] });
  await openSession(page);

  const textarea = page.getByRole("textbox", { name: "Message Keel" });
  await textarea.fill("Hello world");
  await textarea.evaluate((el: HTMLTextAreaElement) => {
    el.focus();
    el.setSelectionRange(5, 5); // between "Hello" and " world"
  });
  await page.getByRole("button", { name: "Dictate message" }).click();
  await emitFinal(page, "brave");

  await expect(textarea).toHaveValue("Hello brave world");
  await expect(page.getByRole("status").filter({ hasText: "Transcript received" })).toBeVisible();
  expect(bridge.count("POST", /\/messages$/)).toBe(0); // no auto-send

  await endSpeech(page);
  await expect(page.getByRole("status").filter({ hasText: "transcript inserted at the cursor. Nothing was sent" })).toBeVisible();
  expect(consoleErrors).toEqual([]);
});

test("a denied microphone permission is reported without touching the draft", async ({ page, consoleErrors }) => {
  await installSpeechFixture(page, "standard");
  const bridge = await mockBridge(page, { rows: [] });
  await openSession(page);

  const textarea = page.getByRole("textbox", { name: "Message Keel" });
  await textarea.fill("draft stays here");
  await page.getByRole("button", { name: "Dictate message" }).click();
  await emitError(page, "not-allowed");

  await expect(page.getByRole("alert").filter({ hasText: "Microphone permission was denied" }).first()).toBeVisible();
  await expect(textarea).toHaveValue("draft stays here");
  expect(bridge.count("POST", /\/messages$/)).toBe(0);
  expect(consoleErrors).toEqual([]);
});

test("no-speech is reported truthfully as no transcript", async ({ page, consoleErrors }) => {
  await installSpeechFixture(page, "standard");
  await mockBridge(page, { rows: [] });
  await openSession(page);

  const textarea = page.getByRole("textbox", { name: "Message Keel" });
  await page.getByRole("button", { name: "Dictate message" }).click();
  await emitError(page, "no-speech");

  await expect(page.getByRole("alert").filter({ hasText: "No speech was detected" }).first()).toBeVisible();
  await expect(textarea).toHaveValue("");
  expect(consoleErrors).toEqual([]);
});

test("recognition is aborted on session change and on unmount", async ({ page, consoleErrors }) => {
  await installSpeechFixture(page, "standard");
  await mockBridge(page, { rows: [], bots: [BOT, { ...BOT, id: "bot-2", name: "Second task" }] });
  await openSession(page);

  await page.getByRole("button", { name: "Dictate message" }).click();
  await expect.poll(async () => (await speechCounts(page))?.startCalls).toBe(1);

  await page.getByLabel("Switch task").selectOption("bot-2");
  await expect.poll(async () => (await speechCounts(page))?.abortCalls).toBeGreaterThanOrEqual(1);

  // A fresh composer on the new session still works, and going home aborts it.
  await page.getByRole("button", { name: "Dictate message" }).click();
  await expect.poll(async () => (await speechCounts(page))?.startCalls).toBe(1);
  await page.getByRole("button", { name: "Back to Cowork home" }).click();
  await expect.poll(async () => (await speechCounts(page))?.abortCalls).toBeGreaterThanOrEqual(1);
  expect(consoleErrors).toEqual([]);
});
