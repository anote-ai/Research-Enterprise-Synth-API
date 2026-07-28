from __future__ import annotations

import json
import os

import anthropic

from .schemas import Endpoint

MODEL = "claude-sonnet-5"

PROMPT_TEMPLATE = """You are generating training data for an enterprise AI agent that calls APIs.

Given this API endpoint:
  Method: {method}
  Path: {path}
  Operation ID: {operation_id}
  Parameters: {parameters}

Generate {n} diverse, realistic ENTERPRISE user intents (short natural-language requests from a
person at a company) that a user might say which this specific endpoint would be the correct way
to fulfill. Vary the phrasing and the business scenario across the {n} intents -- do not just
reword the same sentence.

Respond with ONLY a JSON array of {n} strings, nothing else. Example format:
["intent one", "intent two", "intent three"]
"""


class IntentSynthesisAgent:
    """Stage 3: Intent Synthesis Agent. Generates user intents for an API endpoint."""

    def __init__(self, client: anthropic.Anthropic | None = None):
        self.client = client or anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))

    def generate_intents(self, endpoint: Endpoint, n: int = 3) -> list[str]:
        param_desc = ", ".join(
            f"{p.name} ({p.location}, {'required' if p.required else 'optional'})"
            for p in endpoint.parameters
        ) or "none"

        prompt = PROMPT_TEMPLATE.format(
            method=endpoint.method,
            path=endpoint.path,
            operation_id=endpoint.operation_id or "(none)",
            parameters=param_desc,
            n=n,
        )

        response = self.client.messages.create(
            model=MODEL,
            max_tokens=500,
            messages=[{"role": "user", "content": prompt}],
        )
        text_blocks = [block.text for block in response.content if block.type == "text"]
        text = "".join(text_blocks).strip()

        # Strip markdown code fences if the model added them despite instructions.
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
            text = text.strip()

        try:
            intents = json.loads(text)
        except json.JSONDecodeError:
            return []

        if not isinstance(intents, list):
            return []
        return [str(i) for i in intents]
