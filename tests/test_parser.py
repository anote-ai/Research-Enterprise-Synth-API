import json
from pathlib import Path

import pytest

from enterprisesynth.parser import SchemaParser

SPECS_DIR = Path(__file__).resolve().parent.parent / "data" / "specs"


@pytest.fixture(scope="module")
def specs():
    result = {}
    for name, filename in [("github", "github.json"), ("stripe", "stripe.json"), ("slack", "slack.json")]:
        with open(SPECS_DIR / filename) as f:
            result[name] = json.load(f)
    return result


def test_github_endpoint_count(specs):
    schema = SchemaParser().parse(specs["github"])
    assert len(schema.endpoints) == 845


def test_stripe_endpoint_count(specs):
    schema = SchemaParser().parse(specs["stripe"])
    assert len(schema.endpoints) == 446


def test_slack_endpoint_count(specs):
    schema = SchemaParser().parse(specs["slack"])
    assert len(schema.endpoints) == 174


def test_github_has_no_declared_auth_schemes(specs):
    # Verified property of this spec: GitHub's public OpenAPI spec declares no
    # securitySchemes and no security requirements anywhere (auth is documented in prose).
    schema = SchemaParser().parse(specs["github"])
    assert schema.global_auth_schemes == []
    assert all(e.auth_schemes == [] for e in schema.endpoints)


def test_stripe_all_endpoints_have_auth(specs):
    schema = SchemaParser().parse(specs["stripe"])
    assert all(e.auth_schemes for e in schema.endpoints)


def test_parameter_required_flag_preserved(specs):
    schema = SchemaParser().parse(specs["slack"])
    total_required = sum(sum(1 for p in e.parameters if p.required) for e in schema.endpoints)
    assert total_required > 0


def test_method_is_uppercased(specs):
    schema = SchemaParser().parse(specs["github"])
    assert all(e.method == e.method.upper() for e in schema.endpoints)


def test_endpoint_description_is_parsed(specs):
    schema = SchemaParser().parse(specs["stripe"])
    endpoint = next(e for e in schema.endpoints if e.path == "/v1/charges" and e.method == "POST")
    assert endpoint.description
    assert isinstance(endpoint.description, str)


def test_request_body_fields_are_parsed(specs):
    # Regression test: Stripe's /v1/charges has zero OpenAPI 'parameters' -- amount, currency,
    # customer etc. live entirely in requestBody.content[...].schema.properties. The parser
    # used to only track a boolean "schema present" flag and never parsed these into fields.
    schema = SchemaParser().parse(specs["stripe"])
    endpoint = next(e for e in schema.endpoints if e.path == "/v1/charges" and e.method == "POST")
    param_names = {p.name for p in endpoint.parameters}
    assert "amount" in param_names
    assert "currency" in param_names
    body_params = {p.name: p for p in endpoint.parameters if p.location == "body"}
    assert body_params  # at least one body-derived field parsed
    assert all(p.location == "body" for p in body_params.values())


def test_ref_parameters_are_resolved(specs):
    # Regression test: GitHub's spec defines many parameters (org, secret-name, ...) via
    # $ref to #/components/parameters/*. The parser used to silently drop these entirely.
    schema = SchemaParser().parse(specs["github"])
    endpoint = next(
        e
        for e in schema.endpoints
        if e.path == "/orgs/{org}/actions/secrets/{secret_name}/repositories" and e.method == "PUT"
    )
    param_names = {p.name for p in endpoint.parameters}
    assert "org" in param_names
    assert "secret_name" in param_names
    org_param = next(p for p in endpoint.parameters if p.name == "org")
    assert org_param.required is True
    assert org_param.schema_type == "string"
