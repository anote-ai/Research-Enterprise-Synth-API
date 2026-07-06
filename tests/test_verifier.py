from enterprisesynth.schemas import APISchema, Endpoint, Parameter
from enterprisesynth.verifier import SchemaVerificationEngine


def make_schema() -> APISchema:
    endpoint = Endpoint(
        path="/v1/subscription_items/{item}",
        method="DELETE",
        operation_id="DeleteSubscriptionItem",
        parameters=[Parameter(name="item", location="path", required=True, schema_type="string")],
    )
    charge_endpoint = Endpoint(
        path="/v1/charges",
        method="POST",
        operation_id="CreateCharge",
        parameters=[
            Parameter(name="amount", location="query", required=True, schema_type="integer"),
            Parameter(name="currency", location="query", required=True, schema_type="string"),
        ],
    )
    return APISchema(title="test", version="1.0", endpoints=[endpoint, charge_endpoint])


def test_valid_trajectory_passes():
    engine = SchemaVerificationEngine(make_schema())
    result = engine.verify("DELETE", "/v1/subscription_items/{item}", {"item": "si_123"})
    assert result.valid is True


def test_nonexistent_endpoint_fails():
    engine = SchemaVerificationEngine(make_schema())
    result = engine.verify("GET", "/v1/subscription_items/{item}", {"item": "si_123"})
    assert result.valid is False
    assert result.checks["endpoint_exists"] is False


def test_missing_required_param_fails():
    engine = SchemaVerificationEngine(make_schema())
    result = engine.verify("POST", "/v1/charges", {"currency": "usd"})
    assert result.valid is False
    assert result.checks["required_params_present"] is False


def test_wrong_param_type_fails():
    engine = SchemaVerificationEngine(make_schema())
    result = engine.verify("POST", "/v1/charges", {"amount": "not-a-number", "currency": "usd"})
    assert result.valid is False
    assert result.checks["param_types_valid"] is False


def test_numeric_string_amount_is_ok():
    engine = SchemaVerificationEngine(make_schema())
    result = engine.verify("POST", "/v1/charges", {"amount": "1250", "currency": "usd"})
    assert result.valid is True


def test_object_value_for_string_param_fails():
    # Regression test: a nested object is not a valid value for a declared "string" param,
    # even though the original _type_compatible logic used to accept anything for "string".
    engine = SchemaVerificationEngine(make_schema())
    result = engine.verify(
        "DELETE", "/v1/subscription_items/{item}", {"item": {"unexpectedly": "an object"}}
    )
    assert result.valid is False
    assert result.checks["param_types_valid"] is False
