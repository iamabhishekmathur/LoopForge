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

MVP guidance: start with a fixture or JSONL export if live cloud access would slow onboarding. Move to hosted connectors after the first trusted run.

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

```yaml
traces:
  sources:
    - id: prod-langsmith
      type: langsmith
      base_url: https://api.smith.langchain.com
      project: support-agent
      limit: 100
```

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

### Generic HTTP Endpoint

Use this for internal trace APIs that can return JSON payloads.

```yaml
traces:
  sources:
    - id: internal-trace-api
      type: http
      url: https://internal.example.com/agent-traces?project=support-agent&limit=100
```

The response should be either:

- An array of trace-like objects.
- An object with `traces`, `runs`, `data`, `results`, `observations`, or `spans`.
- Already-normalized LoopForge trace objects with `schema_version: "1"`.

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
loopforge queue run-next
loopforge issues list
```

Healthy first run:

- `connectors doctor` reports at least one `ready` source.
- `readiness` passes.
- `monitor --once` reports nonzero `traces`.
- If failures recur, `issues list` shows at least one issue.
- `.loopforge/connectors/SOURCE_ID-sync.json` is written.

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

## Recommended Internal-Onboarding Path

For internal users trying LoopForge against an existing customer-style codebase:

1. Configure a recorded provider fixture first.
2. Run `loopforge readiness`.
3. Run `loopforge monitor --once --last 24h`.
4. Inspect `issues show`, `evals show`, and `refinements preview`.
5. Only then move to a hosted provider endpoint with credentials.
