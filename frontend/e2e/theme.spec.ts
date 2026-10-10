import { expect, test, type Page } from "@playwright/test";

// Light/dark theme: system default, the toggle, persistence, and no flash.
const theme = (page: Page) => page.locator("html").getAttribute("data-theme");
const bodyBackground = (page: Page) => page.evaluate(() => getComputedStyle(document.body).backgroundColor);
const DARK_PAGE = "rgb(14, 18, 24)"; // --page in dark mode
const LIGHT_PAGE = "rgb(248, 250, 252)";

test("the first visit follows the operating system setting", async ({ browser }) => {
  for (const [colorScheme, expected, background] of [
    ["dark", "dark", DARK_PAGE],
    ["light", "light", LIGHT_PAGE],
  ] as const) {
    const context = await browser.newContext({ colorScheme });
    const page = await context.newPage();
    await page.goto("/courses");
    expect(await theme(page)).toBe(expected);
    expect(await bodyBackground(page)).toBe(background);
    await context.close();
  }
});

test("the toggle switches instantly and the choice persists across pages and reloads", async ({ browser }) => {
  const context = await browser.newContext({ colorScheme: "light" });
  const page = await context.newPage();
  const errors: string[] = [];
  page.on("console", (m) => m.type() === "error" && errors.push(m.text()));
  page.on("pageerror", (e) => errors.push(e.message));

  await page.goto("/courses");
  const toggle = page.getByRole("button", { name: "Switch to dark mode" });
  await toggle.click();
  expect(await theme(page)).toBe("dark");
  await expect.poll(() => bodyBackground(page)).toBe(DARK_PAGE);
  await expect(page.getByRole("button", { name: "Switch to light mode" })).toBeVisible();

  // Client-side navigation keeps it.
  await page.getByRole("link", { name: "Requirements" }).click();
  await expect(page).toHaveURL(/requirements/);
  expect(await theme(page)).toBe("dark");

  // So does a reload, even though the system is light: the student's choice wins.
  await page.reload();
  expect(await theme(page)).toBe("dark");

  // And back to light.
  await page.getByRole("button", { name: "Switch to light mode" }).click();
  expect(await theme(page)).toBe("light");
  await page.reload();
  expect(await theme(page)).toBe("light");
  expect(errors.filter((e) => /hydrat/i.test(e))).toEqual([]);
  await context.close();
});

test("the saved theme is applied before the page paints (no flash)", async ({ browser }) => {
  const context = await browser.newContext({ colorScheme: "light" });
  await context.addInitScript(() => localStorage.setItem("finishline.theme", "dark"));
  const page = await context.newPage();
  // Record the theme at the first point a script can observe the document.
  await page.addInitScript(() => {
    document.addEventListener("DOMContentLoaded", () => {
      (window as unknown as { firstTheme: string | null }).firstTheme =
        document.documentElement.getAttribute("data-theme");
    });
  });
  await page.goto("/dashboard", { waitUntil: "domcontentloaded" });
  expect(await page.evaluate(() => (window as unknown as { firstTheme: string | null }).firstTheme)).toBe("dark");
  await context.close();
});

test("without a saved choice, the theme follows system changes", async ({ page }) => {
  await page.emulateMedia({ colorScheme: "light" });
  await page.goto("/courses");
  expect(await theme(page)).toBe("light");
  await page.emulateMedia({ colorScheme: "dark" });
  await expect.poll(() => theme(page)).toBe("dark");
});

test("the toggle works from the keyboard and on a phone", async ({ browser }) => {
  const context = await browser.newContext({ colorScheme: "light", viewport: { width: 390, height: 844 } });
  const page = await context.newPage();
  await page.goto("/dashboard");
  const toggle = page.getByTestId("theme-toggle");
  await expect(toggle).toBeVisible();
  await toggle.focus();
  // A visible focus ring.
  const outline = await toggle.evaluate((el) => getComputedStyle(el).outlineStyle);
  expect(outline).toBe("solid");
  await page.keyboard.press("Enter");
  expect(await theme(page)).toBe("dark");
  await context.close();
});
