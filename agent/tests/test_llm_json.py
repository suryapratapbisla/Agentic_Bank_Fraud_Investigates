import pytest

from llm_json import loads_llm_json, repair_llm_json_text, salvage_json_from_api_error


def test_repair_decimal_word_nine():
    raw = '{"fraud_probability":0. nine,"verdict":"fraud"}'
    fixed = repair_llm_json_text(raw)
    data = loads_llm_json(fixed)
    assert data["fraud_probability"] == 0.9


def test_salvage_from_groq_error_string():
    err = (
        "Error code: 400 - {'error': {'message': 'Failed', 'code': 'json_validate_failed', "
        "'failed_generation': '{\"case_id\":\"HHG-001\",\"case\":{\"fraud_probability\":0. nine}}'}}"
    )
    data = salvage_json_from_api_error(err)
    assert data is not None
    assert data["case_id"] == "HHG-001"
    assert data["case"]["fraud_probability"] == 0.9
