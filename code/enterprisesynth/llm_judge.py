from __future__ import annotations

import json
import os

import anthropic

MODEL = "claude-sonnet-5"

PROMPT = """You are an expert evaluator judging whether an AI agent's API tool call correctly
fulfills a user's request. You will score four dimensions on a 1-5 scale (5 = excellent, 1 = badly
wrong).

User instruction: "{intent}"

Ground-truth API specification for the correct endpoint:
  Method: {gt_method}
  Path: {gt_path}
  Required parameters: {gt_required_params}

Reference (a correct invocation would use the endpoint above, supplying real values for each
required parameter listed).

EnterpriseSynth's actual prediction:
  Method: {pred_method}
  Path: {pred_path}
  Parameters: {pred_parameters}

Score these four dimensions, 1-5 each:
1. intent_match: Does the predicted API call (endpoint chosen) satisfy the user's request?
2. argument_correctness: Are the supplied parameter values plausible and correctly typed for what
   the request needs (ignore whether they're the exact right example values, judge plausibility)?
3. missing_parameters: Are all of the ground-truth required parameters present in the prediction's
   parameters (5 = none missing, 1 = most/all missing)?
4. reasoning_quality: Given only the intent and the prediction (no visible reasoning trace), does
   the choice of endpoint + parameters look like it followed logically from the request?

Also classify the primary error, if any, as exactly one of: "none", "wrong_tool_selected",
"missing_required_parameter", "incorrect_argument_value", "hallucinated_parameter",
"invalid_request_format".

Respond with ONLY a JSON object in this exact shape:
{{"intent_match": <1-5>, "argument_correctness": <1-5>, "missing_parameters": <1-5>,
"reasoning_quality": <1-5>, "primary_error": "<category>"}}
"""


class LLMJudge:
    """LLM-as-a-Judge semantic quality scorer (Phase 4, Solution A).

    Complements Tool Selection Accuracy (a binary metric) with four 1-5 Likert-scale dimensions
    that binary accuracy cannot capture: intent match, argument correctness, missing parameters,
    and reasoning quality. Also classifies the primary error type per example for error analysis.
    """

    def __init__(self, client: anthropic.Anthropic | None = None):
        self.client = client or anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))

    def judge(
        self,
        intent: str,
        gt_method: str,
        gt_path: str,
        gt_required_params: list[str],
        pred_method: str | None,
        pred_path: str | None,
        pred_parameters: dict,
    ) -> dict | None:
        prompt = PROMPT.format(
            intent=intent,
            gt_method=gt_method,
            gt_path=gt_path,
            gt_required_params=", ".join(gt_required_params) or "(none)",
            pred_method=pred_method or "(no valid method parsed)",
            pred_path=pred_path or "(no valid path parsed)",
            pred_parameters=json.dumps(pred_parameters or {}),
        )
        response = self.client.messages.create(
            model=MODEL, max_tokens=1200, messages=[{"role": "user", "content": prompt}]
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
