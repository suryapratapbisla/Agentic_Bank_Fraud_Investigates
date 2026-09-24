from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict

from memory.document_builder import from_investigation_result
from memory.vector_store import write_case_memory_document


def write_case_memory(
    conn,
    investigation: Dict[str, Any],
    case_row: Dict[str, Any],
    evidence: Dict[str, Any],
    *,
    graph_case_id: str = "",
) -> bool:
    doc = from_investigation_result(investigation, case_row, evidence)
    if not doc.closed_at:
        doc.closed_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    closed_id = graph_case_id or doc.case_id
    return write_case_memory_document(conn, doc, closed_case_id=closed_id)
