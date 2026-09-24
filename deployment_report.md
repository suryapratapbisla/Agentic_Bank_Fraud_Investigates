# deployment_report

Date: 2026-09-23
Container: tigergraph (Community 4.2.5)
Staging root: /tmp/agentic_deploy

## completed steps

- Regenerated filtered data with `derived_card_id`, `ext_card_id`, and `ext_connected_card_ids`.
- Destructive reset and schema deployment (`drop_schema.gsql` + `setup.gsql`).
- All 8 loading jobs installed and executed with `ERRORS=0`:
  - `load_customers`, `load_cards`, `load_transactions`, `load_next_edges`, `load_devices`, `load_email_domains`, `load_billing_regions`, `load_closed_cases`
- Global index schema change job applied (`add_investigation_indexes`).
- Post-load `refresh_customer_stats()` executed.
- All investigation queries registered and installed (`INSTALL QUERY ALL`, zero DRAFT).
- Sanity queries and `get_evidence_bundle("3514030","C12382",100)` succeeded.
- Evidence artifact saved to `artifacts/evidence_bundle_HHG-001.json`.

## failed steps

- none

## warnings

- NEXT edges are loaded via `Scripts/generate_next_edges.py` + `load_next_edges.gsql` because the in-graph `create_next_edges` query uses POST-ACCUM patterns not fully supported on TG 4.2.5. Only edges where both endpoint transactions exist in the graph are loaded (1,265 loaded vs more pairs in CSV).
- `refresh_customer_stats` currently updates card counts only (simplified for TG 4.2.5 parser compatibility).
- DEV_MODE=True limits transaction subgraph to 20 case-pack customers; closed-case INVOLVES edges attach only where referenced transactions exist in the filtered set.
- External case card ids (`EXT::...`) remain separate from derived transaction card ids (`DRV::...`).

## schema issues

- none blocking deployment

## loading issues

- none (`ERRORS=0` on all loader runs)

## mapping issues

- Historical external card ids use `EXT::` prefix and are not merged into derived transaction card ids.
- `first_fraud_txn_id` formatting in closed cases (e.g. `3000120.0`) remains a known data-format TODO.

## validation snapshot

| Metric | Count |
|--------|------:|
| Customer | 20 |
| Card | 30+ (includes EXT:: cards) |
| Transaction | 26,643 |
| ClosedCase | 5,565 |
| NEXT | 1,265 |
| INVOLVES | 14,955 |
| ON_CARD | 5,565 |
| CONNECTED_TO | 92 |

## installed query list

All 21 investigation queries installed (zero DRAFT), including:

- `refresh_customer_stats`
- `get_customer_profile`, `get_customer_cards`, `get_customer_txn_history`
- `get_transaction`, `get_flagged_context`, `get_card_transactions`, `get_card_window`
- `get_device_neighbors`, `get_region_neighbors`, `detect_card_testing`, `detect_out_of_region`, `compute_exposure`
- `similar_closed_cases_by_pattern`, `similar_closed_cases_by_outcome`, `similar_cases_by_device`, `similar_cases_by_card`, `get_closed_case`
- `get_evidence_bundle`

## recommendations

- Re-run pipeline: `graph/deployment/deploy.ps1` then `graph/deployment/verify.ps1` (use subst drive `X:` on Windows if path apostrophe causes shell issues).
- Switch `DEV_MODE=False` in `Scripts/Case_data.py` when broader cross-customer link discovery is needed.
- Optionally restore full `refresh_customer_stats` min/max transaction aggregation once a TG 4.2.5-safe multi-pass pattern is validated.

## artifacts

- `artifacts/deployment/deploy.log`
- `artifacts/deployment/04_run_loading_jobs.log`
- `artifacts/deployment/counts_and_queries.log`
- `artifacts/deployment/sanity_checks.log`
- `artifacts/evidence_bundle_HHG-001.json`
