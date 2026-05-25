const { app, BrowserWindow, shell } = require("electron");
const path = require("node:path");

const DEFAULT_WEB_URL = "http://127.0.0.1:5173";
const WEB_URL = process.env.NEUROWEAVE_WEB_URL || DEFAULT_WEB_URL;
const ICON_PATH = path.join(__dirname, "..", "assets", "neuroweave-icon.svg");

let mainWindow = null;

function isAppUrl(url) {
  try {
    return new URL(url).origin === new URL(WEB_URL).origin;
  } catch {
    return false;
  }
}

function isShellFallbackUrl(url) {
  return url.startsWith("data:text/plain;charset=utf-8,");
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
    const message = encodeURIComponent(
      `NeuroWeave web UI is not reachable at ${WEB_URL}.\n\nStart the local API and web dev server first, then reopen the desktop shell.\n\n${errorCode}: ${errorDescription}`
    );
    mainWindow.loadURL(`data:text/plain;charset=utf-8,${message}`);
  });

  mainWindow.loadURL(WEB_URL);
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
    createWindow();

    app.on("activate", () => {
      if (BrowserWindow.getAllWindows().length === 0) {
        createWindow();
      }
    });
  });

  app.on("window-all-closed", () => {
    if (process.platform !== "darwin") {
      app.quit();
    }
  });
}
