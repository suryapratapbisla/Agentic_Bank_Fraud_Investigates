"""
Filter transactions.csv down to only the customers we need for testing,
then merge with identity.csv on TransactionID.

DEV_MODE (default True): keep only the 20 case-pack customers and their
flagged transaction ids. Set DEV_MODE = False for the full subset
(20 case-pack customers + all closed-case customers + closed-case txn ids).

WHY: transactions.csv is ~708MB / 590k rows with 393 columns. We don't
need the full file to build and test the graph + agent pipeline. This
script streams the big file in chunks (so it never fully loads into
memory) and keeps only rows that matter right now. Once your schema
and agent logic work on this subset, load the full transactions.csv
for the final run.

USAGE:
    Keep transactions.csv, identity.csv, case_pack.csv, and
    closed_cases_history.csv in the DATA/ folder, then run:

        venv/Scripts/python.exe Scripts/Case_data.py

OUTPUT (in DATA/filtered_data/):
    - transactions_with_identity_filtered.csv   <- load THIS into TigerGraph
      Includes derived_card_id built from customer_id + card1..card6.
    - closed_cases_history.csv                  <- copied as-is (already small)
    - case_pack.csv                              <- copied as-is
    - filter_stats.txt                           <- what got kept and why
"""

import os
import pandas as pd

# Script is in Scripts/; source CSVs and filtered output live in DATA/
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(SCRIPT_DIR, "..", "DATA")

TRANSACTIONS_PATH = os.path.join(DATA_DIR, "transactions.csv")
IDENTITY_PATH = os.path.join(DATA_DIR, "identity.csv")
CASE_PACK_PATH = os.path.join(DATA_DIR, "case_pack.csv")
CLOSED_CASES_PATH = os.path.join(DATA_DIR, "closed_cases_history.csv")

OUT_DIR = os.path.join(DATA_DIR, "filtered_data")
os.makedirs(OUT_DIR, exist_ok=True)

CHUNK_SIZE = 50_000  # rows per chunk read from transactions.csv
DEV_MODE = True  # False = full subset (20 case-pack + all closed-case customers)
CARD_KEY_COLUMNS = ["customer_id", "card1", "card2", "card3", "card4", "card5", "card6"]


def prefix_ext_card_id(card_id):
    card_id = str(card_id).strip()
    if not card_id:
        return ""
    return f"EXT::{card_id}"


def prefix_ext_connected_cards(value):
    if pd.isna(value):
        return ""
    text = str(value).strip()
    if not text:
        return ""
    return "|".join(prefix_ext_card_id(token) for token in text.split("|") if token.strip())


def main():
    stats_lines = []

    def log(msg):
        print(msg)
        stats_lines.append(msg)

    # ---- 1. Load the small files fully ----
    case_pack = pd.read_csv(CASE_PACK_PATH)
    closed_cases = pd.read_csv(CLOSED_CASES_PATH)

    log(f"case_pack.csv: {len(case_pack)} cases")
    log(f"closed_cases_history.csv: {len(closed_cases)} closed cases")

    # ---- 2. Build the set of customer_ids and txn ids worth keeping ----
    log(f"DEV_MODE: {DEV_MODE}")

    if DEV_MODE:
        needed_customers = set(case_pack["customer_id"].astype(str).unique())
        needed_txn_ids = set(case_pack["flagged_txn_id"].astype(str))

        log(f"Unique customers in case_pack: {len(needed_customers)}")
        log(f"Total unique customers to keep: {len(needed_customers)}")
        log(f"Explicit flagged txn ids (case pack): {len(needed_txn_ids)}")
    else:
        case_pack_customers = set(case_pack["customer_id"].astype(str).unique())
        closed_case_customers = set(closed_cases["customer_id"].astype(str).unique())
        needed_customers = case_pack_customers | closed_case_customers

        log(f"Unique customers in case_pack: {len(case_pack_customers)}")
        log(f"Unique customers in closed_cases_history: {len(closed_case_customers)}")
        log(f"Total unique customers to keep: {len(needed_customers)}")

        flagged_txn_ids = set(case_pack["flagged_txn_id"].astype(str))
        closed_txn_ids = set()
        for txn_str in closed_cases["txn_ids"].dropna().astype(str):
            closed_txn_ids.update(t.strip() for t in txn_str.split("|") if t.strip())

        needed_txn_ids = flagged_txn_ids | closed_txn_ids
        log(f"Explicit flagged txn ids (case pack): {len(flagged_txn_ids)}")
        log(f"Explicit txn ids from closed cases: {len(closed_txn_ids)}")

    # ---- 4. Stream transactions.csv, filter chunk by chunk ----
    log(f"\nStreaming {TRANSACTIONS_PATH} in chunks of {CHUNK_SIZE:,} rows...")

    filtered_chunks = []
    total_rows = 0
    kept_rows = 0

    for i, chunk in enumerate(pd.read_csv(TRANSACTIONS_PATH, chunksize=CHUNK_SIZE, low_memory=False)):
        total_rows += len(chunk)
        chunk["TransactionID"] = chunk["TransactionID"].astype(str)
        chunk["customer_id"] = chunk["customer_id"].astype(str)

        mask = chunk["customer_id"].isin(needed_customers) | chunk["TransactionID"].isin(needed_txn_ids)
        filtered = chunk[mask]

        if len(filtered) > 0:
            filtered_chunks.append(filtered)
            kept_rows += len(filtered)

        print(f"  chunk {i + 1}: processed {total_rows:,} rows so far, kept {kept_rows:,}", end="\r")

    print()
    log(f"Done streaming. Kept {kept_rows:,} of {total_rows:,} total transactions "
        f"({kept_rows / max(total_rows, 1) * 100:.1f}%).")

    if not filtered_chunks:
        raise SystemExit("No rows matched. Check that customer_id values line up between files.")

    transactions_filtered = pd.concat(filtered_chunks, ignore_index=True)

    # ---- 5. Merge with identity.csv (left join: only online txns have identity rows) ----
    identity = pd.read_csv(IDENTITY_PATH)
    identity["TransactionID"] = identity["TransactionID"].astype(str)

    key_frame = transactions_filtered[CARD_KEY_COLUMNS].fillna("").astype(str)
    transactions_filtered["derived_card_id"] = "DRV::" + key_frame.agg("::".join, axis=1)
    n_derived_cards = transactions_filtered["derived_card_id"].nunique()
    log(f"Derived card ids from customer_id+card1..card6: {n_derived_cards:,} unique")

    merged = transactions_filtered.merge(identity, on="TransactionID", how="left")
    n_with_identity = merged["DeviceType"].notna().sum() if "DeviceType" in merged.columns else 0

    log(f"Merged with identity.csv: {len(merged):,} rows total, "
        f"{n_with_identity:,} have an identity/device record (online channel).")

    # ---- 6. Write outputs ----
    out_path = os.path.join(OUT_DIR, "transactions_with_identity_filtered.csv")
    merged.to_csv(out_path, index=False)
    log(f"\nWrote: {out_path}")

    closed_cases["ext_card_id"] = closed_cases["card_id"].astype(str).map(prefix_ext_card_id)
    closed_cases["ext_connected_card_ids"] = closed_cases["connected_card_ids"].map(
        prefix_ext_connected_cards
    )
    closed_cases.to_csv(os.path.join(OUT_DIR, "closed_cases_history.csv"), index=False)
    case_pack.to_csv(os.path.join(OUT_DIR, "case_pack.csv"), index=False)
    log(f"Wrote closed_cases_history.csv with ext_card_id/ext_connected_card_ids into {OUT_DIR}/.")

    if DEV_MODE:
        log("\nNOTE: DEV_MODE is on — only the 20 case-pack customers are in the "
            "filtered transactions file. Cross-customer links (e.g. a device shared "
            "with a customer outside those 20) won't be visible until you set "
            "DEV_MODE = False or load the full transactions.csv.")
    else:
        log("\nNOTE: This subset includes customers from case_pack.csv and "
            "closed_cases_history.csv. Cross-customer links (e.g. a device shared with a "
            "customer who is in neither list) won't be visible until you load the full "
            "transactions.csv. Use this subset to build and debug your schema + agent first.")

    with open(os.path.join(OUT_DIR, "filter_stats.txt"), "w") as f:
        f.write("\n".join(stats_lines))


if __name__ == "__main__":
    main()