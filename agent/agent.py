"""
Fraud Investigation Agent

Run from repo root:
    python agent/agent.py --case-id HHG-001
or:
    python  agent/agent.py --all-cases

Requirements:
    pip install -r agent/requirements.txt

Environment:
    See agent/.env.example
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, Optional

import pandas as pd
from dotenv import load_dotenv
from openai import OpenAI

from graph_queries import gather_all_evidence, get_conn, write_case_to_graph
from memory.pipeline import retrieve_case_memory
from memory.write_back import write_case_memory
from llm_json import loads_llm_json, salvage_json_from_api_error
from output_models import InvestigationResult, validate_and_normalize_result
from prompts import OUTPUT_SCHEMA, SYSTEM_PROMPT

AGENT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = AGENT_DIR.parent
DEFAULT_CASE_PACK = PROJECT_ROOT / "DATA" / "filtered_data" / "case_pack.csv"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "cases"

load_dotenv(AGENT_DIR / ".env")
load_dotenv(PROJECT_ROOT / ".env")


def get_llm_provider() -> str:
    return os.environ.get("LLM_PROVIDER", "openai").strip().lower()


def resolve_default_model() -> str:
    if get_llm_provider() == "groq":
        return os.environ.get("GROQ_MODEL", "openai/gpt-oss-120b")
    return os.environ.get("OPENAI_MODEL", "gpt-4o")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run fraud-investigation agent cases.")
    parser.add_argument(
        "--case-pack",
        default=os.environ.get("AGENT_CASE_PACK_PATH", str(DEFAULT_CASE_PACK)),
        help="Path to case_pack.csv (defaults to DATA/filtered_data/case_pack.csv).",
    )
    parser.add_argument(
        "--output-dir",
        default=os.environ.get("AGENT_OUTPUT_DIR", str(DEFAULT_OUTPUT_DIR)),
        help="Directory to write <case_id>.json outputs.",
    )
    parser.add_argument(
        "--model",
        default=os.environ.get("AGENT_MODEL") or resolve_default_model(),
        help="LLM model name (Groq or OpenAI depending on LLM_PROVIDER).",
    )
    parser.add_argument("--case-id", help="Run one case_id from case_pack.csv.")
    parser.add_argument(
        "--all-cases",
        action="store_true",
        help="Run all cases from case_pack.csv.",
    )
    parser.add_argument(
        "--max-cases",
        type=int,
        default=None,
        help="Optional cap on number of cases processed.",
    )
    parser.add_argument(
        "--dry-run-evidence",
        default=None,
        help="Path to JSON fixture used as evidence for every case (no graph reads).",
    )
    parser.add_argument(
        "--skip-graph-write",
        action="store_true",
        help="Do not write generated case results back to TigerGraph.",
    )
    parser.add_argument(
        "--sleep-seconds",
        type=float,
        default=0.5,
        help="Delay between cases to reduce API bursts (default 0.5).",
    )
    return parser.parse_args()


def require_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def build_client() -> OpenAI:
    provider = get_llm_provider()
    if provider == "groq":
        return OpenAI(
            api_key=require_env("GROQ_API_KEY"),
            base_url="https://api.groq.com/openai/v1",
        )
    return OpenAI(api_key=require_env("OPENAI_API_KEY"))


def _compact_evidence(evidence: Dict[str, Any]) -> Dict[str, Any]:
    """Reduce evidence payload size for LLM prompts (Groq free tier limits)."""
    compact = dict(evidence)
    txns = list(compact.get("card_transactions") or [])
    if len(txns) > 18:
        compact["card_transactions"] = txns[-18:]
    for key in ("customer_prior_cases", "prior_cases"):
        pcs = compact.get(key)
        if isinstance(pcs, list) and len(pcs) > 4:
            compact[key] = pcs[:4]
    for key in ("device_neighbors", "region_neighbor_cards", "email_neighbor_cards"):
        items = compact.get(key)
        if isinstance(items, list) and len(items) > 6:
            compact[key] = items[:6]
    return compact


def build_investigation_prompt(
    case_row: dict,
    evidence: dict,
    memory_context: str = "",
) -> str:
    """
    Build the user message for the LLM.
    This is where GraphRAG happens: structured graph evidence → LLM context.
    """

    # --- Format card transaction history ---
    txn_history = evidence.get("card_transactions", [])
    txn_lines = []
    for t in txn_history[-18:]:
        attrs = t.get("attributes", t)
        txn_lines.append(
            f"  txn_id={t.get('v_id', attrs.get('transaction_id','?'))} "
            f"ts={attrs.get('ts','?')} "
            f"amount=${attrs.get('amount', attrs.get('TransactionAmt','?'))} "
            f"channel={attrs.get('channel','?')} "
            f"risk={attrs.get('risk_score','?')} "
            f"product={attrs.get('product_cd','?')} "
            f"region={attrs.get('addr1','?')}"
        )
    txn_history_str = "\n".join(txn_lines) if txn_lines else "No transaction history found."

    # --- Format device profile ---
    device = evidence.get("device", {})
    device_attrs = device.get("attributes", device)
    device_str = (
        f"DeviceType={device_attrs.get('device_type','?')} "
        f"DeviceInfo={device_attrs.get('device_info','?')} "
        f"OS={device_attrs.get('os','?')} "
        f"Browser={device_attrs.get('browser','?')} "
        f"Status={device_attrs.get('device_status','?')} "
        f"Proxy={device_attrs.get('proxy_type','?')}"
        if device_attrs else "No device record (in-person transaction or identity not captured)."
    )

    # --- Format device neighbors (other cards on same device) ---
    neighbors = evidence.get("device_neighbors", [])
    neighbor_str = (
        ", ".join(n.get("v_id", "") for n in neighbors[:10])
        if neighbors else "None found."
    )

    # --- Format fraud cases on same device ---
    fraud_on_device = evidence.get("fraud_cases_on_device", [])
    fraud_device_str = (
        ", ".join(c.get("v_id", "") for c in fraud_on_device[:5])
        if fraud_on_device else "None."
    )

    # --- Format prior cases for this customer ---
    prior_cases = evidence.get("customer_prior_cases") or evidence.get("prior_cases", [])
    prior_str_lines = []
    for pc in prior_cases[:4]:
        attrs = pc.get("attributes", pc)
        prior_str_lines.append(
            f"  case_id={pc.get('v_id', '?')} "
            f"outcome={attrs.get('outcome','?')} "
            f"pattern={attrs.get('pattern','?')} "
            f"exposure=${attrs.get('exposure_usd','?')} "
            f"actions={attrs.get('actions_taken','?')} "
            f"notes={attrs.get('analyst_notes','?')[:60]}"
        )
    prior_str = "\n".join(prior_str_lines) if prior_str_lines else "No prior cases found."

    # --- Neighbor cards from region/email links ---
    region_neighbors = evidence.get("region_neighbor_cards", [])
    region_neighbor_str = (
        ", ".join(n.get("v_id", "") for n in region_neighbors[:10])
        if region_neighbors else "None found."
    )
    email_neighbors = evidence.get("email_neighbor_cards", [])
    email_neighbor_str = (
        ", ".join(n.get("v_id", "") for n in email_neighbors[:10])
        if email_neighbors else "None found."
    )

    # --- Flagged transaction ---
    flagged = evidence.get("flagged_txn", {})
    flagged_attrs = flagged.get("attributes", flagged)

    prompt = f"""
=== CASE TO INVESTIGATE ===
case_id: {case_row['case_id']}
opened_at: {case_row['opened_at']}
trigger_type: {case_row['trigger_type']}
trigger_text: {case_row['trigger_text']}
flagged_txn_id: {case_row['flagged_txn_id']}
card_id: {case_row['card_id']}
customer_id: {case_row['customer_id']}
risk_score: {case_row.get('risk_score', 'N/A')}

=== FLAGGED TRANSACTION DETAILS ===
amount: ${flagged_attrs.get('amount', flagged_attrs.get('TransactionAmt', '?'))}
timestamp: {flagged_attrs.get('ts', '?')}
channel: {flagged_attrs.get('channel', '?')}
product_cd: {flagged_attrs.get('product_cd', '?')}
billing_region: {flagged_attrs.get('addr1', '?')}
billing_country: {flagged_attrs.get('addr2', '?')}
p_email_domain: {flagged_attrs.get('p_email_domain', '?')}

=== DEVICE PROFILE (from graph) ===
{device_str}

=== CARD TRANSACTION HISTORY (from graph, last 18) ===
{txn_history_str}

=== OTHER CARDS ON SAME DEVICE (from graph) ===
{neighbor_str}
(If this list is non-empty, include those card IDs in connected_card_ids — exclude this case's card.)

=== CONFIRMED FRAUD CLOSED CASES ON SAME DEVICE (from graph) ===
{fraud_device_str}

=== CARDS SHARING FLAGGED REGION (from graph) ===
{region_neighbor_str}

=== CARDS SHARING FLAGGED PURCHASER EMAIL DOMAIN (from graph) ===
{email_neighbor_str}

=== PRIOR CLOSED CASES FOR THIS CUSTOMER (from graph) ===
{prior_str}

{memory_context}

=== YOUR TASK ===
1. Investigate this case using the evidence above.
2. Identify the fraud pattern (or confirm legitimate).
3. Assess fraud_probability honestly (not just based on risk_score).
4. Apply the fraud policy rules to determine next best actions.
5. Simulate one evidence request if needed (customer_validation is most common).
6. Output ONLY valid JSON following this exact schema:

{OUTPUT_SCHEMA}

Rules:
- Every ID you use must come from the data above. No made-up IDs.
- affected_txn_ids, connected_card_ids, connected_device_profiles, and similar_prior_cases
  must be grounded in the evidence sections above (including Relevant Previous Investigations when present).
- If OTHER CARDS ON SAME DEVICE is non-empty, populate connected_card_ids with those IDs (exclude this case's card).
- card_not_present_new_device requires device Status=New; if Status=Found use card_not_present_fraud instead.
- If verdict is legitimate: affected_txn_ids=[], exposure_usd=0, sar.file=false and clear all SAR body fields.
- FILE_REPORT threshold uses THIS CASE exposure_usd only — not prior-case exposure.
- R1 applies only when fraud_probability < 0.70.
- If verdict=fraud and investigation is complete: status=closed_fraud.
- If uncertain + exposure > $500: include ESCALATE_TO_ANALYST per R8
- FILE_REPORT must use route L2 (never auto). BLOCK_CARD uses L1 unless exposure > $2500.
- written_to_graph should be false (the code will handle this after your output)
- tool_calls: count how many graph queries were used (estimate from the evidence sections above)
- Cite policy rule numbers in every action reason
- Always include top-level keys: sar (full object), stop_reason, evidence_requests (list, may be empty)
"""
    return prompt.strip()


def run_case(
    client: OpenAI,
    model: str,
    conn,
    case_row: Dict[str, Any],
    dry_run_evidence: Optional[Dict[str, Any]],
    skip_graph_write: bool,
) -> dict:
    """Run the agent on a single case. Returns the full output dict."""
    start_time = time.time()

    if dry_run_evidence is not None:
        print(f"\n[{case_row['case_id']}] Using dry-run evidence fixture...")
        evidence = dry_run_evidence
    else:
        print(f"\n[{case_row['case_id']}] Gathering evidence from graph...")
        evidence = gather_all_evidence(
            conn,
            flagged_txn_id=str(case_row["flagged_txn_id"]),
            card_id=case_row["card_id"],
            customer_id=case_row["customer_id"],
        )
    tool_calls = int(evidence.get("_tool_calls", 0))

    memory_context = ""
    memory_case_ids: list[str] = []
    if dry_run_evidence is None and conn is not None:
        try:
            print(f"[{case_row['case_id']}] Retrieving case memory...")
            memory_result = retrieve_case_memory(conn, case_row, evidence, top_k=5)
            memory_context = memory_result.context_markdown
            memory_case_ids = [h.case_id for h in memory_result.ranked_hits]
            evidence["memory_context"] = memory_context
            evidence["memory_case_ids"] = memory_case_ids
            tool_calls += 1 + memory_result.graph_hit_count // 3
        except Exception as exc:
            print(f"[{case_row['case_id']}] Memory retrieval error: {exc}")

    if len(memory_context) > 1800:
        memory_context = memory_context[:1800] + "\n...(memory truncated for token limit)"

    def _call_llm(prompt_evidence: Dict[str, Any], *, json_object: bool = True) -> tuple[str, int]:
        user_prompt = build_investigation_prompt(
            case_row, prompt_evidence, memory_context=memory_context
        )
        msg = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ]
        schema_payload = {
            "name": "fraud_investigation_result",
            "strict": False,
            "schema": InvestigationResult.model_json_schema(),
        }
        use_groq = get_llm_provider() == "groq"
        kwargs: Dict[str, Any] = {
            "model": model,
            "messages": msg,
            "temperature": 0.1,
        }
        if json_object:
            kwargs["response_format"] = {"type": "json_object"}
        if use_groq:
            resp = client.chat.completions.create(**kwargs)
        else:
            if json_object:
                kwargs["response_format"] = {
                    "type": "json_schema",
                    "json_schema": schema_payload,
                }
            try:
                resp = client.chat.completions.create(**kwargs)
            except Exception:
                kwargs["response_format"] = {"type": "json_object"}
                resp = client.chat.completions.create(**kwargs)
        content = resp.choices[0].message.content or ""
        usage = resp.usage.total_tokens if resp.usage else 0
        return content, usage

    print(f"[{case_row['case_id']}] Calling LLM...")
    prompt_evidence = _compact_evidence(evidence)
    raw_output = ""
    tokens_used = 0
    salvaged = False
    result: Optional[Dict[str, Any]] = None
    try:
        raw_output, tokens_used = _call_llm(prompt_evidence)
    except Exception as exc:
        err = str(exc)
        if "json_validate_failed" in err or "failed_generation" in err:
            recovered = salvage_json_from_api_error(err)
            if recovered:
                print(
                    f"[{case_row['case_id']}] Groq JSON validation failed; "
                    "salvaging repaired failed_generation..."
                )
                result = validate_and_normalize_result(recovered, case_row, evidence)
                result["tool_calls"] = tool_calls
                result["tokens"] = tokens_used
                result["latency_s"] = round(time.time() - start_time, 2)
                salvaged = True
            else:
                print(
                    f"[{case_row['case_id']}] JSON mode failed; retrying without strict JSON..."
                )
                try:
                    raw_output, tokens_used = _call_llm(
                        prompt_evidence, json_object=False
                    )
                except Exception as retry_exc:
                    print(f"[{case_row['case_id']}] ERROR: {retry_exc}")
                    return {"case_id": case_row["case_id"], "error": str(retry_exc)}
        elif "413" in err or "Request too large" in err or "rate_limit_exceeded" in err:
            print(f"[{case_row['case_id']}] Prompt too large; retrying with smaller evidence...")
            smaller = dict(prompt_evidence)
            txns = list(smaller.get("card_transactions") or [])
            smaller["card_transactions"] = txns[-10:]
            smaller["memory_context"] = ""
            memory_context = ""
            try:
                raw_output, tokens_used = _call_llm(smaller)
            except Exception as retry_exc:
                print(f"[{case_row['case_id']}] ERROR: {retry_exc}")
                return {"case_id": case_row["case_id"], "error": str(retry_exc)}
        else:
            print(f"[{case_row['case_id']}] ERROR: {exc}")
            return {"case_id": case_row["case_id"], "error": err}

    if salvaged:
        pass  # result already set in except block
    elif not raw_output:
        return {"case_id": case_row["case_id"], "error": "Empty LLM response"}
    else:
        try:
            parsed = loads_llm_json(raw_output)
        except json.JSONDecodeError as e:
            print(f"[{case_row['case_id']}] JSON parse error: {e}")
            print(f"Raw output: {raw_output[:500]}")
            return {"case_id": case_row["case_id"], "error": str(e), "raw": raw_output}

        result = validate_and_normalize_result(parsed, case_row, evidence)
        result["tool_calls"] = tool_calls
        result["tokens"] = tokens_used
        result["latency_s"] = round(time.time() - start_time, 2)

    if result is None:
        return {"case_id": case_row["case_id"], "error": "Failed to produce investigation result"}

    if not skip_graph_write and conn is not None:
        print(f"[{case_row['case_id']}] Writing case to graph...")
        graph_case_id = write_case_to_graph(conn, result, case_row)
        if graph_case_id:
            result["case"]["written_to_graph"] = True
            result["case"]["graph_case_id"] = graph_case_id
            try:
                write_case_memory(conn, result, case_row, evidence, graph_case_id=graph_case_id)
            except Exception as exc:
                print(f"[{case_row['case_id']}] Memory write-back error: {exc}")

    return result


def main():
    args = parse_args()
    if not args.case_id and not args.all_cases:
        raise SystemExit("Choose one: --case-id HHG-XXX or --all-cases")
    if args.case_id and args.all_cases:
        raise SystemExit("Use either --case-id or --all-cases, not both.")

    client = build_client()
    provider = get_llm_provider()
    print(f"LLM provider: {provider} | model: {args.model}")
    case_pack_path = Path(args.case_pack).expanduser().resolve()
    output_dir = Path(args.output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    if not case_pack_path.exists():
        raise FileNotFoundError(f"case_pack.csv not found: {case_pack_path}")
    case_pack = pd.read_csv(case_pack_path)

    if args.case_id:
        case_pack = case_pack[case_pack["case_id"] == args.case_id]
        if case_pack.empty:
            raise SystemExit(f"Case id not found in case pack: {args.case_id}")
    if args.max_cases is not None:
        case_pack = case_pack.head(args.max_cases)

    dry_run_evidence = None
    if args.dry_run_evidence:
        evidence_path = Path(args.dry_run_evidence).expanduser().resolve()
        with evidence_path.open("r", encoding="utf-8") as f:
            dry_run_evidence = json.load(f)
        print(f"Loaded dry-run evidence fixture: {evidence_path}")

    conn = None
    if dry_run_evidence is None and not args.skip_graph_write:
        print("Connecting to TigerGraph...")
        conn = get_conn()
        print("Connected.")
    elif dry_run_evidence is None:
        print("Graph writes disabled; connecting for read-only evidence queries...")
        conn = get_conn()
        print("Connected.")
    else:
        print("Dry-run evidence mode: skipping TigerGraph connection.")

    results = []
    for _, case_row in case_pack.iterrows():
        case_id = case_row["case_id"]
        print(f"\n{'='*50}")
        print(f"Running case {case_id}...")

        try:
            result = run_case(
                client=client,
                model=args.model,
                conn=conn,
                case_row=case_row.to_dict(),
                dry_run_evidence=dry_run_evidence,
                skip_graph_write=args.skip_graph_write,
            )
            results.append(result)

            # Save individual file
            out_path = output_dir / f"{case_id}.json"
            with out_path.open("w", encoding="utf-8") as f:
                json.dump(result, f, indent=2)
            print(f"[{case_id}] Saved to {out_path}")
            print(f"[{case_id}] Verdict: {result.get('case', {}).get('verdict', '?')} | "
                  f"Pattern: {result.get('case', {}).get('pattern', '?')} | "
                  f"Exposure: ${result.get('case', {}).get('exposure_usd', 0)}")

        except Exception as e:
            print(f"[{case_id}] ERROR: {e}")
            error_result = {"case_id": case_id, "error": str(e)}
            results.append(error_result)
            with (output_dir / f"{case_id}.json").open("w", encoding="utf-8") as f:
                json.dump(error_result, f, indent=2)

        # Small delay to avoid rate limits
        time.sleep(args.sleep_seconds)

    # Summary
    print(f"\n{'='*50}")
    print(f"Done. {len(results)} cases processed.")
    fraud_count = sum(1 for r in results if r.get("case", {}).get("verdict") == "fraud")
    legit_count = sum(1 for r in results if r.get("case", {}).get("verdict") == "legitimate")
    uncertain_count = sum(1 for r in results if r.get("case", {}).get("verdict") == "uncertain")
    print(f"Fraud: {fraud_count} | Legitimate: {legit_count} | Uncertain: {uncertain_count}")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"Fatal error: {exc}", file=sys.stderr)
        sys.exit(1)
