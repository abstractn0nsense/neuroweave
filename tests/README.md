# Tests

Repository-level test support lives here.

Use `tests/fixtures/eeg` for shared EEG fixtures. Package-local tests can be added near the source code when the implementation stack is chosen.

EEG fixtures committed here should stay small and deterministic. Runtime uploads, generated outputs, and caches belong under the ignored `data/` directory instead.

Phase 0 fixtures are generated with:

```powershell
.\apps\api\.venv\Scripts\python.exe .\scripts\generate_sample_eeg.py --fixtures-only
```
