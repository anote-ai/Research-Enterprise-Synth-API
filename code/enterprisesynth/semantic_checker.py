from __future__ import annotations

import json
import os

import anthropic

MODEL = "claude-haiku-4-5"

PROMPT = """You are a semantic-plausibility checker for an API agent trajectory. The trajectory
below is already known to be STRUCTURALLY valid (correct endpoint, correct HTTP method, all
required parameters present with correct types) -- a separate deterministic checker already
confirmed that. Your job is different: does this trajectory make semantic/business SENSE for the
stated user request, or does something look wrong despite being well-typed (e.g. a nonsensical
value, an implausible quantity, a placeholder string that isn't real data)?

User request: "{intent}"

Trajectory:
  Method: {method}
  Path: {path}
  Parameters: {parameters}
  Reasoning given: {reasoning}

Respond with ONLY a JSON object: {{"plausible": true or false, "reason": "<one sentence>"}}
"""


class SemanticPlausibilityChecker:
    """Optional ablation arm layered on top of the deterministic Schema Verification Engine.

    Tests whether a cheap LLM catches semantically-wrong-but-structurally-valid trajectories --
    a class of error the deterministic verifier cannot catch by design, since it only checks
    types/required-fields/existence, not whether parameter VALUES make business sense.
    """

    def __init__(self, client: anthropic.Anthropic | None = None):
        self.client = client or anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))

    def check(self, intent: str, trajectory: dict) -> dict | None:
        prompt = PROMPT.format(
            intent=intent,
            method=trajectory.get("selected_method", ""),
            path=trajectory.get("selected_path", ""),
            parameters=json.dumps(trajectory.get("parameters") or {}),
            reasoning=trajectory.get("reasoning", ""),
        )
        response = self.client.messages.create(
            model=MODEL, max_tokens=200, messages=[{"role": "user", "content": prompt}]
        )
        text = "".join(b.text for b in response.content if b.type == "text").strip()
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
            text = text.strip()
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return None
