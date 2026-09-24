# Fraud Investigation Agent

This folder contains the Python GraphRAG agent that:
- gathers evidence from TigerGraph using installed query `get_evidence_bundle`
- prompts an LLM with policy + evidence
- validates/corrects output structure and policy consistency
- writes case JSON files (and optionally writes case memory back to graph)

## Setup

From repo root:

```bash
python -m venv venv
venv\Scripts\pip install -r agent\requirements.txt
```

Create `agent/.env` from `agent/.env.example`.

### LLM: Groq (default) or OpenAI

Set in `agent/.env`:

```env
LLM_PROVIDER=groq
GROQ_API_KEY=gsk-...
GROQ_MODEL=openai/gpt-oss-120b
```

Groq uses the OpenAI-compatible API (`json_object` mode). Semantic memory embeddings still use OpenAI if `OPENAI_API_KEY` is set; graph-only memory works without it.

For OpenAI instead:

```env
LLM_PROVIDER=openai
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4o
```

## Case memory (hybrid retrieval)

Before first run with semantic memory, deploy graph schema updates and bootstrap historical case memory:

```bash
graph\deployment\deploy.ps1
venv\Scripts\python.exe Scripts\bootstrap_case_memory.py --limit 100
```

The agent retrieves case memory **before** the LLM call (graph similarity + TigerGraph vector search). The LLM never queries the vector index directly. Retrieved cases appear under **Relevant Previous Investigations** in the prompt.

Write-back after investigation closes upserts both `ClosedCase` (graph) and `CaseMemory` (text + embedding).


```bash
venv\Scripts\python.exe agent\agent.py --case-id HHG-001
```

All cases:

```bash
venv\Scripts\python.exe agent\agent.py --all-cases
```

Useful options:
- `--model <name>` (default from `GROQ_MODEL` or `OPENAI_MODEL`)
- `--case-pack <path>`
- `--output-dir <path>`
- `--model <openai_model>`
- `--dry-run-evidence agent/tests/fixtures/evidence_bundle.json`
- `--skip-graph-write`
- `--max-cases 1`

## Offline test mode (no TigerGraph)

```bash
venv\Scripts\python.exe -m pytest agent\tests -q
```

This validates:
- prompt assembly
- output schema + policy guards
- evidence-bound ID filtering
- exposure recomputation

## Docker-ready handoff checklist

1. Start local TigerGraph Docker and confirm host/credentials in `agent/.env`.
2. Build filtered data:
   - `venv\Scripts\python.exe Scripts\Case_data.py`
3. In `graph/`:
   - `gsql setup.gsql`
   - `gsql utils/indexes.gsql`
4. Run loading jobs in order:
   - customers, cards, transactions, devices, email domains, billing regions, closed cases.
5. Post-load:
   - install + run `refresh_customer_stats`
   - install + run `create_next_edges`
6. Install queries:
   - `gsql queries/transaction_queries.gsql`
   - `gsql queries/fraud_queries.gsql`
   - `gsql queries/similarity_queries.gsql`
   - `gsql queries/agent_evidence_queries.gsql`
   - `INSTALL QUERY ALL`
7. Smoke test:
   - run installed query `get_evidence_bundle` for one known flagged transaction.
8. Agent smoke test:
   - `venv\Scripts\python.exe agent\agent.py --case-id HHG-001 --max-cases 1`
9. Full run:
   - `venv\Scripts\python.exe agent\agent.py --all-cases`
