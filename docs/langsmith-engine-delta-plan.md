# LangSmith Engine Delta Plan

Status: Draft 0.1
Date: 2026-09-06

Assumption: "Nextgen" refers to LangSmith Engine and the next-generation closed-loop agent-improvement product pattern it represents.

## 1. Executive Summary

LangSmith Engine is the strongest public product benchmark for LoopForge. It already implements much of the broad category:

```text
production traces -> recurring issue detection -> diagnosis -> proposed fix -> evaluator/dataset examples -> monitoring -> reopen on recurrence
```

LoopForge should not compete by claiming the loop is novel. The durable position is:

```text
open, local-first, repo-native, stack-neutral, manifest-grounded, ontology-standardized, evaluator-validated closed-loop improvement
```

This document translates LangSmith Engine's strongest demonstrated capabilities into a LoopForge build plan.

## 2. Source Baseline

Primary public sources reviewed:

- [LangSmith Engine product docs](https://docs.langchain.com/langsmith/engine)
- [How We Built LangSmith Engine](https://www.langchain.com/blog/how-we-built-langsmith-engine-our-agent-for-improving-agents)
- [LangSmith Engine issue categories](https://docs.langchain.com/langsmith/engine-issue-categories)
- [LangSmith Engine security](https://docs.langchain.com/langsmith/engine-security)
- [LangSmith Engine self-hosted docs](https://docs.langchain.com/langsmith/engine-self-hosted)
- [LangSmith Engine webhooks](https://docs.langchain.com/langsmith/engine-webhooks)
- [LangSmith evaluation docs](https://docs.langchain.com/langsmith/evaluation)
- [LangSmith CLI docs](https://docs.langchain.com/langsmith/langsmith-cli)

## 3. Where LangSmith Engine Is Ahead

### 3.1 Productized Issue Lifecycle

LangSmith Engine has a user-facing issue workflow: issue list, severity, category, evidence traces, diagnosis, proposed actions, watching, closing, ignoring, recurrence tracking, and automatic reopening.

LoopForge current state:

- We specify issue objects and reports.
- We do not yet specify a full issue lifecycle state machine.
- We do not yet specify recurrence matching, issue reopening, duplicate suppression, or reviewer workflows in enough detail.

LoopForge response:

- Build a repo-local issue store with a real lifecycle before building a dashboard.
- Make issue state portable as files plus SQLite, so CLI, CI, GitHub, and future UI all share the same source.

Required objects:

- `Issue`
- `IssueEvent`
- `IssueEvidenceLink`
- `IssueDecision`
- `IssueRecurrenceMatcher`
- `IssueWatch`

Lifecycle:

```text
candidate -> open -> watching -> fix_in_progress -> gated -> merged -> resolved
candidate -> ignored
resolved -> reopened
open -> muted
```

Acceptance criteria:

- A recurring seeded failure maps to one issue, not many.
- A resolved issue reopens when new matching traces appear.
- An ignored issue trains future ranking away from similar false positives.
- Each state transition is audit logged.

### 3.2 Agent Overview Equivalent

LangSmith Engine uses an Agent Overview as both instruction context and project memory. It is generated during setup, read on future runs, updated from investigations, and editable by users.

LoopForge current state:

- We have harness index and runtime manifest concepts.
- We have not formalized the human-readable project memory layer.

LoopForge response:

- Add `.loopforge/agent-profile.md` as the repo-owned equivalent.
- Treat it as generated context, not source of truth.
- Update it automatically from trace mining, accepted/rejected recommendations, and artifact discovery.

Proposed file:

```text
.loopforge/agent-profile.md
```

Sections:

- Agent purpose.
- User-facing workflows.
- Runtime architecture.
- Harness map summary.
- Trace shape guide.
- Canonical ontology priorities.
- Known failure patterns.
- Review preferences learned from PR outcomes.
- Current trust qualification.
- Open observability gaps.

Acceptance criteria:

- First `loopforge shadow` can generate a useful profile from traces and code.
- A reviewer can edit it.
- LoopForge distinguishes profile claims from trace/code evidence.
- Profile changes affect future prioritization but cannot bypass gates.

### 3.3 Trace Scaling With Trajectories

LangSmith Engine does not load every full trace into the main agent. It first screens compact trajectory representations, then loads full traces selectively for deeper investigation.

LoopForge current state:

- We specify semantic clustering and probabilistic issue mining.
- We need a concrete trace compression and screening architecture.

LoopForge response:

- Add a `TraceTrajectory` primitive.
- Use it as the first-pass representation for screening and clustering.
- Preserve pointers back to full spans for evidence.

Trajectory fields:

- Trace ID.
- Session/thread ID.
- Turn count.
- Span skeleton.
- Role/tool names.
- Token/cost/latency summaries.
- Error markers.
- Feedback summaries.
- Side-effect classes.
- Runtime manifest ID.
- Harness artifact hints.

Pipeline:

```text
full trace -> normalized trace -> redacted trace -> trajectory -> screener -> investigation bundle
```

Acceptance criteria:

- Screen 1,000 trace fixtures without loading full content for every trace.
- Preserve enough pointers to reconstruct evidence for flagged traces.
- Detect loops, repeated tool calls, errors, high cost, and feedback-prioritized failures from trajectories.

### 3.4 Screener And Investigator Split

LangSmith Engine uses a narrow screener agent over groups of traces and deeper investigator agents for promising candidates.

LoopForge current state:

- We describe issue miner and diagnosis engine, but not an explicit multi-stage agent topology.

LoopForge response:

- Build a deterministic pipeline shell around probabilistic agents.
- Use specialized prompts/models for separate tasks:
  - trace screener
  - issue clusterer
  - investigator
  - evaluator drafter
  - evaluator validator
  - patch planner
  - patch generator
  - gate explainer

Important distinction:

- The orchestration order and gate enforcement are deterministic product control.
- Discovery, diagnosis, clustering, and patch reasoning remain probabilistic and confidence-scored.

Acceptance criteria:

- Screeners cannot create PRs or mutate issue state directly.
- Investigators must cite trace/span IDs and code artifacts.
- Patch generation cannot run unless issue confidence, observability, and grounding thresholds pass.

### 3.5 Dataset Examples And Assertions

LangSmith Engine turns evidence traces into offline dataset examples and favors assertions over exact reference outputs.

LoopForge current state:

- We specify eval generation and validation records.
- We should add assertion-first dataset examples as the default generated artifact.

LoopForge response:

- Add `EvalExample` and `Assertion` schemas.
- Draft assertions from evidence traces.
- Support exact, semantic, tool-sequence, permission, grounding, side-effect, latency, and cost assertions.

Default generated eval case:

```yaml
id: subscription-options-no-cancel
source_trace_id: tr_123
input:
  user_message: "Before I cancel, explain my plan options."
assertions:
  - type: forbidden_tool_call
    tool: cancel_subscription
  - type: requires_confirmation_before_tool
    tool: cancel_subscription
  - type: semantic_response_requirement
    claim: "The response explains available plan options."
```

Acceptance criteria:

- Every issue has at least one generated eval candidate.
- Every behavior patch has at least one generated eval update.
- Assertion cases can export to Promptfoo, LangSmith, Braintrust, and local pytest-style runners.

### 3.6 Evaluator Management

LangSmith has workspace-level evaluators, online/offline evaluation workflows, evaluator attachment, sampling, experiment runs, and generated evaluators from Engine.

LoopForge current state:

- We go deeper on evaluator validation, but we need the operational layer.

LoopForge response:

- Build a local evaluator registry.
- Separate evaluator definitions from validation records.
- Support online monitor evaluators and offline regression evaluators.

Objects:

- `EvaluatorDefinition`
- `EvaluatorValidationRecord`
- `EvaluatorAttachment`
- `EvaluatorRun`
- `EvaluatorDriftReport`

Acceptance criteria:

- Evaluators can attach to trace sources, datasets, or CI suites.
- Blocking eligibility requires validation records.
- Online evaluator sampling is configurable.
- Evaluator drift triggers revalidation.

### 3.7 Fix PR Workflow

LangSmith Engine opens PRs when a repo is connected and uses source code to ground fixes.

LoopForge current state:

- We specify PR generation and gates.
- We need an implementation-level PR workflow with branch names, patch artifacts, dry-run mode, and review labels.

LoopForge response:

- Implement PRs as a thin layer over local patch artifacts.
- The local patch artifact is canonical; GitHub/GitLab are delivery mechanisms.

Workflow:

```text
issue -> diagnosis -> patch candidate -> eval candidate -> evaluator validation -> gates -> local patch bundle -> PR
```

PR branch convention:

```text
loopforge/ISSUE-ID/short-slug
```

Acceptance criteria:

- Dry-run PR artifact works without GitHub.
- GitHub PR creation works from local git.
- PR body includes evidence, diagnosis, eval changes, gate report, rollback, and residual risk.
- Low-confidence behavior patches remain preview-only.

### 3.8 Notifications, Webhooks, And Integrations

LangSmith Engine can notify Slack and webhooks when issues are created, traces are added, or Engine runs fail. Webhook deliveries include signing, retry, dedupe IDs, and event filters.

LoopForge current state:

- We mention notifications but do not define event payloads.

LoopForge response:

- Define signed webhook events early.
- Make Slack/GitHub comments optional adapters over the same event bus.

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

- Every event has an ID, timestamp, project ID, event type, and object payload.
- Webhook signing uses HMAC over raw body.
- Consumers can dedupe retries by event ID.
- Notification filtering supports severity and event type.

### 3.9 Sandbox And Security Posture

LangSmith Engine runs analysis in isolated sandboxes, uses short-lived GitHub tokens, constrains network access, and presents outputs as advisory PRs or prompt proposals.

LoopForge current state:

- We specify local-first security and replay isolation.
- We need a concrete sandbox profile and credential model.

LoopForge response:

- For MVP, run patch/gate work in an isolated git worktree with restricted output paths.
- For Docker mode, provide a network-denied default and explicit adapter allowlists.
- Never expose raw secrets to model calls.

Security controls:

- Redaction before model calls.
- Read-only repo discovery by default.
- Patch generator can only write patch bundles.
- PR writer is the only component with git push credentials.
- Replay blocks unknown or side-effecting tools unless sandboxed.
- Trace content is always untrusted.

Acceptance criteria:

- Seeded prompt injection inside a trace cannot alter LoopForge behavior.
- Patch cannot modify files outside allowlist.
- Replay cannot perform write, money movement, external message, destructive, or unknown tool effects.
- Credentials never appear in trace bundles, logs, or PR bodies.

### 3.10 Cost And Spend Controls

LangSmith Engine exposes analysis levels, recurring scan costs, spend limits, and pause/resume controls.

LoopForge current state:

- We mention cost/latency gates for target agents, but not LoopForge's own operating budget.

LoopForge response:

- Add explicit analysis budgets for LoopForge runs.
- Make cost part of trust.

Config:

```yaml
analysis:
  max_traces_per_scan: 1000
  max_full_traces_per_scan: 75
  max_model_calls_per_scan: 250
  max_estimated_cost_usd_per_scan: 10
  analysis_level: standard
```

Acceptance criteria:

- Run planner estimates cost before analysis.
- Monitor pauses when budget is exceeded.
- Reduced mode screens fewer traces and lowers full-trace investigation.
- Reports include LoopForge analysis cost, not only target-agent cost.

### 3.11 Setup And Admin Workflow

LangSmith Engine has organization enablement, per-project setup, repository connection, preferences, trace focus, issue settings, and pause/resume.

LoopForge current state:

- We have CLI setup but need more productized setup state.

LoopForge response:

- Implement `loopforge connect` as a guided but mostly automatic setup flow.
- Add `loopforge doctor` as trust-building diagnostics.
- Add `loopforge settings` commands for CI-friendly updates.

Commands:

```text
loopforge connect
loopforge doctor
loopforge settings show
loopforge settings set monitor.schedule "every 6 hours"
loopforge monitor pause
loopforge monitor resume
loopforge scope set --run-name support-agent --metadata env=prod
```

Acceptance criteria:

- A user can get first value with default settings.
- All setup decisions are visible in `loopforge.yaml`.
- Scope can filter by run name, metadata, feedback, ontology ID, and trace source.

### 3.12 LangSmith Adapter And Compatibility

LangSmith Engine is naturally strongest for teams already on LangSmith. LoopForge should turn that from a threat into an integration path.

LoopForge response:

- Build LangSmith as a first-class trace adapter.
- Import LangSmith traces, feedback, datasets, evaluator results, and issue metadata where API access permits.
- Export LoopForge-generated eval examples to LangSmith dataset format.

Acceptance criteria:

- `loopforge connect` detects LangSmith environment variables.
- `loopforge ingest --source langsmith` imports trace metadata, feedback, spans, and run URLs.
- Issue reports link back to LangSmith traces.
- Eval exports can become LangSmith dataset examples.

## 4. Leapfrog Bets

LangSmith is ahead in integrated product workflow. LoopForge should not try to out-UI them first. The leapfrog bets are infrastructure-level:

1. Runtime harness manifests as an open standard.
2. Canonical ontology with local extensions.
3. Evaluator validation records before blocking gates.
4. Local-first and bring-your-own-model execution.
5. Portable adapters across LangSmith, Langfuse, Phoenix, Braintrust, OpenTelemetry, and JSONL.
6. Contractual checks for objective behavior.
7. Git-native patch bundles that work without a hosted control plane.

## 5. Build Plan

### Phase 0: Product Contract Lock

Goal: make the foundations explicit before writing feature code.

Deliverables:

- Issue lifecycle schema.
- Trace trajectory schema.
- Eval example/assertion schema.
- Evaluator definition schema.
- Webhook event schema.
- Analysis budget config.
- Agent profile template.

Exit criteria:

- All schemas validate.
- README describes the first 30-minute workflow.
- Fixtures exist for a seeded support-agent failure.

### Phase 1: Local Closed-Loop Spine

Goal: prove the loop works without external services.

Deliverables:

- Python package skeleton.
- CLI: `init`, `connect`, `discover`, `shadow`, `issues list`, `issues show`.
- JSONL adapter.
- Trace trajectory builder.
- Local issue store.
- Agent profile generator.
- Static HTML/Markdown issue reports.

Exit criteria:

- Seeded JSONL traces produce one recurring issue.
- Issue has evidence trace IDs and ontology IDs.
- Agent profile is generated from code and traces.

### Phase 2: Eval And Validator Spine

Goal: make every issue produce useful eval artifacts.

Deliverables:

- Eval example/assertion generator.
- Evaluator definition generator.
- Evaluator validation runner.
- Local evaluator registry.
- Exporters: local YAML/JSONL and Promptfoo.

Exit criteria:

- Seeded failure generates an assertion-based eval.
- Validation record marks evaluator provisional or validated.
- Blocking eligibility requires thresholds.

### Phase 3: Patch And Gate Spine

Goal: propose safe changes only when grounded.

Deliverables:

- Diagnosis engine.
- Patch planner.
- Markdown/YAML patch generator.
- Gate runner.
- Side-effect-safe replay stub.
- Local patch bundle.
- Dry-run PR artifact.

Exit criteria:

- Cancellation fixture produces a tool-description or permission-policy patch, not a broad system-prompt patch.
- Gate report includes replay, evaluator validation, regression, cost, and grounding checks.
- Low-confidence patch remains preview-only.

### Phase 4: GitHub And Notifications

Goal: match the practical product workflow teams expect.

Deliverables:

- GitHub branch and PR writer.
- PR labels and body template.
- Signed webhook emitter.
- GitHub issue/comment adapter.
- Slack webhook adapter.

Exit criteria:

- `loopforge pr --eval-only` opens a real PR.
- `loopforge pr --patch` opens only after gates pass.
- Webhook payloads are signed and dedupe-safe.

### Phase 5: LangSmith Compatibility

Goal: make LangSmith users a target adoption path, not a competitive blind spot.

Deliverables:

- LangSmith trace adapter.
- LangSmith feedback ingestion.
- LangSmith trace deep links in issue evidence.
- LangSmith dataset export.
- Optional import of existing evaluator results.

Exit criteria:

- A LangSmith project can be analyzed without exporting traces manually.
- LoopForge can produce local issues and eval PRs from LangSmith traces.

### Phase 6: Trace Platform Expansion

Goal: establish LoopForge as stack-neutral.

Deliverables:

- Langfuse adapter.
- Phoenix adapter.
- OpenTelemetry/OpenInference adapter.
- Braintrust adapter where API access permits.
- Adapter conformance tests.

Exit criteria:

- Same seeded failure can be represented through at least three adapters.
- Adapter tests verify span hierarchy, feedback, costs, and side-effect metadata preservation.

### Phase 7: Local Web UI

Goal: close the product experience gap after the core loop is real.

Deliverables:

- Local issue board.
- Issue detail view.
- Evidence trace view.
- Eval candidate view.
- Gate report view.
- Monitor status and budget view.

Exit criteria:

- A developer can review the entire loop locally without opening raw JSON files.
- UI reads from the same local store as CLI.

## 6. Immediate Next Engineering Tickets

1. Add schemas: `issue-event`, `trace-trajectory`, `eval-example`, `evaluator-definition`, `webhook-event`.
2. Scaffold Python package with `uv`, `typer`, `pydantic`, and SQLite.
3. Implement `loopforge init`.
4. Implement JSONL trace adapter.
5. Implement trace trajectory builder.
6. Implement support-agent fixture repo and seeded failure traces.
7. Implement local issue store and issue lifecycle events.
8. Implement first probabilistic screener interface with a mock/local deterministic test double for CI.
9. Implement `loopforge shadow --last 24h` against local JSONL.
10. Implement generated issue Markdown report.

## 7. Strategic Positioning

Do not say:

```text
LoopForge is an open-source LangSmith Engine.
```

Say:

```text
LoopForge is the open standard and local-first runtime for closed-loop agent harness improvement.
```

LangSmith Engine validates demand. LoopForge should win where productized SaaS naturally has less incentive to optimize:

- open schemas
- portable adapters
- local-first execution
- bring-your-own-model
- runtime harness manifests
- canonical ontology
- validated evaluators
- CI-native gates
- no hosted platform requirement
