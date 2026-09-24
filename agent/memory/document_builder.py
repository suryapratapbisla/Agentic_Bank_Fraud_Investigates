from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional

from memory.models import CaseMemoryDocument, GraphFeatures, SarSummary


def _clean(text: Any) -> str:
    return str(text or "").strip()


def _risk_factors_from_pattern(pattern: str, outcome: str, notes: str) -> List[str]:
    factors: List[str] = []
    p = _clean(pattern)
    o = _clean(outcome)
    notes_l = notes.lower()
    if p and p != "none":
        factors.append(p)
    if o == "confirmed_fraud":
        factors.append("confirmed_fraud")
    if "out of region" in notes_l or "billing region" in notes_l:
        factors.append("out_of_region")
    if "new device" in notes_l or "not previously seen" in notes_l:
        factors.append("new_device")
    if "repeat" in notes_l or "reported unrecognized" in notes_l:
        factors.append("repeat_victim_signal")
    return sorted(set(factors))


def _customer_summary(customer_id: str, card_id: str, pattern: str) -> str:
    card = _clean(card_id) or "primary card"
    pat = _clean(pattern).replace("_", " ") if pattern and pattern != "none" else "prior activity"
    return f"Cardholder {customer_id} with activity on {card}; historical pattern includes {pat}."


def _investigation_summary_from_row(row: Dict[str, Any]) -> str:
    notes = _clean(row.get("analyst_notes"))
    if notes:
        return notes[:500]
    outcome = _clean(row.get("outcome"))
    pattern = _clean(row.get("pattern"))
    exposure = row.get("exposure_usd", 0)
    return (
        f"Closed case with outcome {outcome}, pattern {pattern}, "
        f"exposure ${exposure}."
    )


def _evidence_bullets(row: Dict[str, Any], extra: Optional[Dict[str, Any]] = None) -> List[str]:
    bullets: List[str] = []
    pattern = _clean(row.get("pattern"))
    outcome = _clean(row.get("outcome"))
    exposure = row.get("exposure_usd", 0)
    n_txns = row.get("n_txns", 0)
    if pattern and pattern != "none":
        bullets.append(f"Fraud pattern classified as {pattern.replace('_', ' ')}.")
    if outcome:
        bullets.append(f"Investigation outcome: {outcome.replace('_', ' ')}.")
    if exposure:
        bullets.append(f"Total exposure approximately ${exposure}.")
    if n_txns:
        bullets.append(f"{n_txns} transaction(s) involved.")
    notes = _clean(row.get("analyst_notes"))
    if "blocked" in notes.lower():
        bullets.append("Card was blocked and customer reimbursed.")
    if extra:
        regions = extra.get("regions") or []
        if regions:
            bullets.append(f"Billing regions involved: {', '.join(regions[:5])}.")
        channel = extra.get("channel")
        if channel:
            bullets.append(f"Primary channel context: {channel}.")
    return bullets[:6]


def build_embedding_text(doc: CaseMemoryDocument) -> str:
    parts = [
        doc.investigation_summary,
        doc.analyst_notes,
        doc.fraud_type.replace("_", " "),
        ", ".join(doc.risk_factors),
    ]
    if doc.sar and doc.sar.narrative:
        parts.append(doc.sar.narrative)
    return "\n".join(p for p in parts if p)


def from_closed_case_row(
    row: Dict[str, Any],
    *,
    graph_enrichment: Optional[Dict[str, Any]] = None,
) -> CaseMemoryDocument:
    case_id = _clean(row.get("case_id"))
    customer_id = _clean(row.get("customer_id"))
    card_id = _clean(row.get("card_id"))
    pattern = _clean(row.get("pattern")) or "none"
    outcome = _clean(row.get("outcome")) or "uncertain"
    notes = _clean(row.get("analyst_notes"))
    closed_at = _clean(row.get("closed_at"))

    regions: List[str] = []
    channel = ""
    if graph_enrichment:
        regions = list(graph_enrichment.get("regions") or [])
        channel = _clean(graph_enrichment.get("channel"))

    graph_features = GraphFeatures(
        customer_id=customer_id,
        card_ids=[card_id] if card_id else [],
        regions=regions,
        pattern=pattern,
        channel=channel,
        outcome=outcome,
    )

    report_filed = _clean(row.get("report_filed")).lower() in {"yes", "true", "1"}
    sar = SarSummary(
        file=report_filed,
        reason="SAR filed per case record" if report_filed else "",
        narrative=notes if report_filed else "",
    )

    doc = CaseMemoryDocument(
        case_id=case_id,
        customer_summary=_customer_summary(customer_id, card_id, pattern),
        fraud_type=pattern,
        risk_factors=_risk_factors_from_pattern(pattern, outcome, notes),
        investigation_summary=_investigation_summary_from_row(row),
        evidence=_evidence_bullets(row, {"regions": regions, "channel": channel}),
        outcome=outcome,
        sar=sar if report_filed else None,
        analyst_notes=notes,
        graph_features=graph_features,
        closed_at=closed_at,
    )
    doc.embedding_text = build_embedding_text(doc)
    return doc


def from_closed_case_vertex(
    vertex: Dict[str, Any],
    *,
    graph_enrichment: Optional[Dict[str, Any]] = None,
) -> CaseMemoryDocument:
    attrs = vertex.get("attributes", vertex)
    row = {
        "case_id": vertex.get("v_id") or attrs.get("case_id"),
        "customer_id": attrs.get("customer_id"),
        "card_id": attrs.get("card_id"),
        "pattern": attrs.get("pattern"),
        "outcome": attrs.get("outcome"),
        "analyst_notes": attrs.get("analyst_notes"),
        "closed_at": attrs.get("closed_at"),
        "exposure_usd": attrs.get("exposure_usd"),
        "n_txns": attrs.get("n_txns"),
        "report_filed": attrs.get("report_filed"),
    }
    return from_closed_case_row(row, graph_enrichment=graph_enrichment)


def from_investigation_result(
    investigation: Dict[str, Any],
    case_row: Dict[str, Any],
    evidence: Dict[str, Any],
) -> CaseMemoryDocument:
    case = investigation.get("case", {})
    sar_data = investigation.get("sar", {})
    customer_id = _clean(case_row.get("customer_id"))
    card_id = _clean(case_row.get("card_id"))
    pattern = _clean(case.get("pattern")) or "undocumented"
    outcome = _clean(case.get("verdict"))
    if outcome == "fraud":
        outcome = "confirmed_fraud"
    elif outcome == "legitimate":
        outcome = "cleared"
    else:
        outcome = "uncertain"

    flagged = evidence.get("flagged_txn", {})
    flagged_attrs = flagged.get("attributes", flagged)
    channel = _clean(flagged_attrs.get("channel"))
    region = _clean(flagged_attrs.get("addr1"))

    graph_features = GraphFeatures(
        customer_id=customer_id,
        card_ids=[card_id] if card_id else [],
        device_hashes=[
            str(d)
            for d in case.get("connected_device_profiles", [])
            if d
        ],
        regions=[region] if region else [],
        pattern=pattern,
        channel=channel,
        outcome=outcome,
    )

    summary = _clean(case.get("summary"))
    notes = summary
    risk = _risk_factors_from_pattern(pattern, outcome, summary)
    if case_row.get("trigger_type") == "risk_score":
        risk.append("model_alert")

    sar = SarSummary(
        file=bool(sar_data.get("file")),
        reason=_clean(sar_data.get("reason")),
        narrative=_clean(sar_data.get("narrative")),
    )

    doc = CaseMemoryDocument(
        case_id=f"AGENT-{_clean(case_row.get('case_id'))}",
        customer_summary=_customer_summary(customer_id, card_id, pattern),
        fraud_type=pattern,
        risk_factors=sorted(set(risk)),
        investigation_summary=summary or _clean(case_row.get("trigger_text")),
        evidence=[
            e.get("claim", "")
            for e in case.get("evidence", [])
            if e.get("claim")
        ][:6],
        outcome=outcome,
        sar=sar if sar.file else None,
        analyst_notes=notes,
        graph_features=graph_features,
        closed_at=_clean(case_row.get("opened_at")),
    )
    doc.embedding_text = build_embedding_text(doc)
    return doc


def parse_graph_features_json(raw: str) -> GraphFeatures:
    if not raw:
        return GraphFeatures()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return GraphFeatures()
    return GraphFeatures(
        customer_id=_clean(data.get("customer_id")),
        card_ids=list(data.get("card_ids") or []),
        device_hashes=list(data.get("device_hashes") or []),
        regions=list(data.get("regions") or []),
        pattern=_clean(data.get("pattern")),
        channel=_clean(data.get("channel")),
        outcome=_clean(data.get("outcome")),
    )
