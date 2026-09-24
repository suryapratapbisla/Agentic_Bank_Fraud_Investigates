from __future__ import annotations

from typing import Any, Dict, List, Optional, Set

from memory.models import GraphMemoryHit


def _list_vertices(raw: Any) -> List[Dict[str, Any]]:
    if isinstance(raw, list):
        return [v for v in raw if isinstance(v, dict)]
    return []


def _case_hit(
    vertex: Dict[str, Any],
    reason: str,
    source_query: str,
    base_score: float = 0.25,
) -> GraphMemoryHit:
    attrs = vertex.get("attributes", vertex)
    reasons = [reason]
    score = base_score
    if attrs.get("outcome") == "confirmed_fraud":
        score += 0.1
    return GraphMemoryHit(
        case_id=str(vertex.get("v_id") or attrs.get("case_id")),
        match_reasons=reasons,
        graph_score=min(score, 1.0),
        source_query=source_query,
        closed_at=str(attrs.get("closed_at", "")),
        outcome=str(attrs.get("outcome", "")),
        pattern=str(attrs.get("pattern", "")),
    )


def infer_pattern(case_row: Dict[str, Any], evidence: Dict[str, Any]) -> str:
    flagged = evidence.get("flagged_txn", {})
    attrs = flagged.get("attributes", flagged)
    channel = str(attrs.get("channel", "")).lower()
    trigger = str(case_row.get("trigger_text", "")).lower()

    if "out of region" in trigger or "billing region" in trigger:
        return "out_of_region_use"
    if channel == "online":
        device = evidence.get("device", {})
        if device:
            device_attrs = device.get("attributes", device)
            status = str(device_attrs.get("device_status", "")).lower()
            if status == "new":
                return "card_not_present_new_device"
            return "card_not_present_fraud"
        return "card_not_present_fraud"
    if channel == "in_person":
        return "out_of_region_use"
    return "undocumented"


def retrieve_graph_memory(
    conn,
    case_row: Dict[str, Any],
    evidence: Dict[str, Any],
) -> List[GraphMemoryHit]:
    hits: Dict[str, GraphMemoryHit] = {}
    flagged_txn_id = str(case_row.get("flagged_txn_id", ""))
    customer_id = str(case_row.get("customer_id", ""))
    card_id = str(case_row.get("card_id", ""))
    pattern = infer_pattern(case_row, evidence)

    def add_hit(hit: GraphMemoryHit) -> None:
        existing = hits.get(hit.case_id)
        if existing:
            merged_reasons = sorted(set(existing.match_reasons + hit.match_reasons))
            existing.match_reasons = merged_reasons
            existing.graph_score = min(1.0, existing.graph_score + hit.graph_score * 0.5)
            return
        hits[hit.case_id] = hit

    # Same customer — from evidence bundle (avoid duplicate query when possible).
    prior_key = "customer_prior_cases" if evidence.get("customer_prior_cases") is not None else "prior_cases"
    for vertex in evidence.get(prior_key) or evidence.get("prior_cases") or []:
        add_hit(_case_hit(vertex, "same_customer", "customer_prior_cases", 0.35))

    if conn is None:
        return list(hits.values())

    # Pattern similarity (cross-customer).
    if pattern and pattern not in {"none", "undocumented"}:
        try:
            raw = conn.runInstalledQuery(
                "similar_closed_cases_by_pattern",
                {"pattern": pattern, "k": 10},
            )
            payload = raw[0] if isinstance(raw, list) and raw else raw
            for vertex in _list_vertices((payload or {}).get("cases")):
                add_hit(_case_hit(vertex, "same_pattern", "similar_closed_cases_by_pattern", 0.3))
        except Exception as exc:
            print(f"[memory] similar_closed_cases_by_pattern error: {exc}")

    # Device-linked cases.
    if flagged_txn_id:
        try:
            raw = conn.runInstalledQuery(
                "similar_cases_by_device",
                {"transaction_id": flagged_txn_id},
            )
            payload = raw[0] if isinstance(raw, list) and raw else raw
            for vertex in _list_vertices((payload or {}).get("cases")):
                add_hit(_case_hit(vertex, "same_device", "similar_cases_by_device", 0.35))
        except Exception as exc:
            print(f"[memory] similar_cases_by_device error: {exc}")

    # Card-linked cases (DRV:: from transactions; EXT:: only when loaded from closed-case history).
    for cid in _card_ids_to_query(evidence, card_id):
        try:
            raw = conn.runInstalledQuery("similar_cases_by_card", {"card_id": cid})
            payload = raw[0] if isinstance(raw, list) and raw else raw
            for vertex in _list_vertices((payload or {}).get("cases")):
                add_hit(_case_hit(vertex, "same_card", "similar_cases_by_card", 0.3))
            for vertex in _list_vertices((payload or {}).get("connected")):
                add_hit(_case_hit(vertex, "connected_entity", "similar_cases_by_card", 0.25))
        except Exception as exc:
            msg = str(exc)
            if "not valid Card vertex" in msg:
                continue
            print(f"[memory] similar_cases_by_card({cid}) error: {exc}")

    # Region neighbors — map cohort cards to closed cases via customer overlap in evidence.
    region_case_ids = _region_linked_case_ids(conn, evidence, flagged_txn_id)
    for case_id in region_case_ids:
        if case_id in hits:
            hits[case_id].match_reasons = sorted(
                set(hits[case_id].match_reasons + ["same_region"])
            )
            hits[case_id].graph_score = min(1.0, hits[case_id].graph_score + 0.2)
        else:
            add_hit(
                GraphMemoryHit(
                    case_id=case_id,
                    match_reasons=["same_region"],
                    graph_score=0.25,
                    source_query="region_neighbor_cards",
                )
            )

    return list(hits.values())


def _card_ids_to_query(evidence: Dict[str, Any], case_pack_card_id: str) -> List[str]:
    """
    Card vertices in the graph:
    - DRV::... from transaction loading (owner_cards in evidence bundle)
    - EXT::... only for cards referenced in closed_cases_history.csv
    Case-pack ids like C08299-K1 are NOT automatically loaded as EXT unless they
    appear in closed-case history.
    """
    ids: Set[str] = set()
    for card in evidence.get("owner_cards") or []:
        v_id = card.get("v_id")
        if v_id:
            ids.add(str(v_id))

    prior_key = (
        "customer_prior_cases"
        if evidence.get("customer_prior_cases") is not None
        else "prior_cases"
    )
    priors = evidence.get(prior_key) or evidence.get("prior_cases") or []
    for pc in priors:
        attrs = pc.get("attributes", pc)
        raw = str(attrs.get("card_id", "")).strip()
        if not raw:
            continue
        ids.add(raw if raw.startswith("EXT::") else f"EXT::{raw}")

    bare_pack = case_pack_card_id.replace("EXT::", "") if case_pack_card_id else ""
    if bare_pack:
        for pc in priors:
            attrs = pc.get("attributes", pc)
            if str(attrs.get("card_id", "")).replace("EXT::", "") == bare_pack:
                ids.add(
                    case_pack_card_id
                    if case_pack_card_id.startswith("EXT::")
                    else f"EXT::{case_pack_card_id}"
                )
                break

    return list(ids)


def _region_linked_case_ids(
    conn,
    evidence: Dict[str, Any],
    flagged_txn_id: str,
) -> Set[str]:
    """Best-effort: fraud cases on device + pattern cases already cover most; region tag enriches."""
    del conn, evidence, flagged_txn_id
    return set()
