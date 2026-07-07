"""Smoke tests for finetune.py's pure-logic helpers (prompt formatting, JSON extraction).

The module imports torch/peft at the top level, so it can't even be collected without them
installed -- these are optional dependencies (see README's Setup section), not part of the base
`pip install -e ".[dev]"` CI environment. importorskip means this file runs when torch is
available (e.g. locally, while working on Experiment 5) and skips cleanly everywhere else,
instead of failing collection.

Model loading, training, and generation (train_lora, generate_response, evaluate) are not covered
here -- those need a real model/tokenizer and are exercised by actually running
scripts/run_experiment5.py, not by a mocked unit test.
"""

import pytest

torch = pytest.importorskip("torch")

from enterprisesynth.finetune import extract_json, format_prompt  # noqa: E402


def test_format_prompt_includes_intent_and_tools():
    candidates = [
        {"method": "POST", "path": "/repos/{owner}/{repo}/issues", "operation_id": "CreateIssue"},
        {"method": "GET", "path": "/repos/{owner}/{repo}", "operation_id": "GetRepo"},
    ]
    prompt = format_prompt("file a bug", candidates)
    assert "file a bug" in prompt
    assert "POST /repos/{owner}/{repo}/issues" in prompt
    assert "GET /repos/{owner}/{repo}" in prompt


def test_format_prompt_empty_candidates():
    prompt = format_prompt("do something", [])
    assert "do something" in prompt
    assert "Available tools:\n" in prompt


def test_extract_json_happy_path():
    text = 'Sure, here you go: {"selected_method": "GET", "selected_path": "/x"} thanks!'
    result = extract_json(text)
    assert result == {"selected_method": "GET", "selected_path": "/x"}


def test_extract_json_no_braces_returns_none():
    assert extract_json("no json here") is None


def test_extract_json_malformed_returns_none():
    assert extract_json('{"unterminated": ') is None


def test_extract_json_nested_object():
    text = '{"selected_method": "POST", "parameters": {"a": 1, "b": {"c": 2}}}'
    result = extract_json(text)
    assert result["parameters"]["b"]["c"] == 2
