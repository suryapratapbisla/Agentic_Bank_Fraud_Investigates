from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class SarSummary:
    file: bool
    reason: str
    narrative: str


@dataclass
class GraphFeatures:
    customer_id: str = ""
    card_ids: List[str] = field(default_factory=list)
    device_hashes: List[str] = field(default_factory=list)
    regions: List[str] = field(default_factory=list)
    pattern: str = ""
    channel: str = ""
    outcome: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "customer_id": self.customer_id,
            "card_ids": self.card_ids,
            "device_hashes": self.device_hashes,
            "regions": self.regions,
            "pattern": self.pattern,
            "channel": self.channel,
            "outcome": self.outcome,
        }


@dataclass
class CaseMemoryDocument:
    case_id: str
    customer_summary: str
    fraud_type: str
    risk_factors: List[str]
    investigation_summary: str
    evidence: List[str]
    outcome: str
    sar: Optional[SarSummary]
    analyst_notes: str
    graph_features: GraphFeatures
    closed_at: str
    embedding_text: str = ""

    def to_vertex_attrs(self) -> Dict[str, Any]:
        return {
            "customer_id": self.graph_features.customer_id,
            "outcome": self.outcome,
            "pattern": self.fraud_type,
            "closed_at": self.closed_at,
            "investigation_summary": self.investigation_summary,
            "analyst_notes": self.analyst_notes,
            "risk_factors": "|".join(self.risk_factors),
            "graph_features_json": _json_dumps(self.graph_features.to_dict()),
        }


@dataclass
class GraphMemoryHit:
    case_id: str
    match_reasons: List[str]
    graph_score: float
    source_query: str
    closed_at: str = ""
    outcome: str = ""
    pattern: str = ""


@dataclass
class SemanticMemoryHit:
    case_id: str
    cosine_score: float
    snippet: str
    closed_at: str = ""
    outcome: str = ""


@dataclass
class MemoryHit:
    case_id: str
    match_reasons: List[str]
    graph_score: float
    semantic_score: float
    recency_score: float
    outcome_bonus: float
    final_score: float
    outcome: str = ""
    pattern: str = ""
    closed_at: str = ""
    investigation_summary: str = ""
    analyst_notes: str = ""
    evidence: List[str] = field(default_factory=list)
    exposure_usd: Optional[float] = None


@dataclass
class RetrievalResult:
    ranked_hits: List[MemoryHit]
    context_markdown: str
    graph_hit_count: int
    semantic_hit_count: int


def _json_dumps(data: Dict[str, Any]) -> str:
    import json

    return json.dumps(data, separators=(",", ":"))
