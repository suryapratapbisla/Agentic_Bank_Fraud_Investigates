"""
Bootstrap CaseMemory index from closed_cases_history.csv.

Usage (from repo root):
  venv\\Scripts\\python.exe Scripts/bootstrap_case_memory.py
  venv\\Scripts\\python.exe Scripts/bootstrap_case_memory.py --limit 100
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
AGENT_DIR = PROJECT_ROOT / "agent"
sys.path.insert(0, str(AGENT_DIR))

from graph_queries import get_conn  # noqa: E402
from memory.document_builder import from_closed_case_row  # noqa: E402
from memory.semantic_retrieval import embed_text  # noqa: E402
from memory.vector_store import link_memory_to_closed_case, upsert_case_memory_vertex, upsert_case_memory_vector  # noqa: E402

DEFAULT_CSV = PROJECT_ROOT / "DATA" / "filtered_data" / "closed_cases_history.csv"
ARTIFACTS = PROJECT_ROOT / "artifacts" / "memory"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Bootstrap CaseMemory vertices and embeddings.")
    parser.add_argument("--csv", default=str(DEFAULT_CSV), help="closed_cases_history.csv path")
    parser.add_argument("--limit", type=int, default=None, help="Max cases to index (dev)")
    parser.add_argument("--batch-size", type=int, default=50, help="Embedding batch size")
    parser.add_argument("--skip-embed", action="store_true", help="Upsert text only, no vectors")
    return parser.parse_args()


def main() -> int:
    load_dotenv(AGENT_DIR / ".env")
    load_dotenv(PROJECT_ROOT / ".env")
    args = parse_args()

    csv_path = Path(args.csv)
    if not csv_path.exists():
        print(f"Missing CSV: {csv_path}")
        return 1

    df = pd.read_csv(csv_path)
    if args.limit:
        df = df.head(args.limit)

    print(f"Indexing {len(df)} closed cases into CaseMemory...")
    conn = get_conn()

    indexed = 0
    embedded = 0
    errors = 0
    batch_docs = []

    for _, row in df.iterrows():
        row_dict = row.to_dict()
        case_id = str(row_dict.get("case_id", "")).strip()
        if not case_id:
            continue
        try:
            doc = from_closed_case_row(row_dict)
            upsert_case_memory_vertex(conn, doc)
            link_memory_to_closed_case(conn, case_id, case_id)
            batch_docs.append(doc)
            indexed += 1
        except Exception as exc:
            errors += 1
            print(f"  error {case_id}: {exc}")

        if not args.skip_embed and len(batch_docs) >= args.batch_size:
            embedded += _embed_batch(conn, batch_docs)
            batch_docs = []
            time.sleep(0.2)

    if not args.skip_embed and batch_docs:
        embedded += _embed_batch(conn, batch_docs)

    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    stats = {
        "indexed_vertices": indexed,
        "embedded_vectors": embedded,
        "errors": errors,
        "csv": str(csv_path),
        "limit": args.limit,
    }
    stats_path = ARTIFACTS / "bootstrap_stats.json"
    stats_path.write_text(json.dumps(stats, indent=2), encoding="utf-8")
    print(f"Done. indexed={indexed} embedded={embedded} errors={errors}")
    print(f"Stats: {stats_path}")
    return 0 if errors == 0 else 2


def _embed_batch(conn, docs) -> int:
    count = 0
    for doc in docs:
        try:
            vector = embed_text(doc.embedding_text)
            upsert_case_memory_vector(conn, doc.case_id, vector)
            count += 1
        except Exception as exc:
            print(f"  embed error {doc.case_id}: {exc}")
    return count


if __name__ == "__main__":
    raise SystemExit(main())
