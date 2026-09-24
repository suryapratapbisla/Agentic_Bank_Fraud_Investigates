from __future__ import annotations

from typing import Any, Dict, List, Optional

from memory.document_builder import build_embedding_text
from memory.models import CaseMemoryDocument


def upsert_case_memory_vertex(conn, doc: CaseMemoryDocument) -> None:
    attrs = doc.to_vertex_attrs()
    conn.upsertVertex("CaseMemory", doc.case_id, attrs)


def upsert_case_memory_vector(
    conn,
    case_id: str,
    vector: List[float],
) -> None:
    conn.upsertVertex(
        "CaseMemory",
        case_id,
        {"summary_embedding": vector},
    )


def link_memory_to_closed_case(conn, case_id: str, closed_case_id: str) -> None:
    try:
        conn.upsertEdge("CaseMemory", case_id, "MEMORY_OF", "ClosedCase", closed_case_id)
    except Exception as exc:
        print(f"[memory] MEMORY_OF edge error: {exc}")


def write_case_memory_document(
    conn,
    doc: CaseMemoryDocument,
    *,
    closed_case_id: Optional[str] = None,
    embed_fn=None,
) -> bool:
    if conn is None:
        return False
    try:
        upsert_case_memory_vertex(conn, doc)
        if embed_fn is None:
            from memory.semantic_retrieval import embed_text

            embed_fn = embed_text
        vector = embed_fn(doc.embedding_text or build_embedding_text(doc))
        upsert_case_memory_vector(conn, doc.case_id, vector)
        if closed_case_id:
            link_memory_to_closed_case(conn, doc.case_id, closed_case_id)
        return True
    except Exception as exc:
        print(f"[memory] write_case_memory_document error: {exc}")
        return False


def fetch_case_memory(conn, case_id: str) -> Optional[Dict[str, Any]]:
    try:
        raw = conn.runInstalledQuery("get_case_memory", {"case_id": case_id})
        payload = raw[0] if isinstance(raw, list) and raw else raw
        memories = (payload or {}).get("memories") or []
        if memories:
            return memories[0]
    except Exception as exc:
        msg = str(exc).lower()
        if "not valid casememory" in msg:
            return None
        print(f"[memory] get_case_memory error: {exc}")
    return None


def fetch_closed_case_vertex(conn, case_id: str) -> Optional[Dict[str, Any]]:
    """Fallback when graph retrieval returns ClosedCase ids without CaseMemory vertices."""
    try:
        raw = conn.runInstalledQuery("get_closed_case", {"case_id": case_id})
        payload = raw[0] if isinstance(raw, list) and raw else raw
        cases = (payload or {}).get("cases") or []
        if cases:
            return cases[0]
    except Exception as exc:
        print(f"[memory] get_closed_case error: {exc}")
    return None
