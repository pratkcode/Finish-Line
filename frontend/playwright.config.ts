import { defineConfig } from "@playwright/test";

// Browser tests for real user interactions. They start the backend and the
// frontend (or reuse ones already running) and use the installed Chrome.
// Run: npm run test:e2e   (needs the migrated database; see the README)
// E2E_WEB_URL / E2E_API_URL point the tests at other running servers.
const WEB = process.env.E2E_WEB_URL ?? "http://localhost:3000";
const API = process.env.E2E_API_URL ?? "http://localhost:8000";

export default defineConfig({
  testDir: "./e2e",
  workers: 1,
  timeout: 60_000,
  expect: { timeout: 10_000 },
  use: {
    baseURL: WEB,
    channel: "chrome",
    headless: true,
  },
  webServer: [
    {
      command: ".venv/bin/uvicorn app.main:app --port 8000",
      cwd: "../backend",
      url: `${API}/api/health`,
      reuseExistingServer: true,
    },
    {
      command: "npm run dev",
      url: WEB,
      reuseExistingServer: true,
      timeout: 120_000,
    },
  ],
});
