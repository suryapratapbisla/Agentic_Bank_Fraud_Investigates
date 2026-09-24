"""Integration test for HHG-001: evidence + memory + prompt (no LLM)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
AGENT_DIR = PROJECT_ROOT / "agent"
sys.path.insert(0, str(AGENT_DIR))

from agent import build_investigation_prompt  # noqa: E402
from graph_queries import gather_all_evidence, get_conn  # noqa: E402
from memory.pipeline import retrieve_case_memory  # noqa: E402


def main() -> int:
    case_pack = PROJECT_ROOT / "DATA" / "filtered_data" / "case_pack.csv"
    row = pd.read_csv(case_pack)
    row = row[row["case_id"] == "HHG-001"].iloc[0].to_dict()

    print("Connecting to TigerGraph...")
    conn = get_conn()

    print("Gathering evidence...")
    evidence = gather_all_evidence(
        conn,
        flagged_txn_id=str(row["flagged_txn_id"]),
        card_id=row["card_id"],
        customer_id=row["customer_id"],
    )

    print("Retrieving case memory...")
    memory = retrieve_case_memory(conn, row, evidence, top_k=5)

    prompt = build_investigation_prompt(row, evidence, memory_context=memory.context_markdown)

    out_dir = PROJECT_ROOT / "artifacts"
    out_dir.mkdir(parents=True, exist_ok=True)

    summary = {
        "case_id": "HHG-001",
        "flagged_txn_id": row["flagged_txn_id"],
        "prior_cases": [c.get("v_id") for c in evidence.get("customer_prior_cases", [])],
        "card_txn_count": len(evidence.get("card_transactions", [])),
        "graph_memory_hits": len(memory.ranked_hits),
        "top_memory_cases": [
            {"case_id": h.case_id, "score": h.final_score, "reasons": h.match_reasons}
            for h in memory.ranked_hits
        ],
        "memory_context_preview": memory.context_markdown[:1500],
        "prompt_chars": len(prompt),
    }

    summary_path = out_dir / "hhg001_pipeline_test.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    prompt_path = out_dir / "hhg001_prompt_preview.txt"
    prompt_path.write_text(prompt, encoding="utf-8")

    print("\n=== HHG-001 Pipeline Test ===")
    print(f"Prior cases (same customer): {summary['prior_cases']}")
    print(f"Card transactions in window: {summary['card_txn_count']}")
    print(f"Ranked memory hits: {summary['graph_memory_hits']}")
    for hit in summary["top_memory_cases"]:
        print(f"  - {hit['case_id']} (score={hit['score']:.2f}) reasons={hit['reasons']}")
    print(f"\nPrompt length: {summary['prompt_chars']} chars")
    print(f"Summary: {summary_path}")
    print(f"Full prompt: {prompt_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
