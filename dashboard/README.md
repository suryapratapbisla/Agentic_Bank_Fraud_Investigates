# FraudIQ Dashboard

Vite + React UI for the 20 HHG investigation case outputs.

## Quick start

```powershell
cd dashboard
npm install
npm run dev
```

Open http://localhost:5173

## Sync case data after agent run

From repo root:

```powershell
Copy-Item cases\HHG-*.json dashboard\src\data\
```

Or use the export script with `--sync-cases`:

```powershell
venv\Scripts\python.exe Scripts\export_dashboard_bundles.py --sync-cases
```

## Graph view (hybrid TigerGraph)

The **Graph** tab loads investigation topology in this order:

1. **Live TigerGraph** — `get_evidence_bundle` via Vite proxy (`/api/tg` → `http://127.0.0.1:14240`). Requires Docker TigerGraph running.
2. **Cached bundle** — JSON under `src/data/bundles/HHG-*.json`
3. **Case JSON only** — fallback from static case files

Export bundles (with TigerGraph up):

```powershell
venv\Scripts\python.exe Scripts\export_dashboard_bundles.py --sync-cases
```

Disable live fetch (bundles/static only):

```powershell
# dashboard/.env.local
VITE_TG_LIVE=false
```

## Build

```powershell
npm run build
npm run preview
```
