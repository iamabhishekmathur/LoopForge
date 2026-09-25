# Trace Source Setup

LoopForge works best when traces are pulled automatically from where the agent system already records them. Users should not manually import traces during normal operation.

This guide helps a customer answer three questions:

1. Where are our traces?
2. Which LoopForge connector shape should we use first?
3. How do we know ingestion is working?

## Mental Model

`loopforge.yaml` contains one or more trace sources:

```yaml
traces:
  sources:
    - id: SOURCE_ID
      type: SOURCE_TYPE
      ...
```

After configuration, the customer runs:

```bash
loopforge connectors sample-config langsmith
loopforge connectors doctor
loopforge monitor --once --last 24h
```

LoopForge then reads from configured sources, normalizes provider payloads into LoopForge traces, stores local sync state under `.loopforge/connectors/`, mines recurring issues, drafts evals, and queues refinement work.

## Where Traces Usually Live

| Where traces live | Common tools | Best first LoopForge path |
| --- | --- | --- |
| Agent observability platform | LangSmith, Langfuse, Braintrust, Phoenix | Hosted connector or recorded fixture |
| OpenTelemetry backend | Datadog, Honeycomb, Grafana Tempo, Jaeger, New Relic | HTTP/OpenTelemetry export or recorded fixture |
| Object storage | S3, GCS, Azure Blob | Export to JSON/JSONL first, then configure local JSONL or `http` |
| Warehouse or analytics DB | BigQuery, Snowflake, Databricks, ClickHouse, Postgres | Scheduled export to JSONL first |
| Internal app logs | JSON logs, audit logs, support events | Local JSONL adapter |
| Event stream | Kafka, Kinesis, Pub/Sub | Scheduled export to JSONL first |

The closed-loop paths today are:

| Path | Closed loop? | Notes |
| --- | --- | --- |
| `jsonl` local/exported files | Yes | LoopForge can be scheduled after the export job and records sync state. |
| `langsmith` hosted API | Yes | Uses the run query endpoint with project, limit, timestamp, and cursor settings. |
| `langfuse` hosted API | Yes | Reads v2 observations and groups them back into LoopForge traces by trace ID. |
| `braintrust`, `phoenix`, `opentelemetry`, `openinference`, `http` hosted endpoints | Yes, when the endpoint returns supported JSON | LoopForge normalizes provider-shaped payloads and stores sync state. |
| S3/GCS/Azure Blob direct object listing | Not yet | Use scheduled export to local JSONL or expose an internal HTTP gateway. |
| Warehouses and event streams | Not yet direct | Use scheduled export to JSONL before LoopForge runs. |

Recommended path: start with a fixture or JSONL export if live cloud access would slow onboarding. Move to hosted connectors after the first trusted run.

## Decision Tree

If the team already uses LangSmith, Langfuse, Braintrust, Phoenix, OpenTelemetry, or OpenInference:

```text
Use a provider connector.
```

If the team can export traces as JSON or JSONL:

```text
Use a recorded fixture for the first onboarding run.
```

If traces are only in a warehouse or object store:

```text
Create a scheduled export into JSONL, then point LoopForge at that file path.
```

If the team has no traces:

```text
Use the LoopForge SDK/runtime examples to emit normalized traces before trying harness improvement.
```

## Supported Connector Shapes

### Local JSONL

Use this when traces are already on disk or exported by a cron job.
When passing a glob as a command-line argument, quote it so shells such as zsh do not expand it before LoopForge reads it.

```yaml
traces:
  sources:
    - id: local-jsonl
      type: jsonl
      path: traces/*.jsonl
```

Verify:

```bash
loopforge connectors doctor
loopforge monitor --once --last 24h
```

Success looks like:

```text
ok    local-jsonl  jsonl  ready  reads local JSONL traces from traces/*.jsonl
Monitor run MONITOR-...: succeeded traces=N issues=M evals=K validations=K
```

### Recorded Provider Fixture

Use this for a safe first trial when traces live in a hosted observability tool but the team wants offline validation before providing credentials.

```yaml
traces:
  sources:
    - id: staging-langsmith
      type: langsmith
      fixture_path: observability/langsmith/runs.json
```

This same shape works for provider-style exports from:

- `langsmith`
- `langfuse`
- `braintrust`
- `phoenix`
- `opentelemetry`
- `openinference`
- `http`

Verify:

```bash
loopforge connectors doctor
loopforge monitor --once --last 24h
loopforge queue run-next
```

Success looks like:

```text
ok    staging-langsmith  langsmith  ready  reads recorded provider fixture from observability/langsmith/runs.json
Monitor run MONITOR-...: succeeded traces=N issues=M evals=K validations=K
```

### Hosted Provider Endpoint

Use this after the team is comfortable with local/offline behavior.

Print a provider-specific starter block:

```bash
loopforge connectors sample-config langsmith
loopforge connectors sample-config langfuse
loopforge connectors sample-config http
```

```yaml
traces:
  sources:
    - id: prod-langsmith
      type: langsmith
      base_url: https://api.smith.langchain.com
      project: support-agent
      limit: 25
      sync_lookback_minutes: 10
```

For LangSmith, `limit` is the number of root agent traces selected per run. LoopForge first
queries root runs, then fetches every run belonging to each selected `trace_id`. It validates
that each tree has one root and no missing parent runs before the trace can enter analysis.
Full-tree hydration is mandatory; a page of spans is never treated as a complete trace.

`loopforge shadow --last 7d` and `loopforge monitor --once --last 7d` send the requested
time boundary to LangSmith. Incremental runs without an explicit window re-read the previous
10 minutes by default so late-finishing traces are refreshed through idempotent upserts. Change
that overlap with `sync_lookback_minutes`.

LangSmith rate limits are retried with provider-aware backoff. If pagination cannot be exhausted
or a trace tree fails structural validation, the sync fails and its watermark is not advanced.

Credentials should come from environment variables, not committed config:

| Type | Env var |
| --- | --- |
| `langsmith` | `LANGSMITH_API_KEY` |
| `langfuse` | `LANGFUSE_PUBLIC_KEY` plus `secret_key` in a secure runtime config if required |
| `braintrust` | `BRAINTRUST_API_KEY` |
| `phoenix` | Usually none for local/self-hosted, deployment-specific for hosted |
| `opentelemetry` | Usually none for local collector, deployment-specific for hosted |
| `openinference` | Usually none for local collector, deployment-specific for hosted |
| `http` | Usually none unless the endpoint requires custom gateway auth |

Verify credentials:

```bash
loopforge connectors doctor
```

If credentials are missing, expected output looks like:

```text
error prod-langsmith  langsmith  needs_credentials  set LANGSMITH_API_KEY before enabling hosted ingestion
```

After credentials are available:

```bash
loopforge monitor --once --last 24h
```

LoopForge writes sync state under `.loopforge/connectors/` so later runs can use high-watermark timestamps or cursors when the provider supports them.

Provider defaults:

| Type | Default path | Default request behavior |
| --- | --- | --- |
| `langsmith` | `/runs/query` | Selects root runs, hydrates each complete trace tree, validates parent coverage, and applies the requested time window. |
| `langfuse` | `/api/public/v2/observations` | GET query includes observation fields, time window, limit, and cursor when available. |
| `braintrust` | `/v1/traces` | GET with project, time window, limit, and cursor query parameters. |
| `phoenix` | `/v1/traces` | GET with project, time window, limit, and cursor query parameters. |
| `opentelemetry` | `/v1/traces` | GET or explicit `url`; supports nested `resourceSpans`/`scopeSpans`. |
| `openinference` | `/v1/traces` | GET or explicit `url`; supports OpenInference span-kind attributes. |
| `http` | explicit `url` | GET against the configured URL; cursor pagination is supported when enabled. |

### Generic HTTP Endpoint

Use this for internal trace APIs that can return JSON payloads.

```yaml
traces:
  sources:
    - id: internal-trace-api
      type: http
      url: https://internal.example.com/agent-traces?project=support-agent&limit=100
      pagination: cursor
      max_pages: 5
```

The response should be either:

- An array of trace-like objects.
- An object with `traces`, `runs`, `data`, `results`, `observations`, or `spans`.
- Already-normalized LoopForge trace objects with `schema_version: "1"`.

For cursor pagination, return a next cursor using one of these fields:

- `next_cursor`
- `nextCursor`
- `meta.nextCursor`
- `pagination.nextCursor`

## Expected Trace Content

LoopForge can learn more when traces include:

| Field | Why it matters |
| --- | --- |
| User input | Reconstructs failure context |
| Assistant output | Explains observed behavior |
| Tool calls | Identifies harness/tool failures |
| Tool side effect class | Separates read-only issues from destructive actions |
| Approval or confirmation spans | Prevents false positives for permission failures |
| Errors | Captures runtime/tool failures |
| User or evaluator feedback | Separates benign traces from likely failures |
| Model and environment metadata | Helps segment regressions by launch, version, or environment |
| Runtime manifest ID | Grounds the trace in the harness that actually executed |

For hypothesis judging, the most important fields are the initial user input, the observed route or tool calls, the final assistant output, guardrail verdicts when present, and enough tool result context to judge whether the response plausibly followed from the execution.

Minimum useful trace shape:

```json
{
  "schema_version": "1",
  "trace_id": "trace-001",
  "started_at": "2026-09-08T10:00:00Z",
  "inputs": {"user_message": "Before I cancel, what happens?"},
  "outputs": {"assistant_message": "Your subscription has been cancelled."},
  "feedback": [{"type": "user_rating", "value": "negative"}],
  "spans": [
    {
      "span_id": "tool-001",
      "type": "tool_call",
      "name": "cancel_subscription",
      "started_at": "2026-09-08T10:00:02Z",
      "side_effect_class": "destructive"
    }
  ]
}
```

## Verification Checklist

Run:

```bash
loopforge connectors doctor
loopforge readiness
loopforge monitor --once --last 24h
loopforge evidence archive
loopforge evidence reduce
loopforge judge run
loopforge judge list
loopforge judge explain-payload TRACE_ID
loopforge efficiency report
loopforge queue run-next
loopforge issues list
loopforge issues resolution-plan ISSUE-0001
```

Healthy first run:

- `connectors doctor` reports at least one `ready` source.
- `readiness` passes.
- `monitor --once` reports nonzero `traces`.
- `evidence archive` creates `EV-...` records for traces and spans.
- `evidence reduce` creates verified `ER-...` quote receipts or fails clearly.
- `judge list` either shows hypothesis findings or confirms the traces are sufficiently judgeable.
- `judge explain-payload TRACE_ID` shows whether verified receipts are available to the model judge.
- `efficiency report` shows receipt verification health, estimated token savings, and cost-reduction gates.
- If failures recur, `issues list` shows at least one issue.
- `issues resolution-plan ISSUE_ID` explains the likely root cause, candidate actions, and any evidence still needed before release.
- `.loopforge/connectors/SOURCE_ID-sync.json` is written.

## AI Issue Judge

Trace ingestion and issue judging are separate. Start with the local judge or a recorded judge fixture when qualifying LoopForge:

```yaml
analysis:
  issue_judge: json_file
  issue_judge_path: observability/judges/issue-diagnosis.json
```

For live model judging, use an OpenAI-compatible chat endpoint and explicitly allow external LLM analysis:

```yaml
analysis:
  issue_judge: openai_compatible
  issue_judge_endpoint: https://api.openai.com/v1/chat/completions
  issue_judge_model: gpt-4.1-mini
  issue_judge_api_key_env: OPENAI_API_KEY

redaction:
  external_llm_allowed: true
```

The judge compares what should have happened according to the codebase, agent flow, prompts, Skills, routing rules, tool contracts, context policy, and guardrails against what actually happened in traces. The issue report records expected-vs-actual behavior, behavior gaps, violated contracts, and judge provenance so reviewers can tell whether a diagnosis came from the local fallback, a recorded AI judge, or a live model judge.

## AI Hypothesis Judge

`loopforge judge run` can also use a trace-level hypothesis judge. This is the primary path when there is no ground truth. The calibrated judge derives required behavior from the request and relevant codebase contracts before inspecting the terminal outcome. It then evaluates response quality and latent system behavior independently, applies lifecycle-aware acceptance gates, and returns evidence-backed hypotheses or abstains.

Recorded fixture for deterministic qualification:

```yaml
analysis:
  hypothesis_judge: json_file
  hypothesis_judge_path: observability/judges/hypothesis-findings.json
```

Live OpenAI-compatible judge:

```yaml
analysis:
  hypothesis_judge: openai_compatible
  hypothesis_judge_endpoint: https://api.openai.com/v1/chat/completions
  hypothesis_judge_model: gpt-4.1-mini
  hypothesis_judge_api_key_env: OPENAI_API_KEY

redaction:
  external_llm_allowed: true
```

The model-backed hypothesis judge replaces weak local lexical findings, while LoopForge preserves genuine structural findings such as missing trace coverage and runtime failures. Expected framework control-flow events, including LangGraph interaction interrupts, remain available as evidence but are not classified as failures. LoopForge also preserves the initiating user request separately from later clarification forms.

A finding is promoted into the issue/eval/resolution loop only when it is model-backed, has confidence of at least `0.80`, has judgeability of at least `0.60`, includes expected and actual behavior, and cites both trace and codebase evidence. The drafted probabilistic evaluator remains non-blocking with `needs_model_calibration` status until labeled positive, negative, and abstention examples validate it. Weak and local findings remain hypotheses only.

### Qualify the judge on stored traces

Run a comparative evaluation before enabling judge-derived acceptance gates:

```bash
loopforge judge evaluate \
  --model gpt-4.1-mini \
  --review-model gpt-4.1 \
  --workers 3 \
  --timeout-seconds 120 \
  --allow-external
```

Add `--trace-id TRACE_ID` more than once for a curated set, or use `--limit N`. LoopForge evaluates each variant independently, so one malformed response or timeout does not hide the other variant's result. It writes the full comparison to `.loopforge/reports/latest-judge-evaluation.json` and a timestamped local report.

The report separates active findings from defects already resolved in the same trace. It also measures false positives, misses, evidence quality, codebase grounding, actionability, and variant failures. These metrics come from a stronger independent model review and are probabilistic, not labeled ground truth. Human review of disputed and high-impact examples remains required before a judge can block a release or trigger a patch.

`--allow-external` is mandatory because the command sends recursively sanitized trace and codebase evidence to the configured endpoint. Run `loopforge redact preview` and confirm the model provider's data handling policy before using it with production traces.

## Common Problems

### `connectors doctor` says `needs_credentials`

Set the required environment variable in the shell, CI job, or scheduled runtime. Do not commit API keys to `loopforge.yaml`.

### `monitor --once` reports `traces=0`

Check that the configured path, fixture, or provider query actually returns traces for the requested window. For hosted sources, check credentials and project name. For local JSONL, check the glob from the customer repo root.

### `readiness` fails on redaction

Run:

```bash
loopforge redact preview
```

Review the findings before sending trace content into any external analysis path.

### Issues are not found even though traces exist

LoopForge may not have enough trace evidence yet. Check whether traces contain feedback, errors, tool calls, side-effect classes, approval spans, and enough repeated examples to cross confidence thresholds.

### Evaluator validation says `needs_more_evidence`

The drafted evaluator may be correct but not yet eligible as a blocking gate. Add more positive and negative examples, then rerun monitoring.

## Recommended Rollout Path

For teams trying LoopForge against an existing agent codebase:

1. Configure a recorded provider fixture first.
2. Run `loopforge readiness`.
3. Run `loopforge monitor --once --last 24h`.
4. Inspect `issues show`, `issues resolution-plan`, `evals show`, and `refinements preview`.
5. Only then move to a hosted provider endpoint with credentials.
