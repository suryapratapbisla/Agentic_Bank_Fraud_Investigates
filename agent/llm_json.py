"""Parse and repair LLM JSON (Groq json_validate_failed salvage)."""

from __future__ import annotations

import ast
import json
import re
from typing import Any, Dict, Optional

_DECIMAL_WORDS = {
    "zero": "0",
    "one": "1",
    "two": "2",
    "three": "3",
    "four": "4",
    "five": "5",
    "six": "6",
    "seven": "7",
    "eight": "8",
    "nine": "9",
}


def repair_llm_json_text(text: str) -> str:
    """Fix common invalid JSON tokens from chat models."""
    text = text.replace("\u2011", "-").replace("\u2013", "-").replace("\u2014", "-")
    text = text.replace("\u201c", '"').replace("\u201d", '"')

    def fix_decimal_words(match: re.Match[str]) -> str:
        word = match.group(1).lower()
        digit = _DECIMAL_WORDS.get(word)
        if digit is not None:
            return f"0.{digit}"
        return match.group(0)

    text = re.sub(r"0\.\s*([a-z]+)", fix_decimal_words, text, flags=re.IGNORECASE)
    # Trailing commas before } or ]
    text = re.sub(r",\s*([}\]])", r"\1", text)
    return text


def loads_llm_json(text: str) -> Dict[str, Any]:
    cleaned = repair_llm_json_text(text.strip())
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    return json.loads(cleaned)


def extract_failed_generation(error_text: str) -> Optional[str]:
    """Pull failed_generation payload from Groq/OpenAI API error string."""
    if "failed_generation" not in error_text:
        return None

    # Error shape: Error code: 400 - {'error': {..., 'failed_generation': '...'}}
    marker = "400 - "
    if marker in error_text:
        tail = error_text.split(marker, 1)[1].strip()
        try:
            body = ast.literal_eval(tail)
            fg = body.get("error", {}).get("failed_generation")
            if isinstance(fg, str) and fg.strip():
                return fg
        except (SyntaxError, ValueError):
            pass

    match = re.search(
        r"failed_generation['\"]:\s*'((?:\\'|[^'])*)'",
        error_text,
        re.DOTALL,
    )
    if match:
        return match.group(1).replace("\\'", "'")

    match = re.search(
        r'failed_generation["\']:\s*"((?:\\"|[^"])*)"',
        error_text,
        re.DOTALL,
    )
    if match:
        return match.group(1).replace('\\"', '"')

    return None


def salvage_json_from_api_error(error_text: str) -> Optional[Dict[str, Any]]:
    """Try to recover a dict from json_validate_failed errors."""
    raw = extract_failed_generation(error_text)
    if not raw:
        return None
    try:
        return loads_llm_json(raw)
    except json.JSONDecodeError:
        return None
