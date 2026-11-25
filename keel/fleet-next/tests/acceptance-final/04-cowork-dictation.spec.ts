import { openApp, expect, test, routeAcceptanceBridge, installSpeechRecognitionMock,
  speechState, emitSpeechResult, emitSpeechError, emitSpeechEnd } from "./fixtures";

/**
 * Agent G independent acceptance — Cowork dictation with a MOCKED
 * SpeechRecognition. No microphone or speech service is used: the mock is
 * installed before navigation and every start/stop call is observable.
 * Acceptance: insert at the captured caret, never auto-send, explicit stop,
 * explicit error states, and an honest unsupported-browser state.
 */

async function openComposer(page: import("@playwright/test").Page) {
  await openApp(page);
  const box = page.getByRole("textbox", { name: "Message Keel" });
  await expect(box).toBeVisible();
  return box;
}

function sentMessageCount(calls: Array<{ method: string; path: string }>): number {
  return calls.filter((c) => c.method === "POST" && /\/messages$/.test(c.path)).length;
}

test("dictation inserts the final transcript at the caret and never auto-sends", async ({ page, consoleErrors }) => {
  void consoleErrors;
  const fixture = await routeAcceptanceBridge(page);
  await installSpeechRecognitionMock(page);
  const box = await openComposer(page);

  await box.fill("hello world");
  // Put the caret between the two words; only the click starts recognition.
  await box.evaluate((el) => (el as HTMLTextAreaElement).setSelectionRange(5, 5));
  expect((await speechState(page)).count).toBe(0);

  await page.getByRole("button", { name: "Dictate message" }).click();
  expect((await speechState(page)).calls).toContain("start");
  await expect(page.getByText(/Listening… speak now/)).toBeVisible();

  await emitSpeechResult(page, "brave");
  await expect(box).toHaveValue("hello brave world");
  expect(sentMessageCount(fixture.calls), "dictation must never send a message").toBe(0);

  await emitSpeechEnd(page);
  await expect(page.getByText(/Dictation stopped — transcript inserted at the cursor\. Nothing was sent\./)).toBeVisible();
  await expect(page.getByRole("button", { name: "Dictate message" })).toBeVisible();
  expect(sentMessageCount(fixture.calls)).toBe(0);
});

test("dictation replaces a text selection instead of appending", async ({ page, consoleErrors }) => {
  void consoleErrors;
  await routeAcceptanceBridge(page);
  await installSpeechRecognitionMock(page);
  const box = await openComposer(page);

  await box.fill("alpha beta");
  await box.evaluate((el) => (el as HTMLTextAreaElement).setSelectionRange(6, 10));
  await page.getByRole("button", { name: "Dictate message" }).click();
  await emitSpeechResult(page, "gamma");
  await expect(box).toHaveValue("alpha gamma");
  await emitSpeechEnd(page);
});

test("Stop dictation invokes recognition.stop() and inserts no transcript", async ({ page, consoleErrors }) => {
  void consoleErrors;
  const fixture = await routeAcceptanceBridge(page);
  await installSpeechRecognitionMock(page);
  const box = await openComposer(page);

  await box.fill("draft stays");
  await page.getByRole("button", { name: "Dictate message" }).click();
  await expect(page.getByText(/Listening… speak now/)).toBeVisible();

  await page.getByRole("button", { name: "Stop dictation" }).click();
  expect((await speechState(page)).calls).toContain("stop");
  await emitSpeechEnd(page);

  await expect(box).toHaveValue("draft stays");
  await expect(page.getByText(/Dictation stopped — no transcript was inserted\./)).toBeVisible();
  expect(sentMessageCount(fixture.calls)).toBe(0);
});

test("a speech recognition error is announced and inserts nothing", async ({ page, consoleErrors }) => {
  void consoleErrors;
  const fixture = await routeAcceptanceBridge(page);
  await installSpeechRecognitionMock(page);
  const box = await openComposer(page);

  await box.fill("unchanged");
  await page.getByRole("button", { name: "Dictate message" }).click();
  await emitSpeechError(page, "not-allowed");

  const alert = page.getByRole("alert").filter({ hasText: /Microphone permission was denied/ }).first();
  await expect(alert).toBeVisible();
  await expect(alert).toHaveAttribute("aria-live", "assertive");
  await expect(box).toHaveValue("unchanged");
  expect(sentMessageCount(fixture.calls)).toBe(0);

  // A late onend must not overwrite the error with a false success.
  await emitSpeechEnd(page);
  await expect(alert).toBeVisible();
});

test("unsupported browsers show an honest disabled control and no microphone call", async ({ page, consoleErrors }) => {
  void consoleErrors;
  await routeAcceptanceBridge(page);
  await page.addInitScript(() => {
    const scope = window as unknown as Record<string, unknown>;
    delete scope.SpeechRecognition;
    delete scope.webkitSpeechRecognition;
  });
  await openComposer(page);

  await expect(page.getByText("Dictation unavailable in this browser.")).toBeVisible();
  const disabled = page.getByRole("button", {
    name: "Dictation unavailable — speech recognition is not supported in this browser",
  });
  await expect(disabled).toBeDisabled();
});
