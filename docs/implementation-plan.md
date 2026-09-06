# LoopForge Implementation Plan

Status: Draft 0.1
Date: 2026-09-06

This plan converts the product spec, engineering design, and LangSmith Engine delta plan into buildable work. The principle is to build a thin but real closed loop before adding broad adapter coverage or UI polish.

## 1. Build Strategy

LoopForge should be implemented as a local-first CLI and library first, with every major product claim exercised by fixtures:

```text
fixture agent repo
  -> fixture traces
  -> discovery
  -> trajectory screening
  -> issue lifecycle
  -> eval example generation
  -> evaluator validation record
  -> report / local patch bundle
```

The first release should optimize for:

- Automatic trace ingestion from configured sources.
- AI-drafted issue, eval, and patch artifacts.
- Probabilistic discovery and diagnosis.
- Contractual checks where behavior is objectively knowable.
- Canonical ontology IDs.
- Strong evaluator validation before blocking gates.
- Local artifacts that can later flow into GitHub, GitLab, Slack, LangSmith, Langfuse, Phoenix, Braintrust, or CI.

## 2. Repository Shape

Target repo structure:

```text
loopforge/
  __init__.py
  cli.py
  config.py
  db.py
  models/
    trace.py
    trace_trajectory.py
    issue.py
    issue_event.py
    harness_artifact.py
    runtime_manifest.py
    eval_example.py
    evaluator_definition.py
    evaluator_validation.py
    gate_report.py
    webhook_event.py
  adapters/
    base.py
    jsonl.py
    langsmith.py
  discovery/
    scanner.py
    classifier.py
    index.py
  trajectories/
    builder.py
    screener.py
  issues/
    store.py
    lifecycle.py
    recurrence.py
    report.py
  evals/
    generator.py
    validator.py
    registry.py
    exporters/
      promptfoo.py
      langsmith.py
  patching/
    planner.py
    generator.py
    bundle.py
  gates/
    runner.py
    checks.py
  runtime/
    manifest.py
schemas/
fixtures/
  support-agent/
  traces/
tests/
```

Packaging:

- Use `pyproject.toml`.
- Use `typer` for CLI.
- Use `pydantic` for runtime models.
- Use SQLite through the standard library for MVP.
- Keep model-provider calls behind an interface so CI can use deterministic test doubles.

## 3. Phase 0: Product Contract Lock

Goal: add the missing schemas and fixture targets before feature code.

### 3.1 Add Missing Schemas

Add:

- `schemas/issue-event.schema.json`
- `schemas/trace-trajectory.schema.json`
- `schemas/eval-example.schema.json`
- `schemas/evaluator-definition.schema.json`
- `schemas/webhook-event.schema.json`

Acceptance criteria:

- All schemas parse with `python -m json.tool`.
- Required IDs are explicit.
- Every schema includes `schema_version`.
- Issue/event/eval objects reference canonical ontology IDs where applicable.

### 3.2 Add Agent Profile Template

Add:

- `templates/agent-profile.md`

Sections:

- Agent purpose.
- User workflows.
- Runtime architecture.
- Harness summary.
- Trace shape guide.
- Ontology priorities.
- Known failure patterns.
- Reviewer preferences.
- Trust qualification.
- Observability gaps.

Acceptance criteria:

- `loopforge init` can copy or generate this file into `.loopforge/agent-profile.md`.
- The profile is treated as generated project context, not source of truth.

### 3.3 Add Support-Agent Fixture

Add a small fake support-agent harness:

```text
fixtures/support-agent/
  harness/
    system.md
    tools/cancel_subscription.yaml
    permissions.yaml
  evals/
    datasets/subscription.jsonl
  loopforge.yaml
fixtures/traces/support-agent-cancellation.jsonl
```

Seeded failure:

```text
User asks to understand cancellation/options.
Agent calls cancel_subscription before explicit confirmation.
```

Acceptance criteria:

- The fixture contains at least 10 traces.
- At least 5 traces exhibit the seeded failure.
- At least 3 traces are clean counterexamples.
- At least 2 traces are ambiguous and should lower confidence.

## 4. Phase 1: Local Closed-Loop Spine

Goal: make `loopforge shadow --last 24h` produce a useful local issue report from JSONL.

### 4.1 Scaffold Package And CLI

Commands:

```text
loopforge init
loopforge connect
loopforge doctor
loopforge discover
loopforge shadow
loopforge issues list
loopforge issues show ISSUE_ID
```

Acceptance criteria:

- CLI installs locally in editable mode.
- Commands have useful `--help`.
- Commands return non-zero on invalid config.
- No network dependency for fixture tests.

### 4.2 Config Loader

Implement:

- `loopforge.yaml` parsing.
- Defaults for local JSONL.
- Analysis budget config.
- Monitor schedule config.
- Autonomy level config.
- Redaction config.

Acceptance criteria:

- Missing config gets sensible defaults after `init`.
- Invalid config errors point to exact fields.
- `loopforge doctor` reports config health.

### 4.3 SQLite Store

Tables:

- `traces`
- `trace_spans`
- `trace_trajectories`
- `runtime_manifests`
- `harness_artifacts`
- `issues`
- `issue_events`
- `issue_evidence`
- `eval_examples`
- `evaluator_definitions`
- `evaluator_validation_records`
- `gate_reports`

Acceptance criteria:

- Store can be recreated from local artifacts.
- Inserts are idempotent by stable IDs.
- All state transitions are evented.

### 4.4 JSONL Adapter

Implement:

- `TraceAdapter` base class.
- `JsonlTraceAdapter`.
- Cursor/watermark support.
- Native metadata preservation.
- Trace schema validation.

Acceptance criteria:

- Fixture traces ingest without loss of span hierarchy.
- Bad JSONL rows are reported with line numbers.
- Adapter can re-run without duplicating traces.

### 4.5 Trace Trajectory Builder

Implement compact trace summaries:

- Role/tool skeleton.
- Tool names.
- Error markers.
- Token/cost/latency summaries.
- Feedback summaries.
- Side-effect classes.
- Runtime manifest ID.
- Evidence pointers back to spans.

Acceptance criteria:

- Build trajectories for all fixture traces.
- Detect repeated tool loops structurally.
- Preserve enough references for later evidence rendering.

### 4.6 Discovery And Harness Index V0

Implement:

- Repository inventory.
- Parse known Markdown/YAML/JSON files.
- Probabilistic artifact classifier interface.
- Deterministic test double for CI fixtures.
- Harness graph store.

Acceptance criteria:

- Fixture system prompt, tool schema, permission policy, eval dataset, and config are discovered.
- Every artifact has confidence and evidence.
- Discovery does not rely on filename-only assumptions in the production interface.

### 4.7 Issue Store And Lifecycle

Implement:

- Candidate issue creation.
- Open/ignored/resolved/reopened state transitions.
- Issue evidence links.
- Recurrence matcher.
- Markdown issue report generation.

Acceptance criteria:

- Seeded cancellation traces produce one issue.
- Clean traces are not attached as positive evidence.
- Ambiguous traces are represented as uncertainty or counterexamples.
- Resolved issues reopen on recurrence.

## 5. Phase 2: Eval And Evaluator Validation Spine

Goal: every high-confidence issue produces an eval candidate and validation record.

### 5.1 Eval Example Schema And Generator

Implement assertion-first examples:

- `forbidden_tool_call`
- `requires_confirmation_before_tool`
- `semantic_response_requirement`
- `output_schema`
- `grounding_requirement`
- `latency_budget`
- `cost_budget`

Acceptance criteria:

- Seeded issue generates an eval example forbidding premature cancellation.
- Generated assertions cite source traces.
- Export format is stable YAML/JSONL.

### 5.2 Evaluator Definition Registry

Implement:

- Evaluator definitions.
- Attachments to datasets, trace sources, and CI suites.
- Versioning and hashes.
- Local registry commands.

Commands:

```text
loopforge evals list
loopforge evals show EVAL_ID
loopforge evals export --format promptfoo
```

Acceptance criteria:

- Evaluator definitions are separate from validation records.
- Evaluators can be provisional without being blocking.

### 5.3 Evaluator Validation Runner

Implement:

- Positive/negative examples.
- False-positive and false-negative tracking.
- Train/dev/test split metadata.
- TPR/TNR.
- Precision/recall.
- Confidence intervals where sample size permits.
- `pass^k` reliability and reset replay fields.
- Blocking eligibility decision.

Acceptance criteria:

- No LLM judge becomes blocking without a validation record.
- Low sample size produces `needs_more_evidence`.
- Fixture evaluator passes validation only when it catches seeded failures and avoids clean counterexamples.

## 6. Phase 3: Patch And Gate Spine

Goal: produce safe local patch bundles after issue/eval validation works.

### 6.1 Diagnosis Engine

Implement:

- Evidence bundle assembly.
- Root-cause hypotheses.
- Codebase/harness grounding.
- Competing hypotheses.
- Recommended patch layers.

Acceptance criteria:

- Cancellation fixture recommends tool description or permission policy.
- It does not recommend a broad system prompt change when a targeted artifact is available.
- Weak grounding blocks behavior PR eligibility.

### 6.2 Patch Planner And Generator

Implement:

- Markdown patching.
- YAML patching.
- Eval dataset patching.
- Patch bundles.
- Rollback notes.

Acceptance criteria:

- Patch bundle contains unified diff, rationale, evals, risk, rollback, and gate plan.
- Patches stay within configured allowlist.
- Every behavior patch includes eval changes.

### 6.3 Gate Runner

Implement checks:

- Schema validation.
- Patch scope.
- Grounding.
- Runtime manifest coverage.
- Evaluator validation.
- Replay safety.
- Target issue replay.
- Core regression suite.
- Cost/latency budget.

Acceptance criteria:

- Bad patch fixtures fail.
- Seeded targeted patch passes.
- Unknown side-effect tools fail closed.

## 7. Phase 4: GitHub And Notification Workflow

Goal: turn local artifacts into team workflows.

### 7.1 GitHub PR Writer

Commands:

```text
loopforge pr --eval-only ISSUE_ID
loopforge pr --patch PATCH_ID
```

Acceptance criteria:

- Eval-only PR can open without behavior patch.
- Behavior PR requires passing gates.
- PR body includes evidence, evals, validation records, gates, rollback, and residual risk.
- Branch names follow `loopforge/ISSUE-ID/slug`.

### 7.2 Webhook Event Bus

Implement:

- Event schema.
- HMAC signing.
- Retry envelope.
- Dedupe ID.
- Severity/type filters.

Events:

- `issue.created`
- `issue.updated`
- `issue.trace_added`
- `issue.reopened`
- `patch.candidate_created`
- `gate.completed`
- `monitor.run_failed`
- `trust_qualification.failed`

Acceptance criteria:

- Webhook payloads are signed over raw body bytes.
- Consumers can safely ignore unknown event types.
- Retries use stable event IDs.

## 8. Phase 5: LangSmith Compatibility

Goal: make LangSmith users an adoption path.

Implement:

- `LangSmithTraceAdapter`.
- Feedback ingestion.
- Run URL preservation.
- Dataset export.
- Optional evaluator result import.

Commands:

```text
loopforge connect --source langsmith
loopforge ingest --source langsmith
loopforge evals export --format langsmith
```

Acceptance criteria:

- Detect LangSmith environment variables.
- Import traces without manual export files when API access is configured.
- Issue reports deep-link to LangSmith runs.
- Generated eval examples can be exported into LangSmith-compatible dataset JSON.

## 9. Phase 6: Stack-Neutral Adapter Expansion

Goal: make portability real.

Adapters:

- OpenTelemetry/OpenInference.
- Langfuse.
- Phoenix.
- Braintrust where API access permits.

Acceptance criteria:

- Adapter conformance suite verifies span hierarchy, feedback, cost, latency, run URLs, side-effect metadata, and runtime manifest linkage.
- Same fixture failure can be represented through at least three adapter formats.

## 10. Phase 7: Local Review UI

Goal: close product-review ergonomics after the loop works.

Build a local read-only UI over the same store:

- Issue board.
- Issue detail.
- Evidence traces.
- Eval candidates.
- Evaluator validation records.
- Gate reports.
- Monitor status and budgets.

Acceptance criteria:

- User can review a full issue-to-eval-to-patch loop without opening raw JSON.
- UI never becomes the source of truth.

## 11. First Ten PRs

### PR 1: Project Skeleton

- `pyproject.toml`
- `loopforge/__init__.py`
- `loopforge/cli.py`
- basic `loopforge --help`
- test runner setup

Done when:

- `python -m loopforge --help` works.
- `pytest` runs.

### PR 2: Missing Schemas

- Issue event schema.
- Trace trajectory schema.
- Eval example schema.
- Evaluator definition schema.
- Webhook event schema.
- JSON schema validation test.

Done when:

- All schemas parse.
- Tests validate minimal example objects.

### PR 3: Config And Init

- `loopforge init`
- `loopforge.yaml` writer.
- `.loopforge/` directory creation.
- Agent profile template.

Done when:

- Running init in an empty repo creates inspectable local config and profile files.

### PR 4: SQLite Store

- Store initialization.
- Migration table.
- Core tables.
- Idempotent upserts.

Done when:

- Store can create and query traces, trajectories, issues, and events.

### PR 5: JSONL Adapter

- Adapter base.
- JSONL ingestion.
- Cursor support.
- Trace validation.

Done when:

- Fixture traces ingest and re-ingest idempotently.

### PR 6: Trace Trajectories

- Trajectory model.
- Builder.
- Loop/error/feedback signals.

Done when:

- Fixture traces produce compact trajectories with evidence pointers.

### PR 7: Support-Agent Fixture

- Fake harness.
- Seeded traces.
- Expected issue golden file.

Done when:

- Fixture is realistic enough to test discovery, issue mining, eval generation, and patch planning.

### PR 8: Discovery V0

- Scanner.
- Artifact classifier interface.
- Test double.
- Harness index persistence.

Done when:

- Fixture artifacts are discovered with confidence/evidence.

### PR 9: Issue Lifecycle V0

- Issue store.
- Candidate/open/ignored/resolved/reopened transitions.
- Recurrence matching.
- Markdown report.

Done when:

- Seeded traces create one canonical issue and a readable report.

### PR 10: Shadow Command

- `loopforge shadow --last 24h`
- Runs ingest, trajectory build, discovery, issue creation, report generation.

Done when:

- One command produces the first useful local report from fixture traces.

## 12. Testing Plan

Test classes:

- Schema tests.
- Config tests.
- Adapter conformance tests.
- Store idempotency tests.
- Discovery golden tests.
- Trajectory golden tests.
- Issue clustering golden tests.
- Evaluator validation tests.
- Gate rejection tests.
- Security prompt-injection tests.

Golden fixture targets:

- Premature destructive tool call.
- Repeated tool loop.
- Incorrect tool args.
- Silent tool error.
- Context omission.
- Grounding/source failure.
- Safe clean traces.
- Ambiguous traces that should not produce high-confidence patches.

## 13. Definition Of Working

LoopForge "works" for the first milestone when this passes:

```text
loopforge init
loopforge connect --source jsonl --path fixtures/traces/support-agent-cancellation.jsonl
loopforge discover
loopforge shadow --last 24h
loopforge issues list
loopforge issues show ISSUE_ID
```

Expected result:

- One high-confidence issue for premature cancellation.
- Canonical ontology IDs assigned.
- Evidence traces linked.
- Clean counterexamples excluded.
- Ambiguous traces lower confidence.
- Generated eval candidate exists.
- Evaluator validation record exists, even if provisional.
- Markdown report explains evidence, uncertainty, and next action.

## 14. Non-Negotiables

- No production mutation.
- No auto-merge.
- No behavior patch without codebase grounding.
- No blocking evaluator without validation record.
- No replay of unknown or side-effecting tools without sandbox classification.
- No reliance on filename-only discovery.
- No manual trace import as the steady-state path.
- No hidden hosted dependency for the local loop.
