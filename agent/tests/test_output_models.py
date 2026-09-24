from __future__ import annotations

import json
from pathlib import Path

import pytest

from output_models import validate_and_normalize_result


FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures"


def _load_evidence():
    with (FIXTURE_DIR / "evidence_bundle.json").open("r", encoding="utf-8") as f:
        return json.load(f)


def _base_case_row():
    return {
        "case_id": "HHG-001",
        "opened_at": "2016-12-05 01:55:28",
        "trigger_type": "risk_score",
        "trigger_text": "Test trigger",
        "flagged_txn_id": "3514030",
        "card_id": "C12382-K1",
        "customer_id": "C12382",
        "risk_score": 0.61,
    }


def _base_result():
    return {
        "case_id": "HHG-001",
        "case": {
            "status": "closed_fraud",
            "verdict": "fraud",
            "fraud_probability": 0.82,
            "pattern": "card_not_present_new_device",
            "pattern_description": "",
            "affected_txn_ids": ["3514030", "DOES_NOT_EXIST"],
            "first_suspicious_txn_id": "3514030",
            "connected_card_ids": ["DRV::C00001::9999::::::visa::226::debit", "bad-id"],
            "connected_device_profiles": ["DeviceA"],
            "exposure_usd": 999999,
            "evidence": [
                {
                    "claim": "test",
                    "source": "graph",
                    "ref": "query:get_evidence_bundle",
                    "entity_ids": ["3514030"],
                }
            ],
            "similar_prior_cases": [],
            "summary": "Fraud summary for SAR.",
            "written_to_graph": False,
            "graph_case_id": "",
        },
        "evidence_requests": [],
        "next_best_actions": {
            "initial": [{"action": "VERIFY_WITH_CUSTOMER", "route": "auto", "reason": "R1: low probability"}],
            "final": [{"action": "FILE_REPORT", "route": "L2", "reason": "R2"}],
            "what_changed": "customer denied",
        },
        "sar": {
            "file": True,
            "reason": "R2",
            "narrative": "narrative",
            "subjects": ["C12382"],
            "total_amount_usd": 10.0,
            "activity_dates": ["2016-12-05", "2016-12-05"],
        },
        "stop_reason": "done",
        "tool_calls": 0,
        "tokens": 0,
        "latency_s": 0.0,
    }


def test_validate_and_normalize_filters_unknown_ids_and_recomputes_exposure():
    data = validate_and_normalize_result(_base_result(), _base_case_row(), _load_evidence())

    assert data["case"]["affected_txn_ids"] == ["3514030"]
    assert "DRV::C00001::9999::::::visa::226::debit" in data["case"]["connected_card_ids"]
    assert data["case"]["similar_prior_cases"] == ["CC-0003", "CC-0099"]
    assert data["case"]["exposure_usd"] == 77.07
    assert data["case"]["status"] == "closed_fraud"
    assert "FILE_REPORT" in {a["action"] for a in data["next_best_actions"]["final"]}
    assert data["sar"]["file"] is True


def test_legitimate_verdict_forces_zero_exposure_and_no_sar():
    result = _base_result()
    result["case"]["verdict"] = "legitimate"
    result["case"]["status"] = "closed_legitimate"
    result["sar"]["file"] = True
    result["next_best_actions"]["final"] = [
        {"action": "CLOSE_NO_FRAUD", "route": "auto", "reason": "R3"}
    ]

    data = validate_and_normalize_result(result, _base_case_row(), _load_evidence())
    assert data["case"]["affected_txn_ids"] == []
    assert data["case"]["exposure_usd"] == 0.0
    assert data["sar"]["file"] is False
    assert data["sar"]["narrative"] == ""


def test_internal_evidence_source_maps_to_graph():
    result = _base_result()
    result["case"]["evidence"].append(
        {
            "claim": "Internal note",
            "source": "internal",
            "ref": "policy:R2",
            "entity_ids": [],
        }
    )
    data = validate_and_normalize_result(result, _base_case_row(), _load_evidence())
    assert data["case"]["evidence"][-1]["source"] == "graph"


def test_coerce_numeric_txn_ids_to_strings():
    result = _base_result()
    result["case"]["affected_txn_ids"] = [3514030]
    result["case"]["evidence"][0]["entity_ids"] = [3514030]
    data = validate_and_normalize_result(result, _base_case_row(), _load_evidence())
    assert data["case"]["affected_txn_ids"] == ["3514030"]


def test_file_report_auto_route_is_corrected_to_l2():
    result = _base_result()
    result["next_best_actions"]["final"] = [
        {"action": "FILE_REPORT", "route": "auto", "reason": "R2: exposure over threshold"},
    ]
    data = validate_and_normalize_result(result, _base_case_row(), _load_evidence())
    file_report = [
        a for a in data["next_best_actions"]["final"] if a["action"] == "FILE_REPORT"
    ]
    assert file_report and file_report[0]["route"] == "L2"


def test_missing_sar_and_stop_reason_are_repaired():
    result = _base_result()
    del result["sar"]
    del result["stop_reason"]
    data = validate_and_normalize_result(result, _base_case_row(), _load_evidence())
    assert "file" in data["sar"]
    assert data["stop_reason"]


def test_sar_file_false_clears_narrative_and_subjects():
    result = _base_result()
    result["case"]["connected_card_ids"] = []
    result["case"]["pattern"] = "card_not_present_fraud"
    result["case"]["exposure_usd"] = 292.36
    result["next_best_actions"]["final"] = [
        {"action": "BLOCK_CARD", "route": "L1", "reason": "R2"},
        {"action": "CREATE_CASE", "route": "auto", "reason": "R2"},
    ]
    result["sar"] = {
        "file": False,
        "reason": "FILE_REPORT is required due to prior cases",
        "narrative": "Should be cleared",
        "subjects": ["C11891"],
        "total_amount_usd": 292.36,
        "activity_dates": ["2016-11-22", "2016-11-22"],
    }

    evidence = _load_evidence()
    evidence["device_neighbors"] = []
    evidence["region_neighbor_cards"] = []
    evidence["email_neighbor_cards"] = []
    evidence["fraud_cases_on_device"] = []

    data = validate_and_normalize_result(result, _base_case_row(), evidence)
    assert data["sar"]["file"] is False
    assert data["sar"]["narrative"] == ""
    assert data["sar"]["subjects"] == []
    assert data["sar"]["total_amount_usd"] == 0.0
    assert "FILE_REPORT" not in {a["action"] for a in data["next_best_actions"]["final"]}


def test_high_exposure_triggers_file_report():
    result = _base_result()
    result["case"]["connected_card_ids"] = []
    result["case"]["exposure_usd"] = 1000.03
    result["case"]["affected_txn_ids"] = ["3514030"]
    result["next_best_actions"]["final"] = [
        {"action": "BLOCK_CARD", "route": "L2", "reason": "R2"},
    ]
    result["sar"]["file"] = False
    result["sar"]["narrative"] = ""

    data = validate_and_normalize_result(result, _base_case_row(), _load_evidence())
    assert data["sar"]["file"] is True
    assert "FILE_REPORT" in {a["action"] for a in data["next_best_actions"]["final"]}
    assert data["sar"]["narrative"]


def test_device_neighbors_infer_connected_cards():
    result = _base_result()
    result["case"]["connected_card_ids"] = []
    result["next_best_actions"]["final"] = [
        {"action": "BLOCK_CARD", "route": "L1", "reason": "R2"},
        {"action": "CREATE_CASE", "route": "auto", "reason": "R2"},
    ]
    result["sar"]["file"] = False

    data = validate_and_normalize_result(result, _base_case_row(), _load_evidence())
    assert "DRV::C00001::9999::::::visa::226::debit" in data["case"]["connected_card_ids"]


def test_r1_stripped_when_probability_high():
    result = _base_result()
    result["case"]["fraud_probability"] = 0.85
    result["next_best_actions"]["initial"] = [
        {"action": "VERIFY_WITH_CUSTOMER", "route": "auto", "reason": "R1: probability < 0.70"},
    ]

    data = validate_and_normalize_result(result, _base_case_row(), _load_evidence())
    initial_actions = [a["action"] for a in data["next_best_actions"]["initial"]]
    assert "VERIFY_WITH_CUSTOMER" not in initial_actions


def test_fraud_verdict_sets_closed_fraud_status():
    result = _base_result()
    result["case"]["status"] = "open"

    data = validate_and_normalize_result(result, _base_case_row(), _load_evidence())
    assert data["case"]["status"] == "closed_fraud"


def test_r2_final_includes_block_and_create_when_only_file_report():
    result = _base_result()
    result["case"]["exposure_usd"] = 1000.03
    result["next_best_actions"]["final"] = [
        {"action": "FILE_REPORT", "route": "L2", "reason": "R2: exposure over threshold"},
    ]
    result["evidence_requests"] = [
        {
            "type": "customer_validation",
            "asked_after_step": 1,
            "assumed_response": "Customer states they did not make this purchase.",
        }
    ]

    data = validate_and_normalize_result(result, _base_case_row(), _load_evidence())
    final = {a["action"] for a in data["next_best_actions"]["final"]}
    assert "BLOCK_CARD" in final
    assert "CREATE_CASE" in final
    assert "FILE_REPORT" in final
