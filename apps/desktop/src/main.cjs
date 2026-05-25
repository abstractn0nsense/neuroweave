const { app, BrowserWindow, shell } = require("electron");
const childProcess = require("node:child_process");
const fs = require("node:fs");
const http = require("node:http");
const path = require("node:path");

const DEFAULT_WEB_PORT = 5173;
const DEFAULT_API_PORT = 8000;
const BACKEND_TIMEOUT_MS = Number(process.env.NEUROWEAVE_BACKEND_TIMEOUT_MS || 90000);
const BACKEND_POLL_MS = 1000;
const ICON_PATH = path.join(__dirname, "..", "assets", "neuroweave-icon.svg");

let mainWindow = null;
let backendProcess = null;
let backendStartedByDesktop = false;
let backendExited = false;
let backendStartupError = null;
let quitAfterBackendStop = false;

function getRepoRoot() {
  return path.resolve(__dirname, "..", "..", "..");
}

function getApiPort() {
  return Number(process.env.NEUROWEAVE_API_PORT || DEFAULT_API_PORT);
}

function getWebUrl() {
  return (
    process.env.NEUROWEAVE_WEB_URL ||
    `http://127.0.0.1:${Number(process.env.NEUROWEAVE_WEB_PORT || DEFAULT_WEB_PORT)}`
  );
}

function getApiHealthUrl() {
  return process.env.NEUROWEAVE_API_HEALTH_URL || `http://127.0.0.1:${getApiPort()}/health`;
}

function getLogDirectory() {
  if (app.isPackaged) {
    return path.join(app.getPath("userData"), "logs");
  }
  return path.join(getRepoRoot(), "data", "logs");
}

function getBackendLogPath() {
  return path.join(getLogDirectory(), "desktop-api.log");
}

function getBackendMode() {
  if (process.env.NEUROWEAVE_DESKTOP_BACKEND_MODE) {
    return process.env.NEUROWEAVE_DESKTOP_BACKEND_MODE;
  }
  return app.isPackaged ? "packaged" : "development";
}

function getBackendLaunchConfig() {
  const mode = getBackendMode();
  const apiPort = getApiPort();

  if (process.env.NEUROWEAVE_API_COMMAND) {
    return {
      mode,
      command: process.env.NEUROWEAVE_API_COMMAND,
      args: (process.env.NEUROWEAVE_API_ARGS || "").split(" ").filter(Boolean),
      cwd: process.env.NEUROWEAVE_API_CWD || process.cwd()
    };
  }

  if (mode === "packaged") {
    throw new Error(
      "Packaged backend runtime is not bundled yet. Set NEUROWEAVE_API_COMMAND, NEUROWEAVE_API_ARGS, and NEUROWEAVE_API_CWD to launch an external backend."
    );
  }

  const repoRoot = getRepoRoot();
  const apiDir = path.join(repoRoot, "apps", "api");
  const pythonExecutable =
    process.env.NEUROWEAVE_API_PYTHON ||
    path.join(apiDir, ".venv", "Scripts", process.platform === "win32" ? "python.exe" : "python");

  if (!fs.existsSync(pythonExecutable)) {
    throw new Error(
      `API Python environment was not found at ${pythonExecutable}. Run scripts/setup_api.ps1 before launching the desktop shell.`
    );
  }

  return {
    mode,
    command: pythonExecutable,
    args: ["-m", "uvicorn", "main:app", "--host", "127.0.0.1", "--port", String(apiPort)],
    cwd: apiDir
  };
}

function isAppUrl(url) {
  try {
    return new URL(url).origin === new URL(getWebUrl()).origin;
  } catch {
    return false;
  }
}

function isShellFallbackUrl(url) {
  return url.startsWith("data:text/html;charset=utf-8,");
}

function toDataHtml(title, bodyLines) {
  const escapedTitle = escapeHtml(title);
  const body = bodyLines.map((line) => `<p>${escapeHtml(line)}</p>`).join("");
  const html = `<!doctype html>
<html>
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>${escapedTitle}</title>
    <style>
      body {
        margin: 0;
        min-height: 100vh;
        display: grid;
        place-items: center;
        background: #0f141a;
        color: #f5f7fb;
        font-family: Segoe UI, system-ui, sans-serif;
      }
      main {
        width: min(720px, calc(100vw - 48px));
        border: 1px solid #334155;
        padding: 28px;
        background: #151c24;
      }
      h1 {
        margin: 0 0 16px;
        font-size: 22px;
        line-height: 1.25;
      }
      p {
        margin: 10px 0 0;
        color: #cbd5e1;
        line-height: 1.5;
        overflow-wrap: anywhere;
      }
    </style>
  </head>
  <body>
    <main>
      <h1>${escapedTitle}</h1>
      ${body}
    </main>
  </body>
</html>`;

  return `data:text/html;charset=utf-8,${encodeURIComponent(html)}`;
}

function escapeHtml(value) {
  return String(value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1440,
    height: 960,
    minWidth: 1100,
    minHeight: 760,
    title: "NeuroWeave",
    icon: ICON_PATH,
    backgroundColor: "#0f141a",
    show: false,
    webPreferences: {
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true
    }
  });

  mainWindow.once("ready-to-show", () => {
    mainWindow.show();
  });

  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    if (isAppUrl(url)) {
      return { action: "allow" };
    }
    shell.openExternal(url);
    return { action: "deny" };
  });

  mainWindow.webContents.on("will-navigate", (event, url) => {
    if (isAppUrl(url) || isShellFallbackUrl(url)) {
      return;
    }
    event.preventDefault();
    shell.openExternal(url);
  });

  mainWindow.webContents.on("did-fail-load", (_event, errorCode, errorDescription) => {
    showStatusPage("NeuroWeave Web UI Unavailable", [
      `The web UI is not reachable at ${getWebUrl()}.`,
      "Start the existing Vite web dev server, then reopen the desktop shell.",
      `${errorCode}: ${errorDescription}`
    ]);
  });

  showStatusPage("Starting NeuroWeave", [
    `Starting local FastAPI backend at ${getApiHealthUrl()}.`,
    `Backend logs: ${getBackendLogPath()}`
  ]);
}

function showStatusPage(title, bodyLines) {
  if (mainWindow && !mainWindow.isDestroyed()) {
    mainWindow.loadURL(toDataHtml(title, bodyLines));
  }
}

function loadWebUi() {
  if (mainWindow && !mainWindow.isDestroyed()) {
    mainWindow.loadURL(getWebUrl());
  }
}

function requestHealth(url) {
  return new Promise((resolve, reject) => {
    const request = http.get(url, { timeout: 2000 }, (response) => {
      let body = "";
      response.setEncoding("utf8");
      response.on("data", (chunk) => {
        body += chunk;
      });
      response.on("end", () => {
        if (response.statusCode < 200 || response.statusCode >= 300) {
          reject(new Error(`Health check returned HTTP ${response.statusCode}.`));
          return;
        }
        try {
          const payload = JSON.parse(body);
          if (payload.status !== "ok" || payload.service !== "neuroweave-api") {
            reject(new Error("Health check payload did not match NeuroWeave API."));
            return;
          }
          resolve(payload);
        } catch (error) {
          reject(error);
        }
      });
    });

    request.on("timeout", () => {
      request.destroy(new Error("Health check timed out."));
    });
    request.on("error", reject);
  });
}

async function waitForBackendHealth() {
  const healthUrl = getApiHealthUrl();
  const deadline = Date.now() + BACKEND_TIMEOUT_MS;
  let lastError = null;

  while (Date.now() < deadline) {
    if (backendStartupError) {
      throw backendStartupError;
    }
    if (backendStartedByDesktop && backendExited) {
      throw new Error("Backend process exited before becoming healthy.");
    }

    try {
      return await requestHealth(healthUrl);
    } catch (error) {
      lastError = error;
      await new Promise((resolve) => setTimeout(resolve, BACKEND_POLL_MS));
    }
  }

  throw new Error(
    `Backend did not become healthy within ${BACKEND_TIMEOUT_MS} ms. Last error: ${lastError?.message || "unknown"}`
  );
}

async function startBackendIfNeeded() {
  if (process.env.NEUROWEAVE_DESKTOP_SKIP_BACKEND === "1") {
    return;
  }

  try {
    await requestHealth(getApiHealthUrl());
    fs.mkdirSync(getLogDirectory(), { recursive: true });
    fs.appendFileSync(getBackendLogPath(), `[${new Date().toISOString()}] Reusing healthy backend at ${getApiHealthUrl()}\n`);
    return;
  } catch {
    // No healthy backend is available, so the desktop shell owns the process it starts below.
  }

  const launchConfig = getBackendLaunchConfig();
  fs.mkdirSync(getLogDirectory(), { recursive: true });
  const logStream = fs.createWriteStream(getBackendLogPath(), { flags: "a" });

  logStream.write(
    `[${new Date().toISOString()}] Starting ${launchConfig.mode} backend: ${launchConfig.command} ${launchConfig.args.join(" ")}\n`
  );

  backendProcess = childProcess.spawn(launchConfig.command, launchConfig.args, {
    cwd: launchConfig.cwd,
    env: {
      ...process.env,
      NEUROWEAVE_CORS_ALLOW_LOCALHOST_PORTS: process.env.NEUROWEAVE_CORS_ALLOW_LOCALHOST_PORTS || "true"
    },
    windowsHide: true,
    stdio: ["ignore", "pipe", "pipe"]
  });
  backendStartedByDesktop = true;

  backendProcess.stdout.pipe(logStream, { end: false });
  backendProcess.stderr.pipe(logStream, { end: false });
  backendProcess.on("exit", (code, signal) => {
    backendExited = true;
    logStream.write(`[${new Date().toISOString()}] Backend exited with code=${code} signal=${signal}\n`);
    logStream.end();
  });
  backendProcess.on("error", (error) => {
    backendStartupError = error;
    logStream.write(`[${new Date().toISOString()}] Backend process error: ${error.message}\n`);
  });

  await waitForBackendHealth();
}

function stopBackend() {
  return new Promise((resolve) => {
    if (!backendStartedByDesktop || !backendProcess || backendExited) {
      resolve();
      return;
    }

    const processToStop = backendProcess;
    let resolved = false;
    const finish = () => {
      if (resolved) {
        return;
      }
      resolved = true;
      clearTimeout(termTimeout);
      clearTimeout(killTimeout);
      resolve();
    };
    const killTimeout = setTimeout(() => {
      finish();
    }, 8000);
    const termTimeout = setTimeout(() => {
      if (!backendExited) {
        processToStop.kill("SIGKILL");
      }
    }, 5000);

    processToStop.once("exit", () => {
      finish();
    });
    processToStop.kill("SIGTERM");
  });
}

async function bootDesktop() {
  createWindow();

  try {
    await startBackendIfNeeded();
    await waitForBackendHealth();
    if (process.env.NEUROWEAVE_DESKTOP_QUIT_AFTER_BACKEND_HEALTH === "1") {
      showStatusPage("NeuroWeave Backend Healthy", [`Health URL: ${getApiHealthUrl()}`]);
      setTimeout(() => app.quit(), 100);
      return;
    }
    loadWebUi();
  } catch (error) {
    showStatusPage("NeuroWeave Backend Failed To Start", [
      error.message,
      `Health URL: ${getApiHealthUrl()}`,
      `Backend logs: ${getBackendLogPath()}`
    ]);
  }
}

const hasSingleInstanceLock = app.requestSingleInstanceLock();

if (!hasSingleInstanceLock) {
  app.quit();
} else {
  app.on("second-instance", () => {
    if (!mainWindow) {
      return;
    }
    if (mainWindow.isMinimized()) {
      mainWindow.restore();
    }
    mainWindow.focus();
  });

  app.whenReady().then(() => {
    app.setName("NeuroWeave");
    bootDesktop();

    app.on("activate", () => {
      if (BrowserWindow.getAllWindows().length === 0) {
        bootDesktop();
      }
    });
  });

  app.on("before-quit", (event) => {
    if (quitAfterBackendStop) {
      return;
    }
    if (!backendStartedByDesktop || !backendProcess || backendExited) {
      return;
    }

    event.preventDefault();
    quitAfterBackendStop = true;
    stopBackend().finally(() => app.quit());
  });

  app.on("window-all-closed", () => {
    if (process.platform !== "darwin") {
      app.quit();
    }
  });
}
