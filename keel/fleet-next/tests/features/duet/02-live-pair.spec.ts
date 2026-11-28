import { expect, test } from "./fixtures";

// Live Pair acceptance: hand-off and take-over use real session/turn routes,
// follow state is visible, Esc takes over, and ghost text stays hidden because
// the bridge exposes no completion endpoint.

async function openLive(page: import("@playwright/test").Page) {
  await page.locator('[data-pair-mode-button="live"]').click();
  await expect(page.locator('[data-duet-pair-mode="live"]')).toBeVisible();
}

test("hand-off to the agent uses the chat session and message routes", async ({ harness }) => {
  const { gotoDuet, openPair, page, requests } = harness;
  await gotoDuet();
  await openPair();
  await openLive(page);

  const live = page.locator('[data-live-root="true"]');
  await expect(live).toHaveAttribute("data-live-driver", "you");
  await page.getByRole("button", { name: /Agent drives/ }).click();
  await expect(live).toHaveAttribute("data-live-driver", "agent");

  const chats = requests.filter(
    (r) => r.method === "POST" && r.path === "/api/bridge/projects/p1/chat",
  );
  expect(chats).toHaveLength(1);
  const messages = requests.filter(
    (r) => r.method === "POST" && r.path === "/api/bridge/bots/chat-b/messages",
  );
  expect(messages).toHaveLength(1);
  expect(String((messages[0].body as { content?: unknown })?.content ?? "")).toContain("Hand-off");
  await expect(live).toHaveAttribute("data-live-driver", "agent");
  await expect(page.getByText("Agent drives", { exact: true }).first()).toBeVisible();
  await expect(page.locator('[data-live-notice="true"]')).toContainText("Handed off to project chat");
});

test("Esc takes over and calls the real cancel route", async ({ harness }) => {
  const { gotoDuet, openPair, page, requests } = harness;
  await gotoDuet();
  await openPair();
  await openLive(page);
  await page.getByRole("button", { name: /Agent drives/ }).click();
  await expect(page.locator('[data-live-root="true"]')).toHaveAttribute("data-live-driver", "agent");

  await page.keyboard.press("Escape");
  const cancels = requests.filter(
    (r) => r.method === "POST" && r.path === "/api/bridge/bots/chat-b/cancel",
  );
  expect(cancels).toHaveLength(1);
  await expect(page.locator('[data-live-root="true"]')).toHaveAttribute("data-live-driver", "you");
  await expect(page.locator('[data-live-notice="true"]')).toContainText("You drive again");
});

test("follow state is visible and the cursor never claims an unreported position", async ({ harness }) => {
  const { gotoDuet, openPair, page, state } = harness;
  await gotoDuet();
  await openPair();
  await openLive(page);
  await page.getByRole("button", { name: /Agent drives/ }).click();

  const live = page.locator('[data-live-root="true"]');
  await expect(live).toHaveAttribute("data-live-follow", "true");
  await expect(page.locator('[data-live-cursor="true"]')).toContainText("not reported by bridge");

  state.botRows["chat-b"] = [
    { seq: 9, kind: "message", body: { role: "assistant", content: "step" } },
  ];
  await page.getByRole("button", { name: /Follow agent cursor/ }).click();
  await expect(live).toHaveAttribute("data-live-follow", "false");
  await expect(page.locator('[data-live-cursor="true"]')).toContainText("not reported by bridge");

  await page.getByRole("button", { name: /Follow agent cursor/ }).click();
  await expect(live).toHaveAttribute("data-live-follow", "true");
  await expect(page.locator('[data-live-cursor="true"]')).toContainText("transcript row 9");
});

test("ghost text is off by default and no control appears without a completion endpoint", async ({ harness }) => {
  const { gotoDuet, openPair, page, requests } = harness;
  await gotoDuet();
  await openPair();
  await openLive(page);

  await expect(page.locator('[data-ghost="unavailable"]')).toBeVisible();
  await expect(page.locator('[data-ghost="unavailable"]')).toContainText("POST /api/bridge/completions");
  expect(await page.getByRole("button", { name: /ghost|completion/i }).count()).toBe(0);
  expect(await page.locator('[data-live-root="true"]').getByRole("textbox").count()).toBe(0);
  expect(requests.filter((r) => /completion|ghost/i.test(r.path))).toEqual([]);

  await page.getByRole("button", { name: /Switch to review pair/ }).click();
  await expect(page.locator('[data-duet-pair-mode="review"]')).toBeVisible();
});
