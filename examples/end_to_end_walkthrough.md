# End-to-End Walkthrough: One Real Example

A single case, followed through all four implemented pipeline stages, pulled directly from
committed `data/generated/*.json` — nothing here is invented for illustration.

## 1. Input: the OpenAPI endpoint (Stage 1 — Schema Parser)

From GitHub's real spec (`data/specs/github.json`):

```
POST /repos/{owner}/{repo}/tags/protection
operation_id: (repos/create-tag-protection)
parameters: owner (path, required, string), repo (path, required, string)
requestBody field: pattern (required, string)
```

## 2. Generated intent (Stage 2 — Intent Generation Agent)

```
"Set up a rule so only admins can push release tags matching v*.* on our payments-service repo
to prevent accidental overwrites in production."
```

Two other intents generated for the same endpoint (from `data/generated/experiment2_intents.json`),
showing scenario diversity rather than rewording:

```
"We need to lock down tag creation on the acme-api repository so that our CI pipeline can't be
tampered with—please add tag protection for anything prefixed with 'release-'."

"Can you configure our infrastructure-as-code repo so that deployment tags like 'prod-*' can only
be created or deleted by repository admins going forward?"
```

## 3. Generated trajectory (Stage 3 — Trajectory Generation Agent)

Given the intent above plus a 15-endpoint candidate list (5 source + 10 distractors), the agent
produced (from `data/generated/experiment3_trajectories.json`):

```json
{
  "selected_method": "POST",
  "selected_path": "/repos/{owner}/{repo}/tags/protection",
  "reasoning": "This tool creates a tag protection rule for a repository restricting who can push matching tags, which aligns with restricting release tag pushes to admins only.",
  "parameters": {
    "owner": "your-org",
    "repo": "payments-service",
    "pattern": "v*.*"
  },
  "expected_response_summary": "Returns the newly created tag protection rule object, including its id, pattern, and creation timestamp, confirming that pushes to matching tags are now restricted."
}
```

Correctly selected the target endpoint out of 15 candidates and extracted "payments-service" and
"v*.*" directly from the free-text intent into the right parameter slots.

## 4. Verification (Stage 4 — Schema Verification Engine)

**The real trajectory above passes** (from `data/generated/experiment4_verification.json`):

```json
{
  "valid": true,
  "checks": {
    "endpoint_exists": true,
    "required_params_present": true,
    "param_types_valid": true
  },
  "errors": []
}
```

**A deliberately corrupted variant of the same trajectory (method changed `POST` → `PATCH`) is
correctly rejected:**

```json
{
  "valid": false,
  "checks": {
    "endpoint_exists": false,
    "required_params_present": false,
    "param_types_valid": false
  },
  "errors": [
    "Endpoint PATCH /repos/{owner}/{repo}/tags/protection does not exist in the spec."
  ]
}
```

This pair (real trajectory passes, corrupted trajectory rejected) is exactly what Experiment 4
tests at scale (44 corrupted variants, 98% (43/44) caught after fixing four real bugs, with one
planted type-mismatch case still missed — see `RESULTS.md`).

## Where this data comes from

- Endpoint definition: `data/specs/github.json` (real, committed GitHub OpenAPI spec)
- Intent: `data/generated/experiment2_intents.json`
- Trajectory: `data/generated/experiment3_trajectories.json`
- Verification: `data/generated/experiment4_verification.json`

Reproduce this exact case: `./.venv/bin/python scripts/run_experiment3.py` (regenerates
trajectories for the same seeded endpoint sample) and
`./.venv/bin/python scripts/run_experiment4.py` (re-verifies + re-corrupts them).
