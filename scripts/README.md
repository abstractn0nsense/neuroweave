# Scripts

Repository scripts live here.

Use this folder for repeatable local setup, fixture generation, and small maintenance commands. Scripts should be safe to re-run and should not require checking generated `data/` contents into git.

## API Setup

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\setup_api.ps1
```

The script selects a supported CPython 3.12 or 3.13 interpreter and creates `apps/api/.venv`.
