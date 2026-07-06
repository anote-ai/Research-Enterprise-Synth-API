"""Experiment 1: OpenAPI Schema Understanding.

Parses each spec with SchemaParser (src/enterprisesynth/parser.py), then independently
recomputes ground-truth counts directly from the raw spec dict (not reusing the parser's
internal logic) to check extraction correctness.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from enterprisesynth.parser import HTTP_METHODS, SchemaParser  # noqa: E402

SPECS = {
    "GitHub": "data/specs/github.json",
    "Stripe": "data/specs/stripe.json",
    "Slack": "data/specs/slack.json",
}


def _resolve_ref(spec: dict, ref: str) -> dict:
    """Independent $ref resolver (deliberately separate from parser.py's, to keep this ground
    truth check honest -- if both implementations shared a bug, this cross-check wouldn't catch it).
    """
    node = spec
    for part in ref.lstrip("#/").split("/"):
        if not isinstance(node, dict):
            return {}
        node = node.get(part, {})
    return node if isinstance(node, dict) else {}


def ground_truth_counts(spec: dict) -> dict:
    """Independently recomputes counts directly from the raw spec, without using SchemaParser."""
    total_endpoints = 0
    total_required_params = 0
    endpoints_with_request_schema = 0
    endpoints_with_response_schema = 0
    endpoints_with_auth = 0
    global_security = spec.get("security", [])
    has_global_auth = bool(global_security)

    for path, path_item in spec.get("paths", {}).items():
        if not isinstance(path_item, dict):
            continue
        path_params = path_item.get("parameters", [])
        for method in HTTP_METHODS:
            if method not in path_item:
                continue
            op = path_item[method]
            if not isinstance(op, dict):
                continue
            total_endpoints += 1

            all_params_raw = [p for p in (path_params + op.get("parameters", [])) if isinstance(p, dict)]
            all_params = [
                _resolve_ref(spec, p["$ref"]) if "$ref" in p else p for p in all_params_raw
            ]
            total_required_params += sum(1 for p in all_params if p.get("required") is True)

            rb = op.get("requestBody")
            if isinstance(rb, dict):
                body_content = rb.get("content", {})
                body_schema = {}
                for media in body_content.values():
                    if isinstance(media, dict) and "schema" in media:
                        body_schema = media["schema"]
                        break
                if isinstance(body_schema, dict) and "$ref" in body_schema:
                    body_schema = _resolve_ref(spec, body_schema["$ref"])
                if isinstance(body_schema, dict):
                    total_required_params += len(body_schema.get("required", []))

            rb = op.get("requestBody")
            if isinstance(rb, dict):
                content = rb.get("content", {})
                if any("schema" in m for m in content.values()):
                    endpoints_with_request_schema += 1

            responses = op.get("responses", {})
            if isinstance(responses, dict):
                found = False
                for resp in responses.values():
                    if isinstance(resp, dict) and any(
                        "schema" in m for m in resp.get("content", {}).values()
                    ):
                        found = True
                        break
                if found:
                    endpoints_with_response_schema += 1

            has_op_auth = "security" in op and bool(op["security"])
            if has_op_auth or (has_global_auth and "security" not in op):
                endpoints_with_auth += 1

    return {
        "total_endpoints": total_endpoints,
        "total_required_params": total_required_params,
        "endpoints_with_request_schema": endpoints_with_request_schema,
        "endpoints_with_response_schema": endpoints_with_response_schema,
        "endpoints_with_auth": endpoints_with_auth,
    }


def parsed_counts(schema) -> dict:
    total_required_params = sum(
        sum(1 for p in e.parameters if p.required) for e in schema.endpoints
    )
    endpoints_with_request_schema = sum(1 for e in schema.endpoints if e.request_body_schema_present)
    endpoints_with_response_schema = sum(
        1 for e in schema.endpoints if any(e.response_schemas.values())
    )
    endpoints_with_auth = sum(1 for e in schema.endpoints if e.auth_schemes)
    return {
        "total_endpoints": len(schema.endpoints),
        "total_required_params": total_required_params,
        "endpoints_with_request_schema": endpoints_with_request_schema,
        "endpoints_with_response_schema": endpoints_with_response_schema,
        "endpoints_with_auth": endpoints_with_auth,
    }


def pct(numerator: int, denominator: int) -> str:
    if denominator == 0:
        return "n/a"
    return f"{100 * numerator / denominator:.1f}"


def main() -> None:
    parser = SchemaParser()
    rows = []
    for name, path in SPECS.items():
        with open(Path(__file__).resolve().parent.parent / path) as f:
            raw = json.load(f)

        gt = ground_truth_counts(raw)
        schema = parser.parse(raw)
        parsed = parsed_counts(schema)

        endpoint_accuracy = pct(parsed["total_endpoints"], gt["total_endpoints"])
        param_accuracy = pct(parsed["total_required_params"], gt["total_required_params"])
        req_schema_accuracy = pct(
            parsed["endpoints_with_request_schema"], gt["endpoints_with_request_schema"]
        )
        resp_schema_accuracy = pct(
            parsed["endpoints_with_response_schema"], gt["endpoints_with_response_schema"]
        )
        auth_accuracy = pct(parsed["endpoints_with_auth"], gt["endpoints_with_auth"])

        rows.append(
            {
                "API": name,
                "ground_truth": gt,
                "parsed": parsed,
                "Endpoint Extraction Accuracy (%)": endpoint_accuracy,
                "Parameter Accuracy (%)": param_accuracy,
                "Request Schema Accuracy (%)": req_schema_accuracy,
                "Response Schema Accuracy (%)": resp_schema_accuracy,
                "Authentication Accuracy (%)": auth_accuracy,
            }
        )

    print(json.dumps(rows, indent=2))
    print()
    print(
        f"{'API':<8} {'Paths+Methods':<15} {'Endpoint Acc %':<16} {'Param Acc %':<13} "
        f"{'ReqSchema Acc %':<17} {'RespSchema Acc %':<18} {'Auth Acc %':<12}"
    )
    for row in rows:
        print(
            f"{row['API']:<8} {row['ground_truth']['total_endpoints']:<15} "
            f"{row['Endpoint Extraction Accuracy (%)']:<16} {row['Parameter Accuracy (%)']:<13} "
            f"{row['Request Schema Accuracy (%)']:<17} {row['Response Schema Accuracy (%)']:<18} "
            f"{row['Authentication Accuracy (%)']:<12}"
        )


if __name__ == "__main__":
    main()
