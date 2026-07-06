from __future__ import annotations

from pydantic import BaseModel, Field

from .schemas import APISchema, Endpoint


class VerificationResult(BaseModel):
    valid: bool
    checks: dict[str, bool] = Field(default_factory=dict)
    errors: list[str] = Field(default_factory=list)


def _type_compatible(value: object, declared_type: str | None) -> bool:
    if declared_type is None:
        return True
    if declared_type == "string":
        return not isinstance(value, (dict, list))  # scalars stringify sensibly; objects/arrays don't
    if declared_type in ("integer", "number"):
        if isinstance(value, bool):
            return False
        if isinstance(value, (int, float)):
            return True
        if isinstance(value, str):
            try:
                float(value)
                return True
            except ValueError:
                return False
        return False
    if declared_type == "boolean":
        return isinstance(value, bool) or str(value).lower() in ("true", "false")
    if declared_type == "array":
        return isinstance(value, list)
    if declared_type == "object":
        return isinstance(value, dict)
    return True  # unknown declared type: don't fail on it


class SchemaVerificationEngine:
    """Stage 6: deterministic, non-LLM structural verification against the parsed spec.

    No execution, no LLM call -- pure structural checks. This is the core methodological
    differentiator from AgentInstruct's soft, LLM-judged verification (see DESIGN_DOC.md S2).
    """

    def __init__(self, schema: APISchema):
        self._by_key: dict[tuple[str, str], Endpoint] = {
            (e.method, e.path): e for e in schema.endpoints
        }

    def verify(self, selected_method: str, selected_path: str, parameters: dict) -> VerificationResult:
        errors: list[str] = []
        checks = {
            "endpoint_exists": False,
            "required_params_present": False,
            "param_types_valid": False,
        }

        key = (str(selected_method).upper(), selected_path)
        endpoint = self._by_key.get(key)

        if endpoint is None:
            errors.append(f"Endpoint {key[0]} {key[1]} does not exist in the spec.")
            return VerificationResult(valid=False, checks=checks, errors=errors)
        checks["endpoint_exists"] = True

        required_names = {p.name for p in endpoint.parameters if p.required}
        provided_names = set(parameters.keys())
        missing = required_names - provided_names
        if missing:
            errors.append(f"Missing required parameters: {sorted(missing)}")
            checks["required_params_present"] = False
        else:
            checks["required_params_present"] = True

        type_errors = []
        param_by_name = {p.name: p for p in endpoint.parameters}
        for name, value in parameters.items():
            param = param_by_name.get(name)
            if param is None:
                continue  # unknown param name; not a type error per se
            if not _type_compatible(value, param.schema_type):
                type_errors.append(
                    f"Parameter '{name}' = {value!r} is not compatible with declared type "
                    f"'{param.schema_type}'"
                )
        if type_errors:
            errors.extend(type_errors)
            checks["param_types_valid"] = False
        else:
            checks["param_types_valid"] = True

        valid = all(checks.values())
        return VerificationResult(valid=valid, checks=checks, errors=errors)
