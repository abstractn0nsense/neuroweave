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

Expected responsibilities:

- upload or select EEG datasets
- configure workflow steps
- inspect channel, event, and preprocessing state
- review results and exports
- provide a future chat panel for workflow assistance

Do not put server, storage, signal processing, or LLM provider logic here.
