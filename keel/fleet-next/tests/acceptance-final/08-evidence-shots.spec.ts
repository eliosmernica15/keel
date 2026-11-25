import fs from "node:fs";
import path from "node:path";
import { openApp, gotoTop, expect, test, routeAcceptanceBridge,
  installSpeechRecognitionMock } from "./fixtures";

/** Captures visual evidence for FRONTEND-FINALIZATION-QA.md. No assertions on pixels. */
const SHOTS = path.join(__dirname, "screenshots");
fs.mkdirSync(SHOTS, { recursive: true });

test("capture Fleet transcript controls and the rewind dialog", async ({ page, consoleErrors }) => {
  void consoleErrors;
  await routeAcceptanceBridge(page);
  await openApp(page);
  await gotoTop(page, "Fleet");
  await page.getByRole("button", { name: "Select Alpha" }).locator("..")
    .getByRole("button", { name: "Details" }).click();
  const drawer = page.getByRole("dialog", { name: "Alpha details" });
  await drawer.getByRole("tab", { name: "Activity / History" }).click();
  await expect(drawer.getByRole("heading", { name: "Transcript" })).toBeVisible();
  await page.screenshot({ path: path.join(SHOTS, "fleet-transcript-controls.png"), fullPage: false });

  await drawer.getByRole("button", { name: /Rewind transcript/ }).click();
  await expect(page.getByRole("dialog", { name: "Rewind transcript?" })).toBeVisible();
  await page.screenshot({ path: path.join(SHOTS, "fleet-rewind-dialog.png"), fullPage: false });
});

test("capture the single in-app desktop link", async ({ page, consoleErrors }) => {
  void consoleErrors;
  await routeAcceptanceBridge(page);
  await openApp(page);
  const link = page.getByRole("link", { name: "Get Keel Desktop" });
  await expect(link).toBeVisible();
  await page.screenshot({ path: path.join(SHOTS, "desktop-link.png"), fullPage: false });
});

test("capture Cowork dictation listening state", async ({ page, consoleErrors }) => {
  void consoleErrors;
  await routeAcceptanceBridge(page);
  await installSpeechRecognitionMock(page);
  await openApp(page);
  const box = page.getByRole("textbox", { name: "Message Keel" });
  await box.fill("Draft before dictation ");
  await page.getByRole("button", { name: "Dictate message" }).click();
  await expect(page.getByText(/Listening… speak now/)).toBeVisible();
  await page.screenshot({ path: path.join(SHOTS, "cowork-dictation-listening.png"), fullPage: false });
});
