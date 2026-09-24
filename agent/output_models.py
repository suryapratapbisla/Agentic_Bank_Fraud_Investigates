from __future__ import annotations

import re
from typing import Any, Dict, List, Literal, Optional, Set

from pydantic import BaseModel, ConfigDict, Field, ValidationError

ActionName = Literal[
    "ALLOW_TRANSACTION",
    "DECLINE_TRANSACTION",
    "MONITOR_CARD",
    "MONITOR_CONNECTED_CARDS",
    "WARN_CUSTOMER",
    "VERIFY_WITH_CUSTOMER",
    "STEP_UP_AUTH",
    "BLOCK_CARD",
    "BLOCK_ALL_CARDS",
    "GENERATE_REPORT",
    "CREATE_CASE",
    "FILE_REPORT",
    "ESCALATE_TO_ANALYST",
    "CLOSE_NO_FRAUD",
]
RouteName = Literal["auto", "L1", "L2"]
Verdict = Literal["fraud", "legitimate", "uncertain"]
CaseStatus = Literal["open", "closed_fraud", "closed_legitimate", "escalated"]
PatternName = Literal[
    "card_testing",
    "card_not_present_fraud",
    "card_not_present_new_device",
    "out_of_region_use",
    "account_takeover",
    "undocumented",
    "none",
]

ROUTE_BY_ACTION: Dict[str, Set[str]] = {
    "ALLOW_TRANSACTION": {"auto"},
    "DECLINE_TRANSACTION": {"L1"},
    "MONITOR_CARD": {"auto"},
    "MONITOR_CONNECTED_CARDS": {"auto"},
    "WARN_CUSTOMER": {"auto"},
    "VERIFY_WITH_CUSTOMER": {"auto"},
    "STEP_UP_AUTH": {"auto"},
    "BLOCK_CARD": {"L1", "L2"},
    "BLOCK_ALL_CARDS": {"L2"},
    "GENERATE_REPORT": {"auto"},
    "CREATE_CASE": {"auto"},
    "FILE_REPORT": {"L2"},
    "ESCALATE_TO_ANALYST": {"auto"},
    "CLOSE_NO_FRAUD": {"auto"},
}

FILE_REPORT_EXPOSURE_THRESHOLD = 1000.0


class ActionItem(BaseModel):
    action: ActionName
    route: RouteName
    reason: str


class EvidenceItem(BaseModel):
    claim: str
    source: Literal["graph", "document", "customer", "external"]
    ref: str
    entity_ids: List[str] = Field(default_factory=list)


class CaseSection(BaseModel):
    status: CaseStatus
    verdict: Verdict
    fraud_probability: float
    pattern: PatternName
    pattern_description: str
    affected_txn_ids: List[str] = Field(default_factory=list)
    first_suspicious_txn_id: str
    connected_card_ids: List[str] = Field(default_factory=list)
    connected_device_profiles: List[str] = Field(default_factory=list)
    exposure_usd: float
    evidence: List[EvidenceItem] = Field(default_factory=list)
    similar_prior_cases: List[str] = Field(default_factory=list)
    summary: str
    written_to_graph: bool
    graph_case_id: str


class EvidenceRequest(BaseModel):
    type: Literal["customer_validation", "step_up_auth", "analyst_info"]
    asked_after_step: int
    assumed_response: str


class NextBestActions(BaseModel):
    initial: List[ActionItem] = Field(default_factory=list)
    final: List[ActionItem] = Field(default_factory=list)
    what_changed: str


class SarSection(BaseModel):
    file: bool
    reason: str
    narrative: str
    subjects: List[str] = Field(default_factory=list)
    total_amount_usd: float
    activity_dates: List[str] = Field(default_factory=list)


class InvestigationResult(BaseModel):
    model_config = ConfigDict(extra="allow")
    case_id: str
    case: CaseSection
    evidence_requests: List[EvidenceRequest] = Field(default_factory=list)
    next_best_actions: NextBestActions
    sar: SarSection
    stop_reason: str
    tool_calls: int = 0
    tokens: int = 0
    latency_s: float = 0.0


def _safe_amount(value: Any) -> Optional[float]:
    try:
        if value in (None, ""):
            return None
        return abs(float(value))
    except (TypeError, ValueError):
        return None


def _known_txn_amounts(evidence: Dict[str, Any]) -> Dict[str, float]:
    amount_map: Dict[str, float] = {}
    for item in evidence.get("card_transactions", []):
        attrs = item.get("attributes", item)
        txn_id = item.get("v_id", attrs.get("transaction_id"))
        amount = _safe_amount(attrs.get("amount", attrs.get("TransactionAmt")))
        if txn_id and amount is not None:
            amount_map[str(txn_id)] = amount
    flagged = evidence.get("flagged_txn", {})
    flagged_attrs = flagged.get("attributes", flagged)
    flagged_id = flagged.get("v_id", flagged_attrs.get("transaction_id"))
    flagged_amt = _safe_amount(flagged_attrs.get("amount", flagged_attrs.get("TransactionAmt")))
    if flagged_id and flagged_amt is not None:
        amount_map[str(flagged_id)] = flagged_amt
    return amount_map


def _txn_dates(evidence: Dict[str, Any], txn_ids: List[str]) -> List[str]:
    dates: List[str] = []
    id_set = set(txn_ids)
    for item in evidence.get("card_transactions", []):
        attrs = item.get("attributes", item)
        txn_id = str(item.get("v_id", attrs.get("transaction_id", "")))
        if txn_id in id_set:
            ts = str(attrs.get("ts", ""))[:10]
            if ts and re.match(r"\d{4}-\d{2}-\d{2}", ts):
                dates.append(ts)
    flagged = evidence.get("flagged_txn", {})
    flagged_attrs = flagged.get("attributes", flagged)
    flagged_id = str(flagged.get("v_id", flagged_attrs.get("transaction_id", "")))
    if flagged_id in id_set:
        ts = str(flagged_attrs.get("ts", ""))[:10]
        if ts and re.match(r"\d{4}-\d{2}-\d{2}", ts):
            dates.append(ts)
    return sorted(set(dates))


def _evidence_id_sets(evidence: Dict[str, Any]) -> Dict[str, Set[str]]:
    txn_ids: Set[str] = set()
    card_ids: Set[str] = set()
    case_ids: Set[str] = set()

    for tx in evidence.get("card_transactions", []):
        v_id = tx.get("v_id")
        if v_id:
            txn_ids.add(str(v_id))
    flagged = evidence.get("flagged_txn", {})
    if flagged.get("v_id"):
        txn_ids.add(str(flagged["v_id"]))

    for card in evidence.get("device_neighbors", []):
        if card.get("v_id"):
            card_ids.add(str(card["v_id"]))
    for card in evidence.get("region_neighbor_cards", []):
        if card.get("v_id"):
            card_ids.add(str(card["v_id"]))
    for card in evidence.get("email_neighbor_cards", []):
        if card.get("v_id"):
            card_ids.add(str(card["v_id"]))
    for card in evidence.get("owner_cards", []):
        if card.get("v_id"):
            card_ids.add(str(card["v_id"]))

    for c in evidence.get("customer_prior_cases", evidence.get("prior_cases", [])):
        if c.get("v_id"):
            case_ids.add(str(c["v_id"]))
    for c in evidence.get("fraud_cases_on_device", []):
        if c.get("v_id"):
            case_ids.add(str(c["v_id"]))
    for c in evidence.get("memory_case_ids", []):
        case_ids.add(str(c))

    return {
        "txn_ids": txn_ids,
        "card_ids": card_ids,
        "case_ids": case_ids,
    }


def _owner_card_ids(evidence: Dict[str, Any], case_row: Dict[str, Any]) -> Set[str]:
    owned: Set[str] = set()
    for card in evidence.get("owner_cards", []):
        if card.get("v_id"):
            owned.add(str(card["v_id"]))
    card_id = str(case_row.get("card_id", ""))
    if card_id:
        owned.add(card_id)
        owned.add(f"EXT::{card_id}")
        owned.add(f"DRV::{card_id}")
    return owned


def _infer_connected_cards(
    evidence: Dict[str, Any],
    case_row: Dict[str, Any],
    valid_card_ids: Set[str],
) -> List[str]:
    owned = _owner_card_ids(evidence, case_row)
    candidates: List[str] = []

    for card in evidence.get("device_neighbors", []):
        vid = str(card.get("v_id", ""))
        if vid and vid in valid_card_ids and vid not in owned:
            candidates.append(vid)

    if evidence.get("fraud_cases_on_device"):
        for card in evidence.get("region_neighbor_cards", []):
            vid = str(card.get("v_id", ""))
            if vid and vid in valid_card_ids and vid not in owned:
                candidates.append(vid)
        for card in evidence.get("email_neighbor_cards", []):
            vid = str(card.get("v_id", ""))
            if vid and vid in valid_card_ids and vid not in owned:
                candidates.append(vid)

    seen: Set[str] = set()
    deduped: List[str] = []
    for cid in candidates:
        if cid not in seen:
            seen.add(cid)
            deduped.append(cid)
    return deduped[:10]


def _device_profile_string(evidence: Dict[str, Any]) -> str:
    device = evidence.get("device", {})
    if not device:
        return ""
    attrs = device.get("attributes", device)
    parts = [
        str(attrs.get("device_info", "")).strip(),
        str(attrs.get("os", "")).strip(),
        str(attrs.get("browser", "")).strip(),
        str(attrs.get("screen_size", attrs.get("screen", ""))).strip(),
    ]
    parts = [p for p in parts if p and p != "?"]
    return " | ".join(parts)


def _normalize_device_profiles(data: Dict[str, Any], evidence: Dict[str, Any]) -> None:
    canonical = _device_profile_string(evidence)
    if not canonical:
        data["case"]["connected_device_profiles"] = []
        return

    kept: List[str] = []
    canonical_lower = canonical.lower()
    for profile in data["case"]["connected_device_profiles"]:
        p = str(profile).strip()
        if not p:
            continue
        if p.lower() in canonical_lower or canonical_lower in p.lower():
            kept.append(p)
    if not kept:
        kept = [canonical]
    data["case"]["connected_device_profiles"] = kept[:3]


def _should_file_report(data: Dict[str, Any]) -> bool:
    case = data["case"]
    if case.get("verdict") != "fraud":
        return False
    exposure = float(case.get("exposure_usd") or 0)
    connected = case.get("connected_card_ids") or []
    pattern = case.get("pattern", "")
    return (
        exposure > FILE_REPORT_EXPOSURE_THRESHOLD
        or len(connected) > 0
        or pattern == "undocumented"
    )


def _block_card_route(exposure_usd: float) -> str:
    return "L2" if exposure_usd > 2500 else "L1"


def _action_in_list(actions: List[Dict[str, Any]], name: str) -> bool:
    return any(a.get("action") == name for a in actions)


def _ensure_action(
    actions: List[Dict[str, Any]],
    action: str,
    route: str,
    reason: str,
) -> None:
    if not _action_in_list(actions, action):
        actions.append({"action": action, "route": route, "reason": reason})


def _enforce_file_report_policy(
    data: Dict[str, Any],
    evidence: Dict[str, Any],
    case_row: Dict[str, Any],
) -> None:
    should_file = _should_file_report(data)
    final = data["next_best_actions"]["final"]
    sar = data["sar"]

    if should_file:
        sar["file"] = True
        _ensure_action(final, "FILE_REPORT", "L2", "R2/R6/R9: SAR required for this case exposure or shared device")
        if not sar.get("narrative"):
            sar["narrative"] = data["case"].get("summary", "")
        if not sar.get("subjects"):
            subjects = [str(case_row.get("customer_id", ""))] if case_row.get("customer_id") else []
            card_id = str(case_row.get("card_id", ""))
            if card_id:
                subjects.append(card_id)
            subjects.extend(data["case"].get("connected_card_ids", [])[:5])
            sar["subjects"] = list(dict.fromkeys(s for s in subjects if s))
        sar["total_amount_usd"] = data["case"].get("exposure_usd", 0)
        dates = _txn_dates(evidence, data["case"].get("affected_txn_ids", []))
        if len(dates) >= 2:
            sar["activity_dates"] = [dates[0], dates[-1]]
        elif len(dates) == 1:
            sar["activity_dates"] = [dates[0], dates[0]]
        if not sar.get("reason") or "not filed" in str(sar.get("reason", "")).lower():
            sar["reason"] = "R2/R6: confirmed fraud with exposure > $1,000, shared device, or coordinated pattern"
    else:
        sar["file"] = False
        data["next_best_actions"]["final"] = [
            a for a in final if a.get("action") != "FILE_REPORT"
        ]
        if "file_report" in str(sar.get("reason", "")).lower() and "not" not in str(sar.get("reason", "")).lower():
            sar["reason"] = (
                f"R2: No SAR — this case exposure ${data['case'].get('exposure_usd', 0):.2f} "
                f"is under ${FILE_REPORT_EXPOSURE_THRESHOLD:.0f} with no cross-card device link"
            )


def _normalize_sar(data: Dict[str, Any], evidence: Dict[str, Any], case_row: Dict[str, Any]) -> None:
    sar = data["sar"]
    if not sar.get("file"):
        sar["narrative"] = ""
        sar["subjects"] = []
        sar["total_amount_usd"] = 0.0
        sar["activity_dates"] = []
        reason = str(sar.get("reason", ""))
        if "file_report" in reason.lower() and "not" not in reason.lower() and "no sar" not in reason.lower():
            sar["reason"] = (
                f"R2: No SAR filed — exposure ${data['case'].get('exposure_usd', 0):.2f} "
                f"does not meet filing threshold for this case"
            )
        return

    final = data["next_best_actions"]["final"]
    if not _action_in_list(final, "FILE_REPORT"):
        _ensure_action(final, "FILE_REPORT", "L2", "R2: sar.file is true")

    if not sar.get("narrative"):
        sar["narrative"] = data["case"].get("summary", "")
    sar["total_amount_usd"] = data["case"].get("exposure_usd", 0)
    if not sar.get("subjects"):
        subjects = []
        if case_row.get("customer_id"):
            subjects.append(str(case_row["customer_id"]))
        if case_row.get("card_id"):
            subjects.append(str(case_row["card_id"]))
        sar["subjects"] = subjects
    dates = _txn_dates(evidence, data["case"].get("affected_txn_ids", []))
    if len(dates) >= 2:
        sar["activity_dates"] = [dates[0], dates[-1]]
    elif len(dates) == 1:
        sar["activity_dates"] = [dates[0], dates[0]]


def _normalize_status(data: Dict[str, Any]) -> None:
    verdict = data["case"]["verdict"]
    final_actions = {a["action"] for a in data["next_best_actions"]["final"]}
    has_pending = bool(data.get("evidence_requests"))

    if verdict == "legitimate":
        data["case"]["status"] = "closed_legitimate"
    elif verdict == "fraud":
        if has_pending and data["case"].get("status") == "open":
            data["case"]["status"] = "open"
        else:
            data["case"]["status"] = "closed_fraud"
    elif verdict == "uncertain":
        if "ESCALATE_TO_ANALYST" in final_actions:
            data["case"]["status"] = "escalated"
        elif has_pending:
            data["case"]["status"] = "open"
        else:
            data["case"]["status"] = "escalated"


def _guard_r1_initial_actions(data: Dict[str, Any], case_row: Dict[str, Any]) -> None:
    prob = float(data["case"].get("fraud_probability", 0))
    trigger = str(case_row.get("trigger_type", "")).lower()
    initial = data["next_best_actions"]["initial"]
    filtered: List[Dict[str, Any]] = []

    for action in initial:
        name = action.get("action", "")
        reason = str(action.get("reason", ""))
        cites_r1 = reason.strip().upper().startswith("R1") or "R1:" in reason.upper()
        if prob >= 0.70 and name in {"VERIFY_WITH_CUSTOMER", "STEP_UP_AUTH"} and cites_r1:
            continue
        if trigger == "customer_report" and name == "VERIFY_WITH_CUSTOMER" and cites_r1:
            action = dict(action)
            action["reason"] = "R2: customer disputed the transaction — verify before blocking"
        filtered.append(action)
    data["next_best_actions"]["initial"] = filtered


def _customer_denied(data: Dict[str, Any], case_row: Dict[str, Any]) -> bool:
    if str(case_row.get("trigger_type", "")).lower() == "customer_report":
        return True
    for req in data.get("evidence_requests", []):
        response = str(req.get("assumed_response", "")).lower()
        if any(
            phrase in response
            for phrase in (
                "did not make",
                "didn't make",
                "denied",
                "deny",
                "not authorize",
                "never made",
            )
        ):
            return True
    return False


def _ensure_r2_final_actions(data: Dict[str, Any], case_row: Dict[str, Any]) -> None:
    if data["case"]["verdict"] != "fraud":
        return

    final = data["next_best_actions"]["final"]
    exposure = float(data["case"].get("exposure_usd") or 0)
    route = _block_card_route(exposure)
    denied = _customer_denied(data, case_row) or str(case_row.get("trigger_type", "")).lower() == "customer_report"

    needs_block = denied or _action_in_list(final, "BLOCK_CARD") or _action_in_list(final, "FILE_REPORT")
    if needs_block:
        _ensure_action(final, "BLOCK_CARD", route, "R2: confirmed or suspected unauthorized use")
        _ensure_action(final, "CREATE_CASE", "auto", "R2: fraud investigation case opened")

    if _action_in_list(final, "FILE_REPORT") and len(data["case"].get("connected_card_ids", [])) > 0:
        _ensure_action(
            final,
            "MONITOR_CONNECTED_CARDS",
            "auto",
            "R6: shared device links other cards",
        )


def _validate_action_routes(actions: List[ActionItem]) -> None:
    for a in actions:
        allowed = ROUTE_BY_ACTION.get(a.action, set())
        if a.route not in allowed:
            raise ValueError(f"Invalid route '{a.route}' for action '{a.action}'")


def _fix_action_routes_in_payload(data: Dict[str, Any]) -> None:
    """Correct common LLM route mistakes before schema validation."""
    exposure = float(data.get("case", {}).get("exposure_usd") or 0)
    nba = data.get("next_best_actions")
    if not isinstance(nba, dict):
        return
    for key in ("initial", "final"):
        actions = nba.get(key)
        if not isinstance(actions, list):
            continue
        for action in actions:
            if not isinstance(action, dict):
                continue
            name = action.get("action", "")
            allowed = ROUTE_BY_ACTION.get(name, set())
            if name == "FILE_REPORT":
                action["route"] = "L2"
            elif name == "BLOCK_CARD":
                action["route"] = _block_card_route(exposure)
            elif name == "BLOCK_ALL_CARDS":
                action["route"] = "L2"
            elif name == "DECLINE_TRANSACTION":
                action["route"] = "L1"
            elif allowed and action.get("route") not in allowed:
                action["route"] = sorted(allowed)[0]


_VALID_EVIDENCE_SOURCES = frozenset({"graph", "document", "customer", "external"})

_SOURCE_ALIASES = {
    "internal": "graph",
    "system": "graph",
    "bank": "graph",
    "policy": "document",
    "regulatory": "document",
    "memory": "graph",
    "case_memory": "graph",
    "prior_case": "graph",
    "closed_case": "graph",
    "analyst": "external",
    "customer_report": "customer",
    "verification": "customer",
}


def _normalize_evidence_sources(data: Dict[str, Any]) -> None:
    case = data.get("case")
    if not isinstance(case, dict):
        return
    items = case.get("evidence")
    if not isinstance(items, list):
        return
    for item in items:
        if not isinstance(item, dict):
            continue
        raw = str(item.get("source", "graph")).strip().lower()
        if raw in _VALID_EVIDENCE_SOURCES:
            item["source"] = raw
        else:
            item["source"] = _SOURCE_ALIASES.get(raw, "graph")


def _coerce_id_strings(data: Dict[str, Any]) -> None:
    """LLMs often emit numeric transaction IDs; schema requires strings."""
    case = data.get("case")
    if not isinstance(case, dict):
        return

    def str_list(items: Any) -> List[str]:
        if not isinstance(items, list):
            return []
        out: List[str] = []
        for item in items:
            if item is None:
                continue
            out.append(str(item))
        return out

    case["affected_txn_ids"] = str_list(case.get("affected_txn_ids"))
    if case.get("first_suspicious_txn_id") not in (None, ""):
        case["first_suspicious_txn_id"] = str(case["first_suspicious_txn_id"])
    case["connected_card_ids"] = str_list(case.get("connected_card_ids"))
    case["connected_device_profiles"] = str_list(case.get("connected_device_profiles"))
    case["similar_prior_cases"] = str_list(case.get("similar_prior_cases"))

    evidence_items = case.get("evidence")
    if isinstance(evidence_items, list):
        for item in evidence_items:
            if isinstance(item, dict) and "entity_ids" in item:
                item["entity_ids"] = str_list(item.get("entity_ids"))

    sar = data.get("sar")
    if isinstance(sar, dict):
        sar["subjects"] = str_list(sar.get("subjects"))
        sar["activity_dates"] = str_list(sar.get("activity_dates"))


def repair_llm_payload(raw_result: Dict[str, Any]) -> Dict[str, Any]:
    """Fill required fields and fix routes on raw LLM JSON before Pydantic validation."""
    data: Dict[str, Any] = dict(raw_result)
    if "case" not in data or not isinstance(data["case"], dict):
        data["case"] = {}
    if "next_best_actions" not in data or not isinstance(data["next_best_actions"], dict):
        data["next_best_actions"] = {"initial": [], "final": [], "what_changed": "nothing"}
    else:
        nba = data["next_best_actions"]
        nba.setdefault("initial", [])
        nba.setdefault("final", [])
        nba.setdefault("what_changed", "nothing")
    if not isinstance(data.get("evidence_requests"), list):
        data["evidence_requests"] = []

    sar = data.get("sar")
    if not isinstance(sar, dict):
        sar = {}
    sar.setdefault("file", False)
    sar.setdefault("reason", "")
    sar.setdefault("narrative", "")
    sar.setdefault("subjects", [])
    sar.setdefault("total_amount_usd", 0.0)
    sar.setdefault("activity_dates", [])
    data["sar"] = sar

    if not data.get("stop_reason"):
        summary = str(data.get("case", {}).get("summary", "")).strip()
        data["stop_reason"] = summary[:240] if summary else "Investigation complete."

    data.setdefault("tool_calls", 0)
    data.setdefault("tokens", 0)
    data.setdefault("latency_s", 0.0)

    _coerce_id_strings(data)
    _normalize_evidence_sources(data)
    _fix_action_routes_in_payload(data)
    return data


def validate_and_normalize_result(
    raw_result: Dict[str, Any],
    case_row: Dict[str, Any],
    evidence: Dict[str, Any],
) -> Dict[str, Any]:
    raw_result = repair_llm_payload(raw_result)
    try:
        result = InvestigationResult.model_validate(raw_result)
    except ValidationError as exc:
        raise ValueError(f"LLM output failed schema validation: {exc}") from exc

    data = result.model_dump()
    data["case_id"] = str(case_row["case_id"])
    data["case"]["written_to_graph"] = False
    data["case"]["graph_case_id"] = ""

    _validate_action_routes(result.next_best_actions.initial)
    _validate_action_routes(result.next_best_actions.final)

    ids = _evidence_id_sets(evidence)
    known_amounts = _known_txn_amounts(evidence)

    affected = [str(t) for t in data["case"]["affected_txn_ids"] if str(t) in ids["txn_ids"]]
    data["case"]["affected_txn_ids"] = affected

    inferred_cards = _infer_connected_cards(evidence, case_row, ids["card_ids"])
    llm_cards = [str(c) for c in data["case"]["connected_card_ids"] if str(c) in ids["card_ids"]]
    merged_cards: List[str] = []
    seen_cards: Set[str] = set()
    for cid in llm_cards + inferred_cards:
        if cid not in seen_cards:
            seen_cards.add(cid)
            merged_cards.append(cid)
    data["case"]["connected_card_ids"] = merged_cards[:10]

    _normalize_device_profiles(data, evidence)

    if not data["case"]["similar_prior_cases"]:
        memory_ids = [str(c) for c in evidence.get("memory_case_ids", []) if str(c) in ids["case_ids"]]
        if memory_ids:
            data["case"]["similar_prior_cases"] = memory_ids[:5]
        else:
            data["case"]["similar_prior_cases"] = sorted(ids["case_ids"])[:5]
    else:
        data["case"]["similar_prior_cases"] = [
            str(c) for c in data["case"]["similar_prior_cases"] if str(c) in ids["case_ids"]
        ]

    if affected:
        recomputed = round(sum(known_amounts.get(t, 0.0) for t in affected), 2)
        if recomputed > 0:
            data["case"]["exposure_usd"] = recomputed
    else:
        data["case"]["first_suspicious_txn_id"] = ""

    if data["case"]["verdict"] == "legitimate":
        data["case"]["affected_txn_ids"] = []
        data["case"]["exposure_usd"] = 0.0
        data["case"]["connected_card_ids"] = []
        data["case"]["connected_device_profiles"] = []
        data["sar"]["file"] = False
        data["sar"]["narrative"] = ""
        data["sar"]["subjects"] = []
        data["sar"]["total_amount_usd"] = 0.0
        data["sar"]["activity_dates"] = []

    _guard_r1_initial_actions(data, case_row)
    _enforce_file_report_policy(data, evidence, case_row)
    _ensure_r2_final_actions(data, case_row)
    _normalize_sar(data, evidence, case_row)
    _normalize_status(data)

    return data
