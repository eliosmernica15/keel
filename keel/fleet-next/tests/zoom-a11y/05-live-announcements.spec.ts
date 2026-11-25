import { test as baseTest } from "@playwright/test";
import {
  test,
  expect,
  DESTINATIONS,
  gotoDestination,
  openAppThemed,
  accessibilityTree,
  axSubtreeText,
} from "./helpers";

/** Dynamic proof that status / error / streaming changes reach the platform
 * accessibility tree through live regions — not just a static DOM scan. */
test("status notice is announced through an aria-live polite status node", async ({
  page,
  consoleErrors,
}) => {
  void consoleErrors;
  await openAppThemed(page, "dark");
  await gotoDestination(page, DESTINATIONS[2]); // Duet owns a local-only reset command

  await page.keyboard.press("Control+k");
  const input = page.getByRole("textbox", { name: "Search commands" });
  await expect(input).toBeFocused();
  await input.fill("Reset Duet layout");
  await page.keyboard.press("Enter");

  const notice = await page.locator(".keel-notices").innerText();
  expect(notice).toContain("Duet layout reset to the default tabs and panes.");
  const ax = await accessibilityTree(page);
  const statusNodes = ax.filter((n) => n.role === "status" && n.live === "polite");
  expect(statusNodes.length, "AX tree must expose a polite status live region").toBeGreaterThan(0);
  const announced = statusNodes.some((n) =>
    axSubtreeText(ax, n.id).includes("Duet layout reset"),
  );
  expect(announced, `status text missing from AX live region: ${JSON.stringify(statusNodes.map((n) => axSubtreeText(ax, n.id)))}`).toBeTruthy();
  console.log("LIVE_STATUS", JSON.stringify({ notice, liveNodes: statusNodes.length }));
});

// The deliberately failing 500 is an expected browser console error, so this
// test uses the base fixture instead of the strict console-error gate.
baseTest("bridge error is announced through a role=alert node", async ({ page }) => {
  await openAppThemed(page, "dark", {
    failPaths: {
      providers: {
        status: 500,
        body: { error: "qa_forced_failure", detail: "Forced QA providers failure" },
      },
    },
  });
  const banner = page.locator('[role="alert"]').filter({ hasText: "Forced QA providers failure" });
  await expect(banner.first()).toBeVisible();
  const ax = await accessibilityTree(page);
  const alerts = ax.filter((n) => n.role === "alert");
  const matching = alerts.find((n) => axSubtreeText(ax, n.id).includes("Forced QA providers failure"));
  expect(
    matching,
    `error text missing from AX alert: ${JSON.stringify(alerts.map((n) => axSubtreeText(ax, n.id)))}`,
  ).toBeTruthy();
  console.log("LIVE_ERROR", JSON.stringify({ alertText: axSubtreeText(ax, matching!.id) }));
});

test("streaming delta is announced by a polite live bubble inside role=log", async ({
  page,
  consoleErrors,
}) => {
  void consoleErrors;
  const bot = {
    id: "qa-bot",
    name: "QA task",
    role: "Assistant",
    engine: "echo",
    provider: "auto",
    model: "",
    state: "idle",
  };
  const bridge = await openAppThemed(page, "dark", {
    bots: [bot],
    rows: [
      {
        seq: 1,
        bot_id: "qa-bot",
        kind: "message",
        role: "user",
        body: { content: "start" },
        created_at: "2026-11-24T10:00:00Z",
      },
    ],
    holdEvents: true,
    eventsBody: `data: ${JSON.stringify({ type: "stream", delta: "Hello from stream" })}\n\n`,
  });

  await page.getByLabel("Open an existing task").selectOption("qa-bot");
  await expect(page.getByRole("log", { name: "Cowork conversation" })).toBeVisible();
  bridge.releaseEvents?.();

  const bubble = page.locator('[data-cowork-live="true"][aria-live="polite"]');
  await expect(bubble).toBeVisible();
  await expect(bubble).toContainText("Hello from stream");

  const ax = await accessibilityTree(page);
  const streamed = ax
    .filter((n) => n.live === "polite")
    .some((n) => axSubtreeText(ax, n.id).includes("Hello from stream"));
  expect(streamed, "streamed text must be in a polite AX live region").toBeTruthy();
  expect(ax.filter((n) => n.role === "log").length, "conversation role=log must be in AX tree").toBeGreaterThan(0);
  console.log("LIVE_STREAM", JSON.stringify({ bubbleText: await bubble.innerText(), axLog: true }));
});
