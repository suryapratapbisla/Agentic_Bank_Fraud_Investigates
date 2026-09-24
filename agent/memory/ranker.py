from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, List, Optional

from memory.models import GraphMemoryHit, MemoryHit, SemanticMemoryHit


def _parse_ts(value: str) -> Optional[datetime]:
    if not value:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(value[:19], fmt)
        except ValueError:
            continue
    return None


def recency_score(closed_at: str, reference: Optional[datetime] = None) -> float:
    ref = reference or datetime.now(timezone.utc).replace(tzinfo=None)
    if reference and reference.tzinfo:
        ref = reference.replace(tzinfo=None)
    ts = _parse_ts(closed_at)
    if not ts:
        return 0.3
    days = max(0, (ref - ts).days)
    if days <= 30:
        return 1.0
    if days <= 90:
        return 0.8
    if days <= 180:
        return 0.6
    if days <= 365:
        return 0.4
    return 0.2


def merge_and_rank(
    graph_hits: List[GraphMemoryHit],
    semantic_hits: List[SemanticMemoryHit],
    *,
    top_k: int = 5,
    reference: Optional[datetime] = None,
) -> List[MemoryHit]:
    merged: Dict[str, MemoryHit] = {}

    for gh in graph_hits:
        merged[gh.case_id] = MemoryHit(
            case_id=gh.case_id,
            match_reasons=list(gh.match_reasons),
            graph_score=gh.graph_score,
            semantic_score=0.0,
            recency_score=recency_score(gh.closed_at, reference),
            outcome_bonus=0.15 if gh.outcome == "confirmed_fraud" else 0.0,
            final_score=0.0,
            outcome=gh.outcome,
            pattern=gh.pattern,
            closed_at=gh.closed_at,
        )

    for sh in semantic_hits:
        hit = merged.get(sh.case_id)
        if hit:
            hit.semantic_score = sh.cosine_score
            if "semantic_match" not in hit.match_reasons:
                hit.match_reasons.append("semantic_match")
        else:
            merged[sh.case_id] = MemoryHit(
                case_id=sh.case_id,
                match_reasons=["semantic_match"],
                graph_score=0.0,
                semantic_score=sh.cosine_score,
                recency_score=recency_score(sh.closed_at, reference),
                outcome_bonus=0.15 if sh.outcome == "confirmed_fraud" else 0.0,
                final_score=0.0,
                outcome=sh.outcome,
                closed_at=sh.closed_at,
                investigation_summary=sh.snippet,
            )

    ranked: List[MemoryHit] = []
    for hit in merged.values():
        hit.final_score = (
            min(hit.graph_score, 1.0) * 0.45
            + hit.semantic_score * 0.35
            + hit.recency_score * 0.15
            + hit.outcome_bonus
        )
        ranked.append(hit)

    ranked.sort(key=lambda h: h.final_score, reverse=True)
    return ranked[:top_k]
