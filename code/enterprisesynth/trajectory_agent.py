from __future__ import annotations

import json
import os

import anthropic

from .schemas import Endpoint

MODEL = "claude-sonnet-5"

PROMPT_TEMPLATE = """You are an enterprise AI agent that calls APIs on behalf of users.

User request: "{intent}"

Available tools (choose the ONE correct tool for this request):
{tool_list}

Respond with ONLY a JSON object, nothing else, in this exact shape:
{{
  "selected_method": "<HTTP method of the tool you chose>",
  "selected_path": "<path of the tool you chose, exactly as listed above>",
  "reasoning": "<1-2 sentences on why this tool fulfills the request>",
  "parameters": {{"<param name>": "<concrete example value>", ...}},
  "expected_response_summary": "<1 sentence on what a successful response would contain>"
}}
"""


def _format_tool(endpoint: Endpoint) -> str:
    params = ", ".join(
        f"{p.name} ({p.location}, {'required' if p.required else 'optional'}, {p.schema_type or 'unknown type'})"
        for p in endpoint.parameters
    ) or "none"
    return f"- {endpoint.method} {endpoint.path} | operation_id={endpoint.operation_id} | params: {params}"


class TrajectoryGenerator:
    """Stages 4+5 combined for this pilot: Agentic Planning + Trajectory Generator.

    Given a user intent and a candidate tool list, selects a tool and generates concrete
    parameters, reasoning, and an expected-response summary in one call.
    """

    def __init__(self, client: anthropic.Anthropic | None = None):
        self.client = client or anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))

    def generate_trajectory(self, intent: str, candidate_endpoints: list[Endpoint]) -> dict | None:
        tool_list = "\n".join(_format_tool(e) for e in candidate_endpoints)
        prompt = PROMPT_TEMPLATE.format(intent=intent, tool_list=tool_list)

        response = self.client.messages.create(
            model=MODEL,
            max_tokens=600,
            messages=[{"role": "user", "content": prompt}],
        )
        text_blocks = [block.text for block in response.content if block.type == "text"]
        text = "".join(text_blocks).strip()

        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
            text = text.strip()

        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return None
