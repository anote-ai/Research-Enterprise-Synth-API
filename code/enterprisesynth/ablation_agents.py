from __future__ import annotations

import json
import os

import anthropic

from .schemas import Endpoint

MODEL = "claude-sonnet-5"


def _text_of(response) -> str:
    return "".join(block.text for block in response.content if block.type == "text").strip()


def _strip_fences(text: str) -> str:
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
        text = text.strip()
    return text


class NoIntentTrajectoryAgent:
    """A1 ablation: Trajectory Generator with the Intent Agent removed.

    Given only an endpoint (no user-authored intent), directly produces a plausible
    instruction + parameters -- there is no candidate list to select from, since the
    endpoint is given directly rather than discovered via intent-driven tool selection.
    """

    PROMPT = """You are generating training data for an enterprise AI agent that calls APIs.

Given this API endpoint (no user request provided):
  Method: {method}
  Path: {path}
  Operation ID: {operation_id}
  Parameters: {parameters}

Without any specific user intent to work from, invent a plausible one-sentence instruction a
user might give that this endpoint would fulfill, AND concrete parameter values.

Respond with ONLY a JSON object: {{"instruction": "...", "parameters": {{...}}}}
"""

    def __init__(self, client: anthropic.Anthropic | None = None):
        self.client = client or anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))

    def generate(self, endpoint: Endpoint) -> dict | None:
        param_desc = ", ".join(
            f"{p.name} ({p.location}, {'required' if p.required else 'optional'})"
            for p in endpoint.parameters
        ) or "none"
        prompt = self.PROMPT.format(
            method=endpoint.method,
            path=endpoint.path,
            operation_id=endpoint.operation_id or "(none)",
            parameters=param_desc,
        )
        response = self.client.messages.create(
            model=MODEL, max_tokens=400, messages=[{"role": "user", "content": prompt}]
        )
        text = _strip_fences(_text_of(response))
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return None


class DescriptionAwareIntentAgent:
    """A3 ablation (the 'with' condition): Intent Agent given the endpoint's OpenAPI
    description/summary, vs. the baseline (Experiment 2), which never had access to it.
    """

    PROMPT = """You are generating training data for an enterprise AI agent that calls APIs.

Given this API endpoint:
  Method: {method}
  Path: {path}
  Operation ID: {operation_id}
  Description: {description}
  Parameters: {parameters}

Generate {n} diverse, realistic ENTERPRISE user intents (short natural-language requests from a
person at a company) that a user might say which this specific endpoint would be the correct way
to fulfill. Vary the phrasing and the business scenario across the {n} intents.

Respond with ONLY a JSON array of {n} strings.
"""

    def __init__(self, client: anthropic.Anthropic | None = None):
        self.client = client or anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))

    def generate_intents(self, endpoint: Endpoint, n: int = 3) -> list[str]:
        param_desc = ", ".join(
            f"{p.name} ({p.location}, {'required' if p.required else 'optional'})"
            for p in endpoint.parameters
        ) or "none"
        prompt = self.PROMPT.format(
            method=endpoint.method,
            path=endpoint.path,
            operation_id=endpoint.operation_id or "(none)",
            description=endpoint.description or "(none provided)",
            parameters=param_desc,
            n=n,
        )
        response = self.client.messages.create(
            model=MODEL, max_tokens=500, messages=[{"role": "user", "content": prompt}]
        )
        text = _strip_fences(_text_of(response))
        try:
            intents = json.loads(text)
        except json.JSONDecodeError:
            return []
        return [str(i) for i in intents] if isinstance(intents, list) else []


class FullContextIntentAgent:
    """A4 ablation (the 'with' condition): Intent Agent given the full list of the API's
    other endpoints, vs. the baseline (Experiment 2), which only ever saw one endpoint at a time.
    """

    PROMPT = """You are generating training data for an enterprise AI agent that calls APIs.

Target endpoint:
  Method: {method}
  Path: {path}
  Operation ID: {operation_id}
  Parameters: {parameters}

Other endpoints available in this same API (for context -- you may reference multi-step
workflows that use one or more of these together with the target endpoint):
{other_endpoints}

Generate {n} diverse, realistic ENTERPRISE user intents for which the TARGET endpoint above is
the correct (or a necessary) step to fulfill. If a request naturally requires a multi-step
workflow involving other listed endpoints, you may describe it that way -- but the target
endpoint must be involved.

Respond with ONLY a JSON array of {n} strings.
"""

    def __init__(self, client: anthropic.Anthropic | None = None):
        self.client = client or anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))

    def generate_intents(
        self, endpoint: Endpoint, other_endpoints: list[Endpoint], n: int = 3
    ) -> list[str]:
        param_desc = ", ".join(
            f"{p.name} ({p.location}, {'required' if p.required else 'optional'})"
            for p in endpoint.parameters
        ) or "none"
        other_desc = "\n".join(f"- {e.method} {e.path}" for e in other_endpoints) or "(none)"
        prompt = self.PROMPT.format(
            method=endpoint.method,
            path=endpoint.path,
            operation_id=endpoint.operation_id or "(none)",
            parameters=param_desc,
            other_endpoints=other_desc,
            n=n,
        )
        response = self.client.messages.create(
            model=MODEL, max_tokens=600, messages=[{"role": "user", "content": prompt}]
        )
        text = _strip_fences(_text_of(response))
        try:
            intents = json.loads(text)
        except json.JSONDecodeError:
            return []
        return [str(i) for i in intents] if isinstance(intents, list) else []
