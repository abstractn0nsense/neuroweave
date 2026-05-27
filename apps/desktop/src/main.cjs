const { app, BrowserWindow, shell } = require("electron");
const childProcess = require("node:child_process");
const fs = require("node:fs");
const http = require("node:http");
const path = require("node:path");
const { pathToFileURL } = require("node:url");

const DEFAULT_WEB_PORT = 5173;
const DEFAULT_API_PORT = 8000;
const BACKEND_TIMEOUT_MS = Number(process.env.NEUROWEAVE_BACKEND_TIMEOUT_MS || 90000);
const BACKEND_POLL_MS = 1000;
const ICON_PATH = path.join(__dirname, "..", "assets", "neuroweave-icon.svg");

let mainWindow = null;
let backendProcess = null;
let backendCommand = null;
let backendStartedByDesktop = false;
let backendExited = false;
let backendStartupError = null;
let quitAfterBackendStop = false;

function getRepoRoot() {
  return path.resolve(__dirname, "..", "..", "..");
}

function isPackagedMode() {
  return app.isPackaged || process.env.NEUROWEAVE_DESKTOP_FORCE_PACKAGED_MODE === "1";
}

function getResourceRoot() {
  if (process.env.NEUROWEAVE_DESKTOP_RESOURCES_DIR) {
    return process.env.NEUROWEAVE_DESKTOP_RESOURCES_DIR;
  }
  if (app.isPackaged) {
    return process.resourcesPath;
  }
  return path.join(getRepoRoot(), "dist", "desktop");
}

function getApiPort() {
  return Number(process.env.NEUROWEAVE_API_PORT || DEFAULT_API_PORT);
}

function getWebUrl() {
  if (process.env.NEUROWEAVE_WEB_URL) {
    return process.env.NEUROWEAVE_WEB_URL;
  }
  if (isPackagedMode()) {
    return pathToFileURL(path.join(getResourceRoot(), "web", "index.html")).toString();
  }
  return (
    `http://127.0.0.1:${Number(process.env.NEUROWEAVE_WEB_PORT || DEFAULT_WEB_PORT)}`
  );
}

function getApiHealthUrl() {
  return process.env.NEUROWEAVE_API_HEALTH_URL || `http://127.0.0.1:${getApiPort()}/health`;
}

function getLogDirectory() {
  if (isPackagedMode()) {
    return path.join(app.getPath("userData"), "logs");
  }
  return path.join(getRepoRoot(), "data", "logs");
}

function getDataDirectory() {
  if (process.env.NEUROWEAVE_DESKTOP_DATA_DIR) {
    return process.env.NEUROWEAVE_DESKTOP_DATA_DIR;
  }
  if (isPackagedMode()) {
    return path.join(app.getPath("userData"), "data");
  }
  return path.join(getRepoRoot(), "data");
}

function getBackendLogPath() {
  return path.join(getLogDirectory(), "desktop-api.log");
}

function getBackendMode() {
  if (process.env.NEUROWEAVE_DESKTOP_BACKEND_MODE) {
    return process.env.NEUROWEAVE_DESKTOP_BACKEND_MODE;
  }
  return isPackagedMode() ? "packaged" : "development";
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
    const executableName = process.platform === "win32" ? "neuroweave-api.exe" : "neuroweave-api";
    const backendExecutable = path.join(getResourceRoot(), "backend", executableName);
    if (!fs.existsSync(backendExecutable)) {
      throw new Error(
        `Packaged backend executable was not found at ${backendExecutable}. Run the backend packaging script before packaging the desktop app.`
      );
    }
    return {
      mode,
      command: backendExecutable,
      args: [],
      cwd: path.dirname(backendExecutable)
    };
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
    const candidate = new URL(url);
    const appUrl = new URL(getWebUrl());
    if (appUrl.protocol === "file:") {
      return candidate.protocol === "file:" && candidate.pathname.startsWith(path.dirname(appUrl.pathname));
    }
    return candidate.origin === appUrl.origin;
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
      isPackagedMode()
        ? "The packaged React build is missing or unreadable."
        : "Start the existing Vite web dev server, then reopen the desktop shell.",
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

  const backendEnv = {
    ...process.env,
    NEUROWEAVE_API_PORT: String(getApiPort()),
    NEUROWEAVE_SAMPLE_DATASET_DIR: process.env.NEUROWEAVE_SAMPLE_DATASET_DIR || path.join(getDataDirectory(), "raw", "samples"),
    NEUROWEAVE_UPLOADS_DIR: process.env.NEUROWEAVE_UPLOADS_DIR || path.join(getDataDirectory(), "raw", "uploads"),
    NEUROWEAVE_RUNS_DIR: process.env.NEUROWEAVE_RUNS_DIR || path.join(getDataDirectory(), "runs"),
    NEUROWEAVE_TEMPLATES_DIR: process.env.NEUROWEAVE_TEMPLATES_DIR || path.join(getDataDirectory(), "templates"),
    NEUROWEAVE_PROCESSED_DIR: process.env.NEUROWEAVE_PROCESSED_DIR || path.join(getDataDirectory(), "processed"),
    NEUROWEAVE_EPOCHS_DIR: process.env.NEUROWEAVE_EPOCHS_DIR || path.join(getDataDirectory(), "epochs"),
    NEUROWEAVE_ERP_DIR: process.env.NEUROWEAVE_ERP_DIR || path.join(getDataDirectory(), "erp"),
    NEUROWEAVE_CORS_ALLOW_LOCALHOST_PORTS: process.env.NEUROWEAVE_CORS_ALLOW_LOCALHOST_PORTS || "true"
  };
  if (isPackagedMode()) {
    backendEnv.NEUROWEAVE_WORKER_COMMAND = launchConfig.command;
    backendEnv.NEUROWEAVE_CORS_ORIGINS = process.env.NEUROWEAVE_CORS_ORIGINS || "null";
  }

  backendProcess = childProcess.spawn(launchConfig.command, launchConfig.args, {
    cwd: launchConfig.cwd,
    env: backendEnv,
    windowsHide: true,
    stdio: ["ignore", "pipe", "pipe"]
  });
  backendCommand = launchConfig.command;
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
    if (!backendStartedByDesktop) {
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
      if (processToStop) {
        forceStopProcessTree(processToStop.pid);
      }
      stopOwnedApiPortListener();
    }, 5000);

    if (process.platform === "win32") {
      const taskkill = processToStop && !backendExited ? stopProcessTree(processToStop.pid) : null;
      const stopListener = () => {
        const listenerStop = stopOwnedApiPortListener();
        listenerStop?.once("close", () => {
          setTimeout(finish, 500);
        });
        listenerStop?.once("error", () => {
          finish();
        });
      };
      if (taskkill) {
        taskkill.once("close", stopListener);
        taskkill.once("error", () => {
          forceStopProcessTree(processToStop.pid);
          stopListener();
        });
      } else {
        stopListener();
      }
    } else {
      processToStop?.once("exit", () => {
        finish();
      });
      if (processToStop && !backendExited) {
        stopProcessTree(processToStop.pid);
      } else {
        finish();
      }
    }
  });
}

function stopProcessTree(processId) {
  if (process.platform === "win32") {
    return childProcess.spawn("taskkill.exe", ["/PID", String(processId), "/T"], {
      windowsHide: true,
      stdio: "ignore"
    });
  }
  backendProcess.kill("SIGTERM");
  return null;
}

function forceStopProcessTree(processId) {
  if (process.platform === "win32") {
    childProcess.spawn("taskkill.exe", ["/PID", String(processId), "/T", "/F"], {
      windowsHide: true,
      stdio: "ignore"
    });
    return;
  }
  backendProcess.kill("SIGKILL");
}

function stopOwnedApiPortListener() {
  if (process.platform !== "win32" || !backendCommand) {
    return null;
  }

  const normalizedBackendCommand = backendCommand.toLowerCase().replace(/'/g, "''");
  const command = [
    "$ErrorActionPreference = 'SilentlyContinue';",
    `$backend = '${normalizedBackendCommand}';`,
    `$port = ${getApiPort()};`,
    "$connections = Get-NetTCPConnection -LocalPort $port -State Listen;",
    "foreach ($connection in $connections) {",
    "  $processInfo = Get-CimInstance Win32_Process -Filter \"ProcessId = $($connection.OwningProcess)\";",
    "  $commandLine = if ($processInfo.CommandLine) { $processInfo.CommandLine.ToLowerInvariant() } else { '' };",
    "  if ($commandLine.Contains($backend)) { Stop-Process -Id $connection.OwningProcess -Force; }",
    "}"
  ].join(" ");

  return childProcess.spawn(
    "powershell.exe",
    ["-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", command],
    {
      windowsHide: true,
      stdio: "ignore"
    }
  );
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
    if (!backendStartedByDesktop) {
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
