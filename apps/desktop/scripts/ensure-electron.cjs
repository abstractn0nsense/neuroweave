const childProcess = require("node:child_process");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");

const electronRoot = path.join(__dirname, "..", "node_modules", "electron");
const electronPackagePath = path.join(electronRoot, "package.json");
const distPath = path.join(electronRoot, "dist");
const pathFile = path.join(electronRoot, "path.txt");
const platformPath = os.platform() === "win32" ? "electron.exe" : os.platform() === "darwin" ? "Electron.app/Contents/MacOS/Electron" : "electron";
const executablePath = path.join(distPath, platformPath);

function isElectronReady() {
  return fs.existsSync(pathFile) && fs.existsSync(executablePath);
}

async function ensureWindowsElectron() {
  if (isElectronReady()) {
    return;
  }

  if (os.platform() !== "win32") {
    throw new Error("Electron binary is not ready after install. Delete node_modules and run npm install again.");
  }

  const { version } = require(electronPackagePath);
  const { downloadArtifact } = require("@electron/get");
  const zipPath = await downloadArtifact({
    version,
    artifactName: "electron",
    platform: process.platform,
    arch: process.arch,
    force: process.env.force_no_cache === "true"
  });

  fs.rmSync(distPath, { recursive: true, force: true });
  fs.mkdirSync(distPath, { recursive: true });

  const quotePowerShellLiteral = (value) => `'${value.replace(/'/g, "''")}'`;
  const command = [
    "$ErrorActionPreference = 'Stop';",
    `Expand-Archive -LiteralPath ${quotePowerShellLiteral(zipPath)} -DestinationPath ${quotePowerShellLiteral(distPath)} -Force;`
  ].join(" ");

  childProcess.execFileSync(
    "powershell.exe",
    ["-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", command],
    { stdio: "inherit" }
  );

  fs.writeFileSync(pathFile, platformPath);
}

ensureWindowsElectron().catch((error) => {
  console.error(error.stack || error);
  process.exit(1);
});
