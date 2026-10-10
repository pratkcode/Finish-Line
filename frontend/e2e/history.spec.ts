import { expect, test, type APIRequestContext, type Page } from "@playwright/test";

// Academic history, transfer credit, and the plan timeline, through the UI.
const API = "http://localhost:8000";

async function startSession(page: Page, request: APIRequestContext, fields: Record<string, unknown> = {}) {
  const session = await (
    await request.post(`${API}/api/sessions`, {
      data: { program_slug: "umd-information-science", current_term: "Fall 2026", max_credits_per_term: 15, ...fields },
    })
  ).json();
  await page.goto("/");
  await page.evaluate((id) => localStorage.setItem("finishline.sessionId", id), session.id);
  return session.id as string;
}

test.afterEach(async ({ page, request }) => {
  const id = await page.evaluate(() => localStorage.getItem("finishline.sessionId")).catch(() => null);
  if (id) await request.delete(`${API}/api/sessions/${id}`);
});

const semester = (page: Page, term: string) => page.locator(`li[data-history-term="${term}"]`);

test("a transfer student records semesters at two schools; only verified credit counts", async ({ page, request }) => {
  await startSession(page, request);
  await page.goto("/history");
  await expect(page.getByTestId("history-applicable")).toHaveText("0");

  // A semester at a community college.
  await page.locator("#new-term").selectOption("Fall 2024");
  await page.locator("#new-term-school").selectOption("other");
  await page.locator("#new-term-institution").fill("Montgomery College");
  await page.getByRole("button", { name: "Add semester" }).click();
  const fall = semester(page, "Fall 2024");
  await expect(fall).toContainText("Montgomery College");

  // A course there, with a UMD equivalent, reported by the student.
  await fall.getByRole("button", { name: "+ Add a course or credit" }).click();
  await fall.getByLabel("Course code at that school").fill("ENG 101");
  await fall.getByLabel("Title").fill("English Composition");
  await fall.getByLabel("UMD equivalent").fill("ENGL101");
  await fall.getByRole("button", { name: "Save credit" }).click();
  const transfer = fall.locator('li[data-transfer="ENG 101"]');
  await expect(transfer.getByTestId("transfer-status")).toHaveText("Not counted until verified");
  await expect(page.getByTestId("history-earned")).toHaveText("3");
  await expect(page.getByTestId("history-applicable")).toHaveText("0");
  await expect(page.getByTestId("pending")).toContainText("ENG 101");

  // Once UMD has verified it, it counts (as ENGL101).
  await transfer.getByLabel("Verification for ENG 101").selectOption("umd_verified");
  await expect(transfer.getByTestId("transfer-status")).toHaveText("Counted");
  await expect(page.getByTestId("history-applicable")).toHaveText("3");

  // A UMD semester with a completed course.
  await page.locator("#new-term").selectOption("Spring 2025");
  await page.locator("#new-term-school").selectOption("umd");
  await page.getByRole("button", { name: "Add semester" }).click();
  const spring = semester(page, "Spring 2025");
  await spring.getByRole("button", { name: "+ Add a UMD course" }).click();
  await spring.getByLabel("Search UMD courses").fill("INST126");
  await spring.getByTestId("history-search-results").locator("li", { hasText: "INST126" }).first()
    .getByRole("button", { name: "Add" }).click();
  await expect(spring.locator('li[data-history-course="INST126"]')).toBeVisible();
  await expect(page.getByTestId("history-applicable")).toHaveText("6");

  // Semesters are in order, and it's all saved.
  await page.reload();
  await expect(page.locator("li[data-history-term]")).toHaveCount(2);
  const order = await page.locator("li[data-history-term]").evaluateAll((els) =>
    els.map((el) => el.getAttribute("data-history-term")),
  );
  expect(order).toEqual(["Fall 2024", "Spring 2025"]);
  await expect(page.getByTestId("history-applicable")).toHaveText("6");

  // Degree progress uses the same record: Academic Writing is met through ENGL101.
  await page.goto("/progress");
  await expect(page.getByTestId("applicable-credits")).toContainText("6");

  // Removing the community-college semester removes its credit.
  await page.goto("/history");
  page.once("dialog", (d) => d.accept());
  await page.getByRole("button", { name: "Remove Fall 2024 at Montgomery College" }).click();
  await expect(page.getByTestId("history-applicable")).toHaveText("3");
});

test("Gen Ed met by a verified associate degree counts; a reported one doesn't", async ({ page, request }) => {
  await startSession(page, request);
  await page.goto("/history");
  await page.locator("#fulfillment-requirement").selectOption("umd.gened");
  await page.getByLabel("How it was met").selectOption("associate_degree");
  await page.getByRole("button", { name: "Record requirement" }).click();
  const row = page.locator('li[data-fulfillment="umd.gened"]');
  await expect(row.getByTestId("fulfillment-status")).toHaveText("Not counted until verified");

  await row.getByLabel("Verification for General Education").selectOption("umd_verified");
  await expect(row.getByTestId("fulfillment-status")).toHaveText("Counted");

  // Degree progress agrees: the Gen Ed section is complete.
  await page.goto("/progress");
  const gened = page.locator("section", { has: page.getByRole("heading", { name: "General Education", exact: true }) });
  await expect(gened).toContainText("Completed");
});

test("the plan shows history, the current semester in progress, and starts where the student chooses", async ({
  page,
  request,
}) => {
  const id = await startSession(page, request);
  const current = await (
    await request.post(`${API}/api/sessions/${id}/history/terms`, { data: { term: "Fall 2026", at_umd: true } })
  ).json();
  const termId = current.terms[0].id;
  await request.post(`${API}/api/sessions/${id}/courses`, {
    data: { code: "INST126", status: "in_progress", academic_term_id: termId },
  });

  await page.goto("/graduation-plan");
  await expect(page.getByTestId("current-term")).toContainText("Fall 2026 · in progress");
  await expect(page.getByTestId("current-term")).toContainText("INST126 (in progress)");
  await expect(page.getByTestId("in-progress-credits")).toHaveText("3");
  // The plan starts after the current semester by default.
  await expect(page.locator("#plan-start")).toHaveValue("Spring 2027");
  await expect(page.locator("li[data-term]").first()).toHaveAttribute("data-term", "Spring 2027");

  // Choose to start in Summer 2027, with Summer terms.
  await page.locator("#include-summer").click();
  await expect(page.locator("#include-summer")).toBeChecked();
  await expect(page.locator("li[data-term='Summer 2027']")).toBeVisible();
  await page.locator("#plan-start").selectOption("Summer 2027");
  await expect(page.locator("li[data-term]").first()).toHaveAttribute("data-term", "Summer 2027");
  await page.reload();
  await expect(page.locator("#plan-start")).toHaveValue("Summer 2027");

  // A recommendation starts there and explains each course.
  await page.getByRole("button", { name: "Generate a recommended plan" }).click();
  const panel = page.getByRole("region", { name: "Recommended plan" });
  await expect(panel).toContainText("Starts Summer 2027");
  await expect(panel.locator("li[data-recommended='INST326']")).toContainText("Why:");
  // INST126 is in progress, so it isn't recommended again.
  await expect(panel.locator("li[data-recommended='INST126']")).toHaveCount(0);

  // Nothing is saved until accepted.
  await page.reload();
  await expect(page.locator("li[data-course]")).toHaveCount(0);
});

test("a target graduation semester is checked against the plan", async ({ page, request }) => {
  await startSession(page, request);
  await page.goto("/graduation-plan");
  await page.locator("#target-graduation").selectOption("Fall 2027");
  await expect(page.getByTestId("target-check")).toContainText("can't be checked");
  await page.getByRole("button", { name: "Generate a recommended plan" }).click();
  await expect(page.getByRole("region", { name: "Recommended plan" })).toContainText("after your target of Fall 2027");
  await expect(page.locator("li[data-term='Fall 2027']")).toBeVisible();
});
