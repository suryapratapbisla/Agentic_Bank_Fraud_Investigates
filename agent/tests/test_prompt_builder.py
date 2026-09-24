from __future__ import annotations

import json
from pathlib import Path

from agent import build_investigation_prompt


FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures"


def test_prompt_includes_core_evidence_sections():
    with (FIXTURE_DIR / "evidence_bundle.json").open("r", encoding="utf-8") as f:
        evidence = json.load(f)

    case_row = {
        "case_id": "HHG-001",
        "opened_at": "2016-12-05 01:55:28",
        "trigger_type": "risk_score",
        "trigger_text": "Model alert",
        "flagged_txn_id": "3514030",
        "card_id": "C12382-K1",
        "customer_id": "C12382",
        "risk_score": 0.61,
    }

    prompt = build_investigation_prompt(case_row, evidence)

    assert "CASE TO INVESTIGATE" in prompt
    assert "FLAGGED TRANSACTION DETAILS" in prompt
    assert "CARD TRANSACTION HISTORY" in prompt
    assert "OTHER CARDS ON SAME DEVICE" in prompt
    assert "CARDS SHARING FLAGGED REGION" in prompt
    assert "CARDS SHARING FLAGGED PURCHASER EMAIL DOMAIN" in prompt
    assert "Output ONLY valid JSON" in prompt
