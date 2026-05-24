import { defineConfig } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const webDir = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = path.resolve(webDir, "../..");
const apiDir = path.join(repoRoot, "apps", "api");
const e2eDataDir = path.join(repoRoot, "data", "cache", "phase2-e2e");
const apiPort = 8010;
const webPort = 5174;
const apiBaseUrl = `http://127.0.0.1:${apiPort}`;
const webBaseUrl = `http://127.0.0.1:${webPort}`;

fs.rmSync(e2eDataDir, { force: true, recursive: true });

const localPython =
  process.platform === "win32"
    ? path.join(apiDir, ".venv", "Scripts", "python.exe")
    : path.join(apiDir, ".venv", "bin", "python");
const pythonCommand = process.env.NEUROWEAVE_E2E_PYTHON
  ?? (fs.existsSync(localPython) ? localPython : "python");

function quoteCommand(value: string): string {
  return value.includes(" ") ? `"${value}"` : value;
}

export default defineConfig({
  testDir: "./e2e",
  timeout: 90_000,
  expect: {
    timeout: 15_000,
  },
  use: {
    baseURL: webBaseUrl,
    trace: "retain-on-failure",
  },
  webServer: [
    {
      command: `${quoteCommand(pythonCommand)} -m uvicorn main:app --host 127.0.0.1 --port ${apiPort}`,
      cwd: apiDir,
      env: {
        ...process.env,
        NEUROWEAVE_UPLOADS_DIR: path.join(e2eDataDir, "uploads"),
        NEUROWEAVE_RUNS_DIR: path.join(e2eDataDir, "runs"),
        NEUROWEAVE_PROCESSED_DIR: path.join(e2eDataDir, "processed"),
        NEUROWEAVE_SAMPLE_DATASET_DIR: path.join(repoRoot, "data", "raw", "samples"),
      },
      reuseExistingServer: !process.env.CI,
      timeout: 120_000,
      url: `${apiBaseUrl}/health`,
    },
    {
      command: `npm run dev -- --host 127.0.0.1 --port ${webPort}`,
      cwd: webDir,
      env: {
        ...process.env,
        VITE_API_BASE_URL: apiBaseUrl,
      },
      reuseExistingServer: !process.env.CI,
      timeout: 120_000,
      url: webBaseUrl,
    },
  ],
});
