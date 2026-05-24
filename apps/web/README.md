# Web App

Browser-facing EEG workflow application.

## Local Development

```powershell
cd apps/web
npm install
npm run dev
```

The development server runs on `http://127.0.0.1:5173`.

Copy `.env.example` to `.env` when local API URL overrides are needed.

Phase 0 UI checks:

- API health status
- sample EEG dataset list
- selected sample metadata
- loading, empty, and API error states

Phase 1 ingestion checks:

- project and experiment creation or selection
- participant/session dataset creation
- EEG recording upload
- event CSV/TSV upload and preview
- event column mapping
- dataset validation status, errors, and warnings
- preprocessing handoff remains disabled until validation succeeds

Phase 2 browser smoke:

```powershell
cd apps/web
npm run e2e:phase2
```

The smoke starts the API and web dev servers, uploads fixture EEG/events through the UI, validates the dataset, starts preprocessing, and waits for a completed run.

Phase 3 browser smokes are split so epoching and ERP preview failures can be
triaged independently:

```powershell
cd apps/web
npm run e2e:phase3:epoch
npm run e2e:phase3:erp
```

`e2e:phase3:epoch` extends the preprocessing path through a completed epoch run.
`e2e:phase3:erp` extends that path through ERP preview and comparison prep. Use
`NEUROWEAVE_E2E_DATA_DIR` to override the isolated browser test data directory.

Phase 3 epoch controls use completed preprocessing runs as inputs. The workbench
lets users choose the condition field, epoch window, baseline, and optional EEG
rejection threshold, then polls epoch status and displays compact
condition/epoch/drop counts.

Phase 3 ERP preview uses completed epoch runs as inputs. The workbench can start
ERP generation, poll ERP status, and display the first generated PNG plot through
the API artifact endpoint. GFP is the default plot mode, with an optional channel
plot mode when a channel name is provided.

Phase 3 comparison prep uses completed ERP runs with at least two conditions. The
workbench can choose a condition pair, GFP or channel target, and mean-amplitude
window, then displays descriptive means and A-B difference while keeping
statistics deferred to Phase 4.

Expected responsibilities:

- upload or select EEG datasets
- configure workflow steps
- inspect channel, event, and preprocessing state
- review results and exports
- provide a future chat panel for workflow assistance

Do not put server, storage, signal processing, or LLM provider logic here.
