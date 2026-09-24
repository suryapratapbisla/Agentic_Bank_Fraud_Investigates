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

## Graph view (works without TigerGraph)

Hosted builds **do not** call TigerGraph. The graph is built from data shipped in the repo:

1. **Cached bundle** — `src/data/bundles/HHG-*.json` (full topology from `get_evidence_bundle`)
2. **Case JSON** — `src/data/HHG-*.json` if a bundle is missing (customer, card, txns, devices, connected cards, prior cases)

Optional live mode (local dev only): set `VITE_TG_LIVE=true` and run TigerGraph on `:14240` with the Vite proxy.

Regenerate bundles when you have TigerGraph up:

```powershell
venv\Scripts\python.exe Scripts\export_dashboard_bundles.py --sync-cases
```

## Static hosting (Netlify, Vercel, GitHub Pages)

```powershell
cd dashboard
npm install
npm run build
```

Deploy the `dashboard/dist` folder. `dashboard/.env.production` sets `VITE_TG_LIVE=false` so the graph never waits on a database.

## Build

```powershell
npm run build
npm run preview
```
