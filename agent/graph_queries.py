"""
Graph query helpers using installed TigerGraph queries.

Expected installed query:
  get_evidence_bundle(flagged_txn_id, customer_id, card_txn_limit)
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import pyTigerGraph as tg


def _as_bool(value: str) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def get_conn():
    kwargs: Dict[str, Any] = {
        "host": os.environ.get("TG_HOST", "http://127.0.0.1:14240"),
        "graphname": os.environ.get("TG_GRAPHNAME", "FraudInvestigationGraph"),
        "tgCloud": _as_bool(os.environ.get("TG_TGCLOUD", "false")),
    }
    if os.environ.get("TG_API_TOKEN"):
        kwargs["apiToken"] = os.environ["TG_API_TOKEN"]
    else:
        kwargs["username"] = os.environ.get("TG_USERNAME", "tigergraph")
        kwargs["password"] = os.environ.get("TG_PASSWORD", "tigergraph")
    if "restppPort" not in kwargs and "14240" in str(kwargs.get("host", "")):
        kwargs["restppPort"] = 14240
    return tg.TigerGraphConnection(**kwargs)


def _first_payload(raw: Any) -> Dict[str, Any]:
    if isinstance(raw, list) and raw:
        if isinstance(raw[0], dict):
            return raw[0]
    if isinstance(raw, dict):
        return raw
    return {}


def _first_vertex(values: Any) -> Dict[str, Any]:
    if isinstance(values, list) and values:
        return values[0]
    return {}


def _list(values: Any) -> List[Dict[str, Any]]:
    if isinstance(values, list):
        return values
    return []


def _sort_txns_chronologically(txns: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    def ts_key(t: Dict[str, Any]) -> str:
        attrs = t.get("attributes", t)
        return str(attrs.get("ts", ""))

    return sorted(txns, key=ts_key)


def run_installed_query(conn, query_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    raw = conn.runInstalledQuery(query_name, params)
    return _first_payload(raw)


def gather_all_evidence(
    conn,
    flagged_txn_id: str,
    card_id: str,  # kept for interface compatibility and prompt context
    customer_id: str,
) -> Dict[str, Any]:
    del card_id
    try:
        raw = conn.runInstalledQuery(
            "get_evidence_bundle",
            {
                "flagged_txn_id": str(flagged_txn_id),
                "customer_id": str(customer_id),
                "card_txn_limit": 30,
            },
        )
    except Exception as exc:
        print(f"[graph] get_evidence_bundle error: {exc}")
        return {
            "flagged_txn": {},
            "owner_cards": [],
            "card_transactions": [],
            "device": {},
            "device_neighbors": [],
            "fraud_cases_on_device": [],
            "customer_prior_cases": [],
            "prior_cases": [],
            "region_neighbor_cards": [],
            "email_neighbor_cards": [],
            "_tool_calls": 1,
        }

    payload = _first_payload(raw)
    customer_prior = _list(
        payload.get("customer_prior_cases") or payload.get("prior_cases")
    )
    card_txns = _sort_txns_chronologically(
        _list(payload.get("card_transactions"))
        or (_list(payload.get("tx_before")) + _list(payload.get("tx_after")))
    )

    evidence = {
        "flagged_txn": _first_vertex(payload.get("start")),
        "owner_cards": _list(payload.get("owner_cards")),
        "card_transactions": card_txns,
        "device": _first_vertex(payload.get("device")),
        "device_neighbors": _list(payload.get("device_neighbors")),
        "fraud_cases_on_device": _list(payload.get("fraud_cases_on_device")),
        "customer_prior_cases": customer_prior,
        "prior_cases": customer_prior,
        "region_neighbor_cards": _list(payload.get("region_neighbor_cards")),
        "email_neighbor_cards": _list(payload.get("email_neighbor_cards")),
        "_tool_calls": 1,
    }
    return evidence


def write_case_to_graph(conn, case_data: Dict[str, Any], case_row: Dict[str, Any]) -> str:
    graph_case_id = f"AGENT-{case_row['case_id']}"
    case = case_data["case"]
    verdict = case.get("verdict", "uncertain")
    if verdict == "fraud":
        outcome = "confirmed_fraud"
    elif verdict == "legitimate":
        outcome = "cleared"
    else:
        outcome = "uncertain"

    opened_at = case_row.get("opened_at", "")
    if not opened_at:
        opened_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    closed_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

    try:
        conn.upsertVertex(
            "ClosedCase",
            graph_case_id,
            {
                "customer_id": case_row.get("customer_id", ""),
                "card_id": case_row.get("card_id", ""),
                "opened_at": opened_at,
                "closed_at": closed_at,
                "outcome": outcome,
                "pattern": case.get("pattern", ""),
                "first_fraud_txn_id": case.get("first_suspicious_txn_id", ""),
                "n_txns": len(case.get("affected_txn_ids", [])),
                "exposure_usd": case.get("exposure_usd", 0),
                "actions_taken": "|".join(
                    a["action"] for a in case_data.get("next_best_actions", {}).get("final", [])
                ),
                "report_filed": str(case_data.get("sar", {}).get("file", False)),
                "analyst_notes": case.get("summary", ""),
            },
        )

        for txn_id in case.get("affected_txn_ids", []):
            conn.upsertEdge("ClosedCase", graph_case_id, "INVOLVES", "Transaction", str(txn_id))

        external_card_id = case_row.get("card_id", "")
        if external_card_id:
            ext_id = f"EXT::{external_card_id}"
            conn.upsertVertex(
                "Card",
                ext_id,
                {"customer_id": case_row.get("customer_id", "")},
            )
            conn.upsertEdge("ClosedCase", graph_case_id, "ON_CARD", "Card", ext_id)

        for connected in case.get("connected_card_ids", []):
            cid = str(connected)
            if not cid.startswith("EXT::") and not cid.startswith("DRV::"):
                cid = f"EXT::{cid}"
            conn.upsertVertex("Card", cid, {"customer_id": case_row.get("customer_id", "")})
            conn.upsertEdge("ClosedCase", graph_case_id, "CONNECTED_TO", "Card", cid)

        return graph_case_id
    except Exception as exc:
        print(f"[graph] write_case_to_graph error: {exc}")
        return ""
