import { test, expect, wizard } from "./fixtures";

test("pre-seeded wizard state renders and reloads with no console errors or hydration warnings", async ({
  page, consoleErrors, hydrationWarnings,
}) => {
  void consoleErrors; void hydrationWarnings;
  await page.addInitScript(() => {
    localStorage.setItem("keel-onboarding-done", "false");
    localStorage.setItem("keel-onboarding:step", JSON.stringify("workspace"));
    localStorage.setItem("keel-onboarding:checklist", JSON.stringify({
      surface: "done", provider: "done", workspace: "pending", permission: "pending",
      capabilities: "pending", channels: "pending", tour: "pending",
    }));
    localStorage.setItem("keel-mode", "plan");
  });

  await page.goto("/");
  await expect(wizard(page).getByRole("heading", { name: "Choose a workspace" })).toBeVisible();
  await expect(wizard(page).getByText("Step 4 of 8")).toBeVisible();
  await expect(wizard(page).getByText("2/4 required")).toBeVisible();

  await page.reload();
  await expect(wizard(page).getByRole("heading", { name: "Choose a workspace" })).toBeVisible();
  await expect(wizard(page).getByText("2/4 required")).toBeVisible();
});
