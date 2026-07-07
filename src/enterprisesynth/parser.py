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


def _resolve_ref(spec: dict[str, Any], ref: str) -> dict[str, Any]:
    """Resolves a local JSON Schema $ref like '#/components/parameters/org' against the spec."""
    node: Any = spec
    for part in ref.lstrip("#/").split("/"):
        if not isinstance(node, dict):
            return {}
        node = node.get(part, {})
    return node if isinstance(node, dict) else {}


def _parse_parameter(raw: dict[str, Any], spec: dict[str, Any]) -> Parameter:
    if "$ref" in raw:
        raw = _resolve_ref(spec, raw["$ref"])
    schema = raw.get("schema", {})
    if isinstance(schema, dict) and "$ref" in schema:
        schema = _resolve_ref(spec, schema["$ref"])
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


def _parse_request_body_fields(raw: dict[str, Any] | None, spec: dict[str, Any]) -> list[Parameter]:
    """Parses requestBody schema properties into Parameters (location='body').

    Most POST/PUT/PATCH endpoints put their real payload fields here, not in the OpenAPI
    'parameters' array -- e.g. Stripe's /v1/charges has zero 'parameters' and puts amount,
    currency, customer, etc. entirely in requestBody.content[...].schema.properties.
    """
    if not raw:
        return []
    content = raw.get("content", {})
    schema: dict[str, Any] = {}
    for media in content.values():
        if isinstance(media, dict) and "schema" in media:
            schema = media["schema"]
            break
    if isinstance(schema, dict) and "$ref" in schema:
        schema = _resolve_ref(spec, schema["$ref"])
    if not isinstance(schema, dict):
        return []

    properties = schema.get("properties", {})
    required_fields = set(schema.get("required", []))

    fields: list[Parameter] = []
    for name, field_schema in properties.items():
        if isinstance(field_schema, dict) and "$ref" in field_schema:
            field_schema = _resolve_ref(spec, field_schema["$ref"])
        field_type = field_schema.get("type") if isinstance(field_schema, dict) else None
        fields.append(
            Parameter(
                name=name,
                location="body",
                required=name in required_fields,
                schema_type=field_type,
            )
        )
    return fields


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
                    _parse_parameter(p, spec) for p in op_params_raw if isinstance(p, dict)
                ]
                parameters += _parse_request_body_fields(operation.get("requestBody"), spec)

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
                        description=operation.get("description") or operation.get("summary"),
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
