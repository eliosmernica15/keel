import { openApp, expect, test, routeAcceptanceBridge } from "./fixtures";

const DOWNLOAD_URL = "https://keel-desktop.vercel.app/download";

/** The in-app desktop entry point: exactly one native control, safe attributes. */
test("application exposes exactly one Get Keel Desktop control with a safe external link", async ({ page, consoleErrors }) => {
  void consoleErrors;
  await routeAcceptanceBridge(page);
  await openApp(page);

  const links = await page.evaluate(() =>
    Array.from(document.querySelectorAll("a"))
      .filter((a) => {
        const url = new URL((a as HTMLAnchorElement).href, location.href);
        return url.pathname === "/download" || /Get Keel Desktop/i.test(a.textContent || a.getAttribute("aria-label") || "");
      })
      .map((a) => ({
        href: (a as HTMLAnchorElement).href,
        target: a.getAttribute("target"),
        rel: a.getAttribute("rel"),
        text: (a.textContent || "").trim(),
        label: a.getAttribute("aria-label"),
      })),
  );
  expect(links, `expected one /download control, saw ${JSON.stringify(links)}`).toHaveLength(1);

  const control = page.getByRole("link", { name: "Get Keel Desktop" });
  await expect(control).toBeVisible();
  await expect(control).toHaveAttribute("href", DOWNLOAD_URL);
  await expect(control).toHaveAttribute("target", "_blank");
  const rel = (await control.getAttribute("rel") ?? "").split(/\s+/).filter(Boolean);
  expect(rel, "reverse-tabnabbing and referrer leakage must both be blocked").toEqual(
    expect.arrayContaining(["noopener", "noreferrer"]),
  );
  expect(rel).toHaveLength(2);

  // No competing button/control with the same accessible name.
  await expect(page.getByRole("button", { name: "Get Keel Desktop" })).toHaveCount(0);
});

test("the desktop link is keyboard operable and opens the approved download URL", async ({ page, consoleErrors }) => {
  void consoleErrors;
  await routeAcceptanceBridge(page);
  // Context-level route: the popup is a new page and does not inherit page.route.
  // No real outbound request is made to the external host.
  await page.context().route("https://keel-desktop.vercel.app/**", (route) =>
    route.fulfill({ status: 200, contentType: "text/html", body: "<title>Keel download (QA fixture)</title>" }));
  await openApp(page);

  const control = page.getByRole("link", { name: "Get Keel Desktop" });
  await control.focus();
  await expect(control).toBeFocused();

  const [popup] = await Promise.all([
    page.waitForEvent("popup"),
    control.press("Enter"),
  ]);
  await popup.waitForLoadState("domcontentloaded");
  expect(popup.url()).toBe(DOWNLOAD_URL);
  await expect(popup).toHaveTitle(/Keel download \(QA fixture\)/);
  await popup.close();
});
