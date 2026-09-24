from __future__ import annotations

import json
from pathlib import Path

import pytest

from memory.context_builder import build_memory_context_section
from memory.document_builder import from_closed_case_row
from memory.graph_retrieval import infer_pattern, retrieve_graph_memory
from memory.models import GraphMemoryHit, MemoryHit, SemanticMemoryHit
from memory.ranker import merge_and_rank


FIXTURES = Path(__file__).resolve().parent / "fixtures"
HHG_EVIDENCE = json.loads((FIXTURES / "evidence_bundle.json").read_text(encoding="utf-8"))


def test_from_closed_case_row_builds_embedding_text():
    row = {
        "case_id": "CC-3587",
        "customer_id": "C12382",
        "card_id": "C12382-K1",
        "outcome": "confirmed_fraud",
        "pattern": "out_of_region_use",
        "closed_at": "2016-09-21 01:08:08",
        "exposure_usd": 49.09,
        "n_txns": 1,
        "report_filed": "No",
        "analyst_notes": "Card-present use in a billing region the cardholder had no history in.",
    }
    doc = from_closed_case_row(row)
    assert doc.case_id == "CC-3587"
    assert "out_of_region_use" in doc.risk_factors
    assert doc.embedding_text
    assert "billing region" in doc.embedding_text.lower()


def test_infer_pattern_hhg001_style():
    case_row = {
        "trigger_text": "Real-time model scored transaction in billing region 444.0",
        "flagged_txn_id": "3514030",
    }
    evidence = {
        "flagged_txn": {
            "attributes": {"channel": "in_person", "addr1": "444.0"},
        }
    }
    assert infer_pattern(case_row, evidence) == "out_of_region_use"


def test_merge_and_rank_dedupes_and_orders():
    graph_hits = [
        GraphMemoryHit(
            case_id="CC-3587",
            match_reasons=["same_customer", "same_pattern"],
            graph_score=0.8,
            source_query="test",
            closed_at="2016-09-21 01:08:08",
            outcome="confirmed_fraud",
            pattern="out_of_region_use",
        ),
        GraphMemoryHit(
            case_id="CC-0041",
            match_reasons=["same_pattern"],
            graph_score=0.4,
            source_query="test",
            closed_at="2016-07-05 03:43:21",
            outcome="confirmed_fraud",
            pattern="out_of_region_use",
        ),
    ]
    semantic_hits = [
        SemanticMemoryHit(
            case_id="CC-3587",
            cosine_score=0.92,
            snippet="Out of region card-present fraud",
            outcome="confirmed_fraud",
        )
    ]
    ranked = merge_and_rank(graph_hits, semantic_hits, top_k=3)
    assert len(ranked) == 2
    assert ranked[0].case_id == "CC-3587"
    assert "semantic_match" in ranked[0].match_reasons
    assert ranked[0].final_score >= ranked[1].final_score


def test_build_memory_context_section_format():
    hits = [
        MemoryHit(
            case_id="CC-3587",
            match_reasons=["same_customer", "same_pattern"],
            graph_score=0.8,
            semantic_score=0.5,
            recency_score=0.6,
            outcome_bonus=0.15,
            final_score=0.87,
            outcome="confirmed_fraud",
            pattern="out_of_region_use",
            investigation_summary="Card-present fraud in unfamiliar billing region.",
        )
    ]
    section = build_memory_context_section(hits)
    assert "## Relevant Previous Investigations" in section
    assert "CC-3587" in section
    assert "Why relevant" in section
    assert "Key evidence" in section


def test_graph_retrieval_uses_evidence_prior_cases_without_conn():
    case_row = {"customer_id": "C12382", "flagged_txn_id": "3514030", "card_id": "C12382-K1"}
    evidence = dict(HHG_EVIDENCE)
    evidence["customer_prior_cases"] = evidence.get("prior_cases", [])
    hits = retrieve_graph_memory(None, case_row, evidence)
    ids = {h.case_id for h in hits}
    assert "CC-0003" in ids
