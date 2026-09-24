from __future__ import annotations

from typing import Any, Dict, List, Optional

from memory.context_builder import build_memory_context_section
from memory.graph_retrieval import retrieve_graph_memory
from memory.models import MemoryHit, RetrievalResult
from memory.ranker import merge_and_rank
from memory.semantic_retrieval import search_semantic_memory
from memory.vector_store import fetch_case_memory, fetch_closed_case_vertex


def _vertex_attrs(vertex: Dict[str, Any]) -> Dict[str, Any]:
    return vertex.get("attributes", vertex)


def _apply_vertex_fields(hit: MemoryHit, attrs: Dict[str, Any]) -> None:
    notes = str(attrs.get("analyst_notes", "") or attrs.get("investigation_summary", ""))
    if notes and not hit.investigation_summary:
        hit.investigation_summary = notes[:500]
    if notes and not hit.analyst_notes:
        hit.analyst_notes = notes[:300]
    hit.outcome = hit.outcome or str(attrs.get("outcome", ""))
    hit.pattern = hit.pattern or str(attrs.get("pattern", ""))
    hit.closed_at = hit.closed_at or str(attrs.get("closed_at", ""))


def _enrich_hits(conn, hits: List[MemoryHit]) -> List[MemoryHit]:
    if conn is None:
        return hits
    for hit in hits:
        if hit.investigation_summary and hit.analyst_notes:
            continue
        memory_vertex = fetch_case_memory(conn, hit.case_id)
        if memory_vertex:
            _apply_vertex_fields(hit, _vertex_attrs(memory_vertex))
            continue
        closed_vertex = fetch_closed_case_vertex(conn, hit.case_id)
        if closed_vertex:
            _apply_vertex_fields(hit, _vertex_attrs(closed_vertex))
    return hits


def retrieve_case_memory(
    conn,
    case_row: Dict[str, Any],
    evidence: Dict[str, Any],
    *,
    top_k: int = 5,
) -> RetrievalResult:
    graph_hits = retrieve_graph_memory(conn, case_row, evidence)
    semantic_hits = search_semantic_memory(conn, case_row, evidence, top_k=10)
    ranked = merge_and_rank(graph_hits, semantic_hits, top_k=top_k)
    ranked = _enrich_hits(conn, ranked)
    context = build_memory_context_section(ranked)
    return RetrievalResult(
        ranked_hits=ranked,
        context_markdown=context,
        graph_hit_count=len(graph_hits),
        semantic_hit_count=len(semantic_hits),
    )
