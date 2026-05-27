# NeuroWeave Local Research Preview Release Checklist

Use this checklist before publishing a Local Research Preview build. The goal is
to confirm that a researcher can install NeuroWeave, launch it without developer
tools, run the public demo path, generate review artifacts, and uninstall the app.

## Release Scope

Release name:

```text
NeuroWeave Local Research Preview
```

Expected release artifacts:

- Windows installer: `apps/desktop/dist-installer/NeuroWeave-Setup-0.1.0.exe`
- Installer block map: `apps/desktop/dist-installer/NeuroWeave-Setup-0.1.0.exe.blockmap`
- Draft release notes with known limitations and smoke results
- Optional checksum file for the installer

Supported preview platform:

- Windows 10 or Windows 11, x64
- Local-only execution
- Single-user install

## Preflight

- Confirm the release branch is clean before building.
- Confirm `apps/api/.venv` exists and was created with supported CPython 3.12 or
  3.13.
- Confirm Node.js and npm are available.
- Confirm local generated data under `data/` is not staged for git.
- Confirm no unrelated process is listening on the API test ports used below.

## Smoke Command List

Run from the repository root unless a command changes directory.

For Phase C template and batch work, also keep the focused release gate in
`docs/phase-c-release-gate.md` current. It records the mainline smoke result,
Phase B artifact contract, and template/batch compatibility checklist.

```powershell
git status --short --branch
```

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\setup_api.ps1
```

```powershell
.\apps\api\.venv\Scripts\python.exe -m pytest tests -o cache_dir=data/cache/pytest-cache --basetemp data/cache/pytest-tmp
```

```powershell
cd apps/web
npm install
npm run build
npm run e2e:all
cd ..\..
```

```powershell
cd apps/desktop
npm install
npm run check
npm audit --omit=optional
npm run package:dir
npm run package:win
cd ..\..
```

Expected results:

- Python tests pass.
- Web build passes.
- Phase 2/3 E2E passes.
- Desktop syntax check passes.
- Desktop audit reports no vulnerabilities.
- Unpacked app is created under `apps/desktop/dist-app-unpacked/`.
- Installer is created under `apps/desktop/dist-installer/`.

## Installation QA

Use a fresh test install path when possible.

```powershell
$installer = ".\apps\desktop\dist-installer\NeuroWeave-Setup-0.1.0.exe"
$installDir = "$env:LOCALAPPDATA\Programs\NeuroWeavePreview"
& $installer /S "/D=$installDir"
```

Confirm:

- `NeuroWeave.exe` exists in the install directory.
- `resources/web/index.html` exists.
- `resources/backend/neuroweave-api.exe` exists.
- Desktop shortcut named `NeuroWeave` exists.
- Start Menu shortcut named `NeuroWeave` exists.
- Windows uninstall entry is registered as `NeuroWeave`.

## First Launch QA

Run the installed app from the shortcut or executable.

Confirm:

- App window opens without a terminal window.
- Backend starts automatically.
- App shows API health as online.
- No browser-based Vite dev server is required.
- Closing the app stops the backend listener.
- Logs are written under Electron `userData/logs`.
- Local research data is written under Electron `userData/data`, not under the
  installation directory.

Backend listener check example:

```powershell
Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue
```

If a custom test port is used, set `NEUROWEAVE_API_PORT` before launch and check
that port instead.

## Public Demo Workflow QA

Prepare the PhysioNet EEGMMI demo files:

```powershell
.\apps\api\.venv\Scripts\python.exe .\scripts\prepare_physionet_eegmmi_demo.py
```

Manual app flow:

- Open NeuroWeave.
- In `Setup`, create a project.
- Create an experiment.
- Create a dataset.
- Select the dataset in `Dataset Queue`.
- Confirm selection stays in `Setup`.
- Click `Continue Analysis`.
- Upload `data/raw/public-samples/S001R03.edf` as EEG recording.
- Upload `data/raw/public-samples/S001R03_events.csv` as event log.
- Save event mapping:
  - `onset_seconds` -> `onset`
  - `duration_seconds` -> `duration`
  - `trial_type` -> `trial_type`
  - `stimulus` -> `stimulus`
- Validate the dataset.
- Run preprocessing.
- Create epochs using `trial_type`.
- Generate ERP preview.

Pass criteria:

- Upload UI shows supported formats and selected file status.
- Validation errors and warnings are readable.
- Preprocessing completes.
- Epoch run completes.
- ERP run completes.
- ERP preview plot is visible.

## Report And Export QA

From a completed ERP run:

- Click `Generate Report` or equivalent report action.
- Confirm `analysis_report.json` is created.
- Confirm report is included in the artifact manifest.
- Click export bundle.
- Confirm ZIP download completes.
- Inspect ZIP contents.

Expected ZIP entries:

```text
analysis_report.json
artifact_manifest.json
export_bundle_manifest.json
configs/
diagnostics/
figures/
provenance/
artifacts/
```

Pass criteria:

- Report contains dataset metadata, event summary, preprocessing config, epoch
  config, ERP config, warnings, artifact manifest, preview plot links, and
  comparison summary when available.
- Export bundle contains report, manifest, plots, config snapshots, provenance,
  diagnostics, and artifacts.
- Missing artifacts are represented as structured warnings, not silent failures.

## Artifact Integrity QA

From a completed run:

- Open the artifact integrity UI.
- Confirm every artifact is listed with status.
- Confirm `ok`, `missing`, and `checksum_mismatch` states are visually distinct
  when present.
- Confirm integrity check does not expose or traverse arbitrary filesystem paths.

API spot check:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/erp-runs/{run_id}/artifact-integrity
```

Pass criteria:

- All expected demo artifacts report `ok`.
- Any missing artifact is shown as `missing`.
- Any checksum mismatch is shown as `checksum_mismatch`.

## Uninstall QA

Uninstall from Windows Settings or run:

```powershell
& "$installDir\Uninstall NeuroWeave.exe" /S
```

Confirm:

- Installation directory is removed.
- Desktop shortcut is removed.
- Start Menu shortcut is removed.
- Windows uninstall entry is removed.
- User research data under Electron `userData/data` is preserved unless a future
  release explicitly adds a data deletion option.

## Known Limitations

- Preview release is Windows-only.
- Installer is not code-signed.
- Auto-update is not implemented.
- Packaged app uses an unpacked app directory during verification; installer
  generation works, but final production hardening should revisit `asar` and
  signing.
- Backend is local-only and not authenticated.
- Public demo download depends on PhysioNet/network availability and remains
  opt-in.
- Current statistical comparison output is descriptive; inferential statistics
  are not implemented.
- Advanced EEG workflows such as ICA, bad-channel interpolation, visual artifact
  review, and group-level analysis are not release blockers for this preview.
- Large EEG files may be slow because execution is local and single-machine.
- Data migration between preview versions is not guaranteed yet.

## Troubleshooting

App opens but backend is offline:

- Check `userData/logs/desktop-api.log`.
- Confirm no unrelated process owns the API port.
- Try setting `NEUROWEAVE_API_PORT` to an unused port.

Installer fails:

- Re-run `npm run package:win`.
- Confirm `dist/desktop/icon/neuroweave.ico` exists.
- Confirm `dist/desktop/backend/neuroweave-api.exe` exists.
- Confirm antivirus did not quarantine the PyInstaller backend executable.

Public demo upload fails:

- Confirm the EDF and CSV exist under `data/raw/public-samples/`.
- Regenerate the CSV with `--events-only` if the EDF already exists.
- Confirm the event mapping uses the expected column names.

Export bundle is incomplete:

- Run artifact integrity check.
- Regenerate the affected run if artifacts are missing.
- Re-run report generation before export.

Uninstall leaves data behind:

- This is expected for the preview. User research data is preserved by default.
- Manually remove Electron `userData/data` only after confirming no needed
  research output remains.

## Release Sign-Off

Record final results before publishing:

| Area | Result | Notes |
| --- | --- | --- |
| Python tests |  |  |
| Web build |  |  |
| Phase 2/3 E2E |  |  |
| Desktop check |  |  |
| Desktop audit |  |  |
| Unpacked app build |  |  |
| Installer build |  |  |
| Install QA |  |  |
| First launch QA |  |  |
| Public demo workflow |  |  |
| Report/export QA |  |  |
| Artifact integrity QA |  |  |
| Uninstall QA |  |  |

## B0 Verification Snapshot

Recorded on 2026-05-27 after the Phase A release gate cleanup.

| Area | Result | Notes |
| --- | --- | --- |
| Desktop audit | Pass | `npm.cmd audit --omit=optional` reports 0 vulnerabilities after lockfile update to `tmp@0.2.6`. |
| Desktop check | Pass | `npm.cmd run check` completed successfully. |
| Web build | Pass | Re-run through desktop packaging; `tsc --noEmit && vite build` completed successfully. |
| Backend executable build | Pass | `npm.cmd run package:dir` and `npm.cmd run package:win` rebuilt `dist/desktop/backend/neuroweave-api.exe`. |
| Unpacked app build | Pass | `apps/desktop/dist-app-unpacked/win-unpacked/` regenerated successfully. |
| Installer build | Pass | `apps/desktop/dist-installer/NeuroWeave-Setup-0.1.0.exe` and `.blockmap` regenerated successfully. |
| Install QA | Pass | Silent install to `%LOCALAPPDATA%\Programs\NeuroWeaveB0Smoke`; app exe, web bundle, backend exe, uninstaller, Desktop shortcut, and Start Menu shortcut verified. |
| First launch QA | Pass | Installed app launched packaged backend on `NEUROWEAVE_API_PORT=8130`, `/health` returned `ok`, and the backend listener stopped after app quit. |
| Logs/data location QA | Pass | Packaged backend log observed under Electron `userData` at `%APPDATA%\@neuroweave\desktop\logs\desktop-api.log`; preserved user data remains outside the install directory. |
| Uninstall QA | Pass | Silent uninstall removed install directory, Desktop shortcut, and Start Menu shortcut. |
| Python tests | Not rerun in B0 | Last checked before B0: 192 tests passed. Re-run before external publication. |
| Phase 2/3 E2E | Not rerun in B0 | Last checked before B0: Phase 2 preprocessing, Phase 3 epoch, and Phase 3 ERP smoke tests passed. Re-run before external publication. |
| Public demo workflow | Not rerun in B0 | Manual PhysioNet public demo remains a release sign-off gate. |
| Report/export QA | Not rerun in B0 | Manual completed-run report/export inspection remains a release sign-off gate. |
| Artifact integrity QA | Not rerun in B0 | Manual completed-run integrity inspection remains a release sign-off gate. |
