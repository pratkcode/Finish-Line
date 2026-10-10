import { expect, test, type APIRequestContext, type Page } from "@playwright/test";

// Each test gets its own planning session, created through the API and loaded
// into the browser the same way the app stores it.
const API = "http://localhost:8000";
const COMPLETED = ["ENGL101", "MATH115", "PSYC100", "STAT100", "INST126", "INST201", "SOCY105"];

async function startSession(page: Page, request: APIRequestContext, program = "umd-information-science") {
  const session = await (
    await request.post(`${API}/api/sessions`, {
      data: { program_slug: program, current_term: "Spring 2026", max_credits_per_term: 15 },
    })
  ).json();
  for (const code of COMPLETED) {
    await request.post(`${API}/api/sessions/${session.id}/courses`, { data: { code, grade: "B" } });
  }
  await page.goto("/");
  await page.evaluate((id) => localStorage.setItem("finishline.sessionId", id), session.id);
  return session.id as string;
}

const term = (page: Page, name: string) => page.locator(`li[data-term="${name}"]`);
const termCredits = (page: Page, name: string) => term(page, name).getByTestId("term-credits");

async function addCourse(page: Page, semester: string, code: string) {
  await term(page, semester).getByRole("button", { name: `+ Add a course to ${semester}` }).click();
  await term(page, semester).getByLabel(`Search courses to add to ${semester}`).fill(code);
  const row = term(page, semester).getByTestId("search-results").locator("li", { hasText: code }).first();
  await row.getByRole("button", { name: "Add" }).click();
  await expect(term(page, semester).locator(`li[data-course="${code}"]`)).toBeVisible();
}

test.afterEach(async ({ page, request }) => {
  const id = await page.evaluate(() => localStorage.getItem("finishline.sessionId")).catch(() => null);
  if (id) await request.delete(`${API}/api/sessions/${id}`);
});

test("switching majors is saved, keeps completed courses, and recalculates requirements", async ({
  page,
  request,
}) => {
  await startSession(page, request);
  await page.goto("/profile");
  const major = page.locator("#major");
  await expect(major).toHaveValue("umd-information-science");

  await major.selectOption("umd-technology-info-design");
  await expect(major).toHaveValue("umd-technology-info-design");
  await page.reload();
  await expect(page.locator("#major")).toHaveValue("umd-technology-info-design");
  // Completed courses are untouched.
  for (const code of COMPLETED) await expect(page.getByText(`${code} –`)).toBeVisible();

  // Degree progress now follows the TID requirements.
  await page.goto("/progress");
  await expect(page.getByRole("heading", { name: "Technology and Information Design Major" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Information Science Major" })).toHaveCount(0);
});

test("a major without verified requirements is explained, not planned", async ({ page, request }) => {
  await startSession(page, request);
  await page.goto("/profile");
  await page.locator("#major").selectOption("umd-computer-science");
  await expect(page.getByText("Requirements for Computer Science aren't verified in Finish Line yet")).toBeVisible();

  await page.goto("/graduation-plan");
  await expect(page.getByText("Requirements for Computer Science aren't verified in Finish Line yet")).toBeVisible();
  await expect(page.getByRole("button", { name: /recommended plan/i })).toBeDisabled();
  await expect(page.getByTestId("projected-graduation")).toHaveText("Not yet");
});

test("the plan starts empty and nothing is added automatically", async ({ page, request }) => {
  await startSession(page, request);
  await page.goto("/graduation-plan");
  await expect(page.getByText("Your plan is empty.").first()).toBeVisible();
  await expect(page.getByTestId("planned-credits")).toHaveText("0");
  await expect(page.locator("li[data-course]")).toHaveCount(0);
});

test("adding, moving, and removing courses updates credits immediately and persists", async ({
  page,
  request,
}) => {
  await startSession(page, request);
  await page.goto("/graduation-plan");

  await addCourse(page, "Fall 2026", "INST326");
  await expect(termCredits(page, "Fall 2026")).toHaveText("3 / 15 cr");
  await expect(page.getByTestId("planned-credits")).toHaveText("3");

  await addCourse(page, "Fall 2026", "INST327");
  await expect(termCredits(page, "Fall 2026")).toHaveText("6 / 15 cr");
  await expect(page.getByTestId("planned-credits")).toHaveText("6");
  await expect(page.getByTestId("remaining-credits")).toHaveText("93"); // 120 - 21 completed - 6

  // Move: the semesters change, the total doesn't.
  await page.getByLabel("Move INST327 to another semester").selectOption("Spring 2027");
  await expect(termCredits(page, "Fall 2026")).toHaveText("3 / 15 cr");
  await expect(termCredits(page, "Spring 2027")).toHaveText("3 / 15 cr");
  await expect(page.getByTestId("planned-credits")).toHaveText("6");

  // Remove: totals drop right away, and nothing is put back.
  await page.getByRole("button", { name: "Remove INST326 from the plan" }).click();
  await expect(termCredits(page, "Fall 2026")).toHaveText("0 / 15 cr");
  await expect(page.getByTestId("planned-credits")).toHaveText("3");
  await expect(page.locator('li[data-course="INST326"]')).toHaveCount(0);

  // Reloading shows the same saved plan.
  await page.reload();
  await expect(termCredits(page, "Spring 2027")).toHaveText("3 / 15 cr");
  await expect(page.getByTestId("planned-credits")).toHaveText("3");
  await expect(page.locator("li[data-course]")).toHaveCount(1);
});

test("duplicates are prevented and bad prerequisite order is flagged", async ({ page, request }) => {
  await startSession(page, request);
  await page.goto("/graduation-plan");
  await addCourse(page, "Fall 2026", "INST346");
  await expect(page.getByText("Needs INST326 first, and it isn't in your plan.").first()).toBeVisible();

  // The same course can't be added again.
  const spring = term(page, "Spring 2027");
  await spring.getByRole("button", { name: "+ Add a course to Spring 2027" }).click();
  await spring.getByLabel("Search courses to add to Spring 2027").fill("INST346");
  await expect(spring.getByText("In plan (Fall 2026)")).toBeVisible();
  await expect(
    spring.getByTestId("search-results").locator("li", { hasText: "INST346" }).getByRole("button", { name: "Add" }),
  ).toHaveCount(0);
  // A completed course can't be planned.
  await spring.getByLabel("Search courses to add to Spring 2027").fill("INST201");
  await expect(spring.getByTestId("search-results").locator("li", { hasText: "INST201" }).getByText("Completed")).toBeVisible();

  // Fixing the order clears the warning.
  await page.getByRole("button", { name: "Cancel" }).click();
  await addCourse(page, "Fall 2026", "INST326");
  await addCourse(page, "Fall 2026", "INST327");
  await page.getByLabel("Move INST346 to another semester").selectOption("Spring 2027");
  await expect(page.getByText(/Needs INST32[67] first/)).toHaveCount(0);
});

test("a recommendation is only added when accepted, and stays editable", async ({ page, request }) => {
  await startSession(page, request);
  await page.goto("/graduation-plan");
  await page.getByRole("button", { name: "Generate a recommended plan" }).click();
  const panel = page.getByRole("region", { name: "Recommended plan" });
  await expect(panel).toBeVisible();
  await expect(page.getByTestId("planned-credits")).toHaveText("0");

  await panel.getByRole("button", { name: /Add \d+ courses to my plan/ }).click();
  await expect(panel).toHaveCount(0);
  const planned = Number(await page.getByTestId("planned-credits").textContent());
  expect(planned).toBeGreaterThan(30);

  // Edit the accepted plan: removing a course lowers the total by its credits.
  const first = page.locator("li[data-course]").first();
  const code = await first.getAttribute("data-course");
  await page.getByRole("button", { name: `Remove ${code} from the plan` }).click();
  await expect(page.getByTestId("planned-credits")).toHaveText(String(planned - 3));
});
