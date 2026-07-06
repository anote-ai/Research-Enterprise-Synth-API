from __future__ import annotations

from typing import Any

from .schemas import APISchema, Endpoint, Parameter

HTTP_METHODS = ("get", "post", "put", "patch", "delete", "options", "head", "trace")


def _security_scheme_names(security: list[dict[str, Any]] | None) -> list[str]:
    if not security:
        return []
    names: list[str] = []
    for requirement in security:
        for scheme_name in requirement.keys():
            if scheme_name not in names:
                names.append(scheme_name)
    return names


def _parse_parameter(raw: dict[str, Any]) -> Parameter:
    schema = raw.get("schema", {})
    return Parameter(
        name=raw.get("name", ""),
        location=raw.get("in", ""),
        required=bool(raw.get("required", False)),
        schema_type=schema.get("type") if isinstance(schema, dict) else None,
    )


def _parse_request_body(raw: dict[str, Any] | None) -> tuple[bool, bool]:
    if not raw:
        return False, False
    required = bool(raw.get("required", False))
    content = raw.get("content", {})
    schema_present = any("schema" in media for media in content.values())
    return required, schema_present


def _parse_responses(raw: dict[str, Any] | None) -> dict[str, bool]:
    if not raw:
        return {}
    result: dict[str, bool] = {}
    for status_code, response in raw.items():
        content = response.get("content", {}) if isinstance(response, dict) else {}
        result[str(status_code)] = any("schema" in media for media in content.values())
    return result


class SchemaParser:
    """Stage 1: API Schema Parser. Parses a raw OpenAPI 3.x spec dict into an APISchema."""

    def parse(self, spec: dict[str, Any]) -> APISchema:
        info = spec.get("info", {})
        global_security = _security_scheme_names(spec.get("security"))

        endpoints: list[Endpoint] = []
        for path, path_item in spec.get("paths", {}).items():
            if not isinstance(path_item, dict):
                continue
            path_level_params_raw = path_item.get("parameters", [])
            for method in HTTP_METHODS:
                if method not in path_item:
                    continue
                operation = path_item[method]
                if not isinstance(operation, dict):
                    continue

                op_params_raw = path_level_params_raw + operation.get("parameters", [])
                parameters = [
                    _parse_parameter(p) for p in op_params_raw if isinstance(p, dict) and "$ref" not in p
                ]

                req_required, req_schema_present = _parse_request_body(operation.get("requestBody"))
                response_schemas = _parse_responses(operation.get("responses"))

                if "security" in operation:
                    auth_schemes = _security_scheme_names(operation.get("security"))
                else:
                    auth_schemes = global_security

                endpoints.append(
                    Endpoint(
                        path=path,
                        method=method.upper(),
                        operation_id=operation.get("operationId"),
                        parameters=parameters,
                        request_body_required=req_required,
                        request_body_schema_present=req_schema_present,
                        response_schemas=response_schemas,
                        auth_schemes=auth_schemes,
                    )
                )

        return APISchema(
            title=info.get("title", ""),
            version=info.get("version", ""),
            endpoints=endpoints,
            global_auth_schemes=global_security,
        )
