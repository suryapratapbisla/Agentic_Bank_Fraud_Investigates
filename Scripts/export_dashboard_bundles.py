"""Export get_evidence_bundle payloads for dashboard offline graph view."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

import pandas as pd

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
AGENT_DIR = PROJECT_ROOT / "agent"
sys.path.insert(0, str(AGENT_DIR))

from graph_queries import gather_all_evidence, get_conn  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Export TG evidence bundles for dashboard.")
    parser.add_argument(
        "--case-pack",
        default=str(PROJECT_ROOT / "DATA" / "filtered_data" / "case_pack.csv"),
    )
    parser.add_argument(
        "--out-dir",
        default=str(PROJECT_ROOT / "dashboard" / "src" / "data" / "bundles"),
    )
    parser.add_argument(
        "--cases-dir",
        default=str(PROJECT_ROOT / "cases"),
        help="Source case JSON to copy into dashboard/src/data",
    )
    parser.add_argument(
        "--sync-cases",
        action="store_true",
        help="Copy cases/HHG-*.json to dashboard/src/data/",
    )
    parser.add_argument("--limit", type=int, default=0, help="Max cases (0 = all)")
    args = parser.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    if args.sync_cases:
        dash_data = PROJECT_ROOT / "dashboard" / "src" / "data"
        for src in Path(args.cases_dir).glob("HHG-*.json"):
            shutil.copy2(src, dash_data / src.name)
        print(f"Synced case JSON to {dash_data}")

    case_pack = pd.read_csv(args.case_pack)
    if args.limit:
        case_pack = case_pack.head(args.limit)

    print("Connecting to TigerGraph...")
    conn = get_conn()
    ok = 0
    errors: list[str] = []

    for _, row in case_pack.iterrows():
        case_id = row["case_id"]
        try:
            evidence = gather_all_evidence(
                conn,
                flagged_txn_id=str(row["flagged_txn_id"]),
                card_id=str(row["card_id"]),
                customer_id=str(row["customer_id"]),
            )
            path = out_dir / f"{case_id}.json"
            path.write_text(json.dumps(evidence, indent=2), encoding="utf-8")
            ok += 1
            print(f"  {case_id} -> {path.name}")
        except Exception as exc:
            errors.append(f"{case_id}: {exc}")
            print(f"  {case_id} FAILED: {exc}")

    print(f"Done. exported={ok} errors={len(errors)} dir={out_dir}")
    if errors:
        for e in errors[:5]:
            print(f"  - {e}")
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
