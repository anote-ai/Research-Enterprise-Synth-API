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
