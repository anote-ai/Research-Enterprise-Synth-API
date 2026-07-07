"""Smoke tests for the four Anthropic-calling agent modules.

None of these hit a real API -- a fake client stands in for anthropic.Anthropic, exercising the
same response-parsing path every agent shares: filter response.content for text blocks, strip
markdown fences, json.loads. That filtering logic is not incidental: a real bug this project hit
was response.content sometimes starting with a non-text (thinking) block, which broke a naive
`response.content[0].text` read. These tests pin that behavior so a future refactor can't
reintroduce it silently.
"""

from enterprisesynth.ablation_agents import (
    DescriptionAwareIntentAgent,
    FullContextIntentAgent,
    NoIntentTrajectoryAgent,
)
from enterprisesynth.intent_agent import IntentSynthesisAgent
from enterprisesynth.schemas import Endpoint, Parameter
from enterprisesynth.semantic_checker import SemanticPlausibilityChecker
from enterprisesynth.trajectory_agent import TrajectoryGenerator


class _FakeBlock:
    def __init__(self, type_: str, text: str = ""):
        self.type = type_
        self.text = text


class _FakeResponse:
    def __init__(self, content):
        self.content = content


class _FakeMessages:
    def __init__(self, response: _FakeResponse):
        self._response = response

    def create(self, **kwargs):
        return self._response


class _FakeClient:
    """Duck-types anthropic.Anthropic: only `.messages.create(...)` is ever called."""

    def __init__(self, response: _FakeResponse):
        self.messages = _FakeMessages(response)


def make_endpoint() -> Endpoint:
    return Endpoint(
        path="/repos/{owner}/{repo}/issues",
        method="POST",
        operation_id="CreateIssue",
        description="Create an issue in a repository.",
        parameters=[
            Parameter(name="owner", location="path", required=True, schema_type="string"),
            Parameter(name="repo", location="path", required=True, schema_type="string"),
        ],
    )


# --- IntentSynthesisAgent -----------------------------------------------------------------


def test_intent_agent_happy_path():
    response = _FakeResponse([_FakeBlock("text", '["file a bug", "request a feature"]')])
    agent = IntentSynthesisAgent(client=_FakeClient(response))
    result = agent.generate_intents(make_endpoint(), n=2)
    assert result == ["file a bug", "request a feature"]


def test_intent_agent_skips_leading_thinking_block():
    """Pins the real bug: Claude Sonnet 5 sometimes returns a thinking block before the text
    block. A naive response.content[0].text read breaks; filtering by block.type == "text" does
    not."""
    response = _FakeResponse(
        [
            _FakeBlock("thinking", "reasoning about the request..."),
            _FakeBlock("text", '["rotate the deploy key"]'),
        ]
    )
    agent = IntentSynthesisAgent(client=_FakeClient(response))
    result = agent.generate_intents(make_endpoint(), n=1)
    assert result == ["rotate the deploy key"]


def test_intent_agent_strips_markdown_fences():
    response = _FakeResponse([_FakeBlock("text", '```json\n["lock down the repo"]\n```')])
    agent = IntentSynthesisAgent(client=_FakeClient(response))
    result = agent.generate_intents(make_endpoint(), n=1)
    assert result == ["lock down the repo"]


def test_intent_agent_malformed_json_returns_empty_list():
    response = _FakeResponse([_FakeBlock("text", "not json at all")])
    agent = IntentSynthesisAgent(client=_FakeClient(response))
    assert agent.generate_intents(make_endpoint(), n=1) == []


def test_intent_agent_non_list_json_returns_empty_list():
    response = _FakeResponse([_FakeBlock("text", '{"not": "a list"}')])
    agent = IntentSynthesisAgent(client=_FakeClient(response))
    assert agent.generate_intents(make_endpoint(), n=1) == []


# --- TrajectoryGenerator -------------------------------------------------------------------


def test_trajectory_generator_happy_path():
    payload = (
        '{"selected_method": "POST", "selected_path": "/repos/{owner}/{repo}/issues", '
        '"reasoning": "matches the request", "parameters": {"owner": "acme", "repo": "api"}, '
        '"expected_response_summary": "the created issue"}'
    )
    response = _FakeResponse([_FakeBlock("text", payload)])
    agent = TrajectoryGenerator(client=_FakeClient(response))
    result = agent.generate_trajectory("file a bug", [make_endpoint()])
    assert result["selected_method"] == "POST"
    assert result["parameters"]["owner"] == "acme"


def test_trajectory_generator_skips_leading_thinking_block():
    response = _FakeResponse(
        [
            _FakeBlock("thinking", "considering tools..."),
            _FakeBlock("text", '{"selected_method": "POST", "selected_path": "/x", "parameters": {}}'),
        ]
    )
    agent = TrajectoryGenerator(client=_FakeClient(response))
    result = agent.generate_trajectory("do a thing", [make_endpoint()])
    assert result["selected_method"] == "POST"


def test_trajectory_generator_malformed_json_returns_none():
    response = _FakeResponse([_FakeBlock("text", "garbage")])
    agent = TrajectoryGenerator(client=_FakeClient(response))
    assert agent.generate_trajectory("do a thing", [make_endpoint()]) is None


# --- Ablation agents (A1, A3, A4) ----------------------------------------------------------


def test_no_intent_trajectory_agent_happy_path():
    response = _FakeResponse(
        [_FakeBlock("text", '{"instruction": "create an issue", "parameters": {"owner": "acme"}}')]
    )
    agent = NoIntentTrajectoryAgent(client=_FakeClient(response))
    result = agent.generate(make_endpoint())
    assert result["instruction"] == "create an issue"


def test_no_intent_trajectory_agent_malformed_returns_none():
    response = _FakeResponse([_FakeBlock("text", "not json")])
    agent = NoIntentTrajectoryAgent(client=_FakeClient(response))
    assert agent.generate(make_endpoint()) is None


def test_description_aware_intent_agent_happy_path():
    response = _FakeResponse([_FakeBlock("text", '["open an issue about the outage"]')])
    agent = DescriptionAwareIntentAgent(client=_FakeClient(response))
    result = agent.generate_intents(make_endpoint(), n=1)
    assert result == ["open an issue about the outage"]


def test_full_context_intent_agent_happy_path():
    response = _FakeResponse([_FakeBlock("text", '["file an issue then assign it"]')])
    agent = FullContextIntentAgent(client=_FakeClient(response))
    other = [Endpoint(path="/repos/{owner}/{repo}/assignees", method="POST")]
    result = agent.generate_intents(make_endpoint(), other, n=1)
    assert result == ["file an issue then assign it"]


# --- SemanticPlausibilityChecker (A5) --------------------------------------------------------


def test_semantic_checker_happy_path():
    response = _FakeResponse([_FakeBlock("text", '{"plausible": true, "reason": "looks fine"}')])
    checker = SemanticPlausibilityChecker(client=_FakeClient(response))
    trajectory = {"selected_method": "POST", "selected_path": "/x", "parameters": {}}
    result = checker.check("do a thing", trajectory)
    assert result == {"plausible": True, "reason": "looks fine"}


def test_semantic_checker_skips_leading_thinking_block():
    response = _FakeResponse(
        [
            _FakeBlock("thinking", "evaluating plausibility..."),
            _FakeBlock("text", '{"plausible": false, "reason": "negative amount"}'),
        ]
    )
    checker = SemanticPlausibilityChecker(client=_FakeClient(response))
    trajectory = {"selected_method": "POST", "selected_path": "/x", "parameters": {"amount": -5}}
    result = checker.check("charge a card", trajectory)
    assert result == {"plausible": False, "reason": "negative amount"}


def test_semantic_checker_malformed_json_returns_none():
    response = _FakeResponse([_FakeBlock("text", "not json")])
    checker = SemanticPlausibilityChecker(client=_FakeClient(response))
    trajectory = {"selected_method": "POST", "selected_path": "/x", "parameters": {}}
    assert checker.check("do a thing", trajectory) is None
