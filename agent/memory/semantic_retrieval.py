from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

from openai import OpenAI

from memory.models import SemanticMemoryHit


def _embedding_client() -> OpenAI:
    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY required for semantic memory retrieval")
    return OpenAI(api_key=api_key)


def build_query_text(case_row: Dict[str, Any], evidence: Dict[str, Any]) -> str:
    flagged = evidence.get("flagged_txn", {})
    attrs = flagged.get("attributes", flagged)
    parts = [
        str(case_row.get("trigger_text", "")),
        f"Channel {attrs.get('channel', '')}",
        f"Amount {attrs.get('amount', '')}",
        f"Billing region {attrs.get('addr1', '')}",
        f"Risk score {case_row.get('risk_score', attrs.get('risk_score', ''))}",
    ]
    prior_key = "customer_prior_cases" if evidence.get("customer_prior_cases") is not None else "prior_cases"
    prior_patterns = [
        (pc.get("attributes") or pc).get("pattern", "")
        for pc in (evidence.get(prior_key) or evidence.get("prior_cases") or [])[:3]
    ]
    if prior_patterns:
        parts.append("Prior customer patterns: " + ", ".join(str(p) for p in prior_patterns if p))
    return ". ".join(p for p in parts if p and str(p).strip())


def embed_text(text: str, *, model: Optional[str] = None) -> List[float]:
    client = _embedding_client()
    model_name = model or os.environ.get("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")
    response = client.embeddings.create(input=text, model=model_name)
    return list(response.data[0].embedding)


def search_semantic_memory(
    conn,
    case_row: Dict[str, Any],
    evidence: Dict[str, Any],
    *,
    top_k: int = 10,
) -> List[SemanticMemoryHit]:
    if conn is None:
        return []

    query_text = build_query_text(case_row, evidence)
    try:
        query_vec = embed_text(query_text)
    except Exception as exc:
        print(f"[memory] embedding error: {exc}")
        return []

    try:
        raw = conn.runInstalledQuery(
            "search_case_memory",
            {"query_vec": query_vec, "top_k": top_k},
        )
    except Exception as exc:
        print(f"[memory] search_case_memory error: {exc}")
        return []

    payload = raw[0] if isinstance(raw, list) and raw else raw
    if not isinstance(payload, dict):
        return []

    vertices = payload.get("results") or payload.get("Result") or []
    distances = payload.get("distances") or {}

    hits: List[SemanticMemoryHit] = []
    for vertex in vertices:
        if not isinstance(vertex, dict):
            continue
        v_id = str(vertex.get("v_id", ""))
        attrs = vertex.get("attributes", vertex)
        dist = _lookup_distance(distances, v_id, vertex)
        cosine = max(0.0, 1.0 - float(dist)) if dist is not None else 0.5
        snippet = str(attrs.get("investigation_summary") or attrs.get("analyst_notes") or "")[:200]
        hits.append(
            SemanticMemoryHit(
                case_id=v_id,
                cosine_score=cosine,
                snippet=snippet,
                closed_at=str(attrs.get("closed_at", "")),
                outcome=str(attrs.get("outcome", "")),
            )
        )
    return hits


def _lookup_distance(
    distances: Any,
    v_id: str,
    vertex: Dict[str, Any],
) -> Optional[float]:
    if isinstance(distances, dict):
        if v_id in distances:
            return float(distances[v_id])
        for key, val in distances.items():
            if str(key) == v_id:
                return float(val)
    return None
