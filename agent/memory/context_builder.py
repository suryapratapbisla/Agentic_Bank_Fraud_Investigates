from __future__ import annotations

from typing import List

from memory.models import MemoryHit


def build_memory_context_section(hits: List[MemoryHit], *, max_cases: int = 5) -> str:
    if not hits:
        return (
            "## Relevant Previous Investigations\n\n"
            "No similar prior investigations were retrieved from case memory."
        )

    lines = ["## Relevant Previous Investigations", ""]
    for idx, hit in enumerate(hits[:max_cases], start=1):
        reasons = ", ".join(hit.match_reasons) if hit.match_reasons else "related"
        outcome = hit.outcome or "unknown"
        summary = hit.investigation_summary or hit.analyst_notes or "No summary available."
        key_evidence = summary[:220].strip()
        if len(summary) > 220:
            key_evidence += "..."

        lines.extend(
            [
                f"### {idx}. {hit.case_id} — {outcome} (confidence: {hit.final_score:.2f})",
                f"**Why relevant:** {reasons}",
                f"**Outcome:** {outcome.replace('_', ' ')}; pattern {hit.pattern or 'n/a'}",
                f"**Key evidence:** {key_evidence}",
                "",
                "---",
                "",
            ]
        )
    return "\n".join(lines).rstrip()


def memory_case_ids(hits: List[MemoryHit]) -> List[str]:
    return [h.case_id for h in hits]
