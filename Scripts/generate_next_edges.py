"""Build next_edges.csv for TigerGraph NEXT edge loading."""

from __future__ import annotations

import csv
from collections import defaultdict
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
TXN_PATH = PROJECT_ROOT / "DATA" / "filtered_data" / "transactions_with_identity_filtered.csv"
OUT_PATH = PROJECT_ROOT / "DATA" / "filtered_data" / "next_edges.csv"


def parse_ts(value: str) -> datetime:
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    return datetime.min


def main() -> None:
    by_card: dict[str, list[tuple[datetime, str]]] = defaultdict(list)
    with TXN_PATH.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            card_id = row.get("derived_card_id", "").strip()
            txn_id = row.get("TransactionID", row.get("transaction_id", "")).strip()
            ts_raw = row.get("ts", "").strip()
            if not card_id or not txn_id:
                continue
            by_card[card_id].append((parse_ts(ts_raw), txn_id))

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    edge_count = 0
    with OUT_PATH.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["from_txn", "to_txn"])
        for txns in by_card.values():
            txns.sort(key=lambda item: (item[0], item[1]))
            for idx in range(len(txns) - 1):
                writer.writerow([txns[idx][1], txns[idx + 1][1]])
                edge_count += 1

    print(f"Wrote {edge_count} NEXT edges to {OUT_PATH}")


if __name__ == "__main__":
    main()
