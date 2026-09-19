import { defineConfig } from "@playwright/test";
import path from "node:path";
import process from "node:process";
import { fileURLToPath } from "node:url";

const directory = path.dirname(fileURLToPath(import.meta.url));
const backend = path.resolve(directory, "../backend");
const python =
  process.env.CLARITYOPS_PYTHON ||
  path.join(
    backend,
    process.platform === "win32"
      ? ".venv/Scripts/python.exe"
      : ".venv/bin/python",
  );
export default defineConfig({
  testDir: "./e2e",
  workers: 1,
  fullyParallel: false,
  timeout: 60000,
  expect: { timeout: 15000 },
  use: {
    baseURL: "http://127.0.0.1:15173",
    trace: "retain-on-failure",
    launchOptions: { executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE || undefined },
  },
  webServer: [
    {
      command: `"${python}" tests/e2e_server.py`,
      cwd: backend,
      url: "http://127.0.0.1:18000/health",
      timeout: 60000,
      env: { CLARITYOPS_E2E: "1" },
      reuseExistingServer: false,
    },
    {
      command: "npm run dev -- --port 15173",
      url: "http://127.0.0.1:15173",
      env: { CLARITYOPS_API_TARGET: "http://127.0.0.1:18000" },
      reuseExistingServer: false,
    },
  ],
});
