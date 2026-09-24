# Agentic Fraud Investigation

GraphRAG fraud investigator for the TigerGraph Hacker House (IEEE-CIS) exam: **20 cases** (`HHG-001` … `HHG-020`), TigerGraph evidence, hybrid case memory, policy-validated LLM outputs, and the **FraudIQ** dashboard.

## What's in this repo

| Path | Purpose |
|------|---------|
| `DATA/` | Task spec (`readme.md`), case pack, closed-case history, **filtered** CSVs for loading |
| `graph/` | GSQL schema, loaders, queries, deployment scripts |
| `agent/` | Python investigator (`agent.py`), memory pipeline, tests |
| `cases/` | Agent answer JSON (exam deliverables) |
| `dashboard/` | Vite + React **FraudIQ** UI |
| `Scripts/` | Data filter, memory bootstrap, dashboard export |

The runtime agent uses **pyTigerGraph** (`get_evidence_bundle`), not an in-repo MCP server. Optional TigerGraph MCP: [github.com/tigergraph/tigergraph-mcp](https://github.com/tigergraph/tigergraph-mcp).

## Quick start

```powershell
python -m venv venv
venv\Scripts\pip install -r agent\requirements.txt
copy agent\.env.example agent\.env
# Start TigerGraph Docker on :14240, then deploy graph (see graph/README.md)

venv\Scripts\python.exe agent\agent.py --case-id HHG-001

venv\Scripts\python.exe Scripts\export_dashboard_bundles.py --sync-cases
cd dashboard
npm install
npm run dev
```

See `agent/README.md`, `graph/README.md`, and `dashboard/README.md` for details.

## Before you push

- Do **not** commit `agent/.env` or API keys.
- Full `DATA/transactions.csv` / `DATA/identity.csv` are gitignored (large); keep filtered data under `DATA/filtered_data/`.
- Optional cleanup (drops vendored MCP, untracks secrets and build output):

```powershell
venv\Scripts\python.exe Scripts\prepare_git_push.py
git add -A
git status
```
