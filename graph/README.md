# Fraud Investigation Graph

Modular GSQL for `FraudInvestigationGraph`. Vertex and edge definitions are unchanged from the original schema; they are only split into files.

Run every `gsql` command from this `graph/` folder so `@schema/...` includes and relative CSV paths resolve.

## Layout

```
graph/
├── schema/
│   ├── vertices.gsql
│   ├── edges.gsql
│   └── graph.gsql
├── loading/
│   ├── load_customers.gsql
│   ├── load_cards.gsql
│   ├── load_transactions.gsql
│   ├── load_devices.gsql
│   ├── load_email_domains.gsql
│   ├── load_billing_regions.gsql
│   └── load_closed_cases.gsql
├── queries/
│   ├── customer_queries.gsql
│   ├── transaction_queries.gsql
│   ├── fraud_queries.gsql
│   ├── similarity_queries.gsql
│   └── agent_evidence_queries.gsql
├── utils/
│   ├── create_next_edges.gsql
│   └── indexes.gsql
├── drop_schema.gsql
├── setup.gsql
└── README.md
```

## Data files

Loading jobs read:

```
../DATA/filtered_data/transactions_with_identity_filtered.csv
../DATA/filtered_data/case_pack.csv
../DATA/filtered_data/closed_cases_history.csv
```

Build that subset from the repo root with the project venv:

```
venv\Scripts\python.exe Scripts\Case_data.py
```

## First install

```
gsql setup.gsql
gsql utils/indexes.gsql
```

`setup.gsql` runs schema files in order: vertices → edges → graph.

## Load data

Each file loads one vertex. Installing the file only creates the job. Run it with the `RUN LOADING JOB` line at the bottom of that file (paths are relative to `graph/`).

Order:

1. `gsql loading/load_customers.gsql` then run `load_customers`
2. `gsql loading/load_cards.gsql` then run `load_cards`
3. `gsql loading/load_transactions.gsql` then run `load_transactions`
4. `gsql loading/load_devices.gsql` then run `load_devices`
5. `gsql loading/load_email_domains.gsql` then run `load_email_domains`
6. `gsql loading/load_billing_regions.gsql` then run `load_billing_regions`
7. `gsql loading/load_closed_cases.gsql` then run `load_closed_cases`

After each run: `SHOW LOADING STATUS ALL`

Re-running a job upserts the same primary ids. Customer card/transaction counts are filled by `refresh_customer_stats()`, not by a COUNT reducer, so a second load does not double them.

## Post-load

```
gsql queries/customer_queries.gsql
gsql utils/create_next_edges.gsql
INSTALL QUERY refresh_customer_stats
INSTALL QUERY create_next_edges
RUN QUERY refresh_customer_stats()
RUN QUERY create_next_edges()
```

Then install the rest of the query files:

```
gsql queries/transaction_queries.gsql
gsql queries/fraud_queries.gsql
gsql queries/similarity_queries.gsql
gsql queries/agent_evidence_queries.gsql
INSTALL QUERY ALL
```

## Rebuild from scratch

```
gsql drop_schema.gsql
gsql setup.gsql
```

Then repeat indexes, loading, post-load, and queries.

If the graph does not exist yet, skip `drop_schema.gsql` — a missing `DROP GRAPH` will stop the GSQL client.

## Notes

- **NEXT** is not in the CSVs. `utils/create_next_edges.gsql` walks each card’s transactions by `ts` and inserts the chain (needed for card-testing). It only sees cards that have `MADE` edges.
- **Card IDs:** `transactions_with_identity_filtered.csv` now includes `derived_card_id` generated from `customer_id + card1..card6`. `load_cards.gsql` and `load_transactions.gsql` use that same key so every kept transaction gets a `MADE` edge.
- **External case card IDs:** values like `C01234-K1` from `closed_cases_history.csv` are loaded as separate `Card` vertices with `EXT::` prefix. They stay separate from `derived_card_id` until a verified mapping exists.
- **Device key** is derived as `DeviceType|DeviceInfo|id_30` because there is no `device_hash` column. `device_status` is unmapped (`TODO`: schema comment says `id_12` or `id_28`; the data readme says `id_15`).
- **first_fraud_txn_id** is loaded unchanged. Some values look like `3000120.0` (`TODO` in `load_closed_cases.gsql`).
- Filtered data covers case-pack plus closed-case customers. Shared-device links to people outside those lists need the full `transactions.csv`.
