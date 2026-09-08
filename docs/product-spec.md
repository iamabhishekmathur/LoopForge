# LoopForge Product Specification

Status: Draft 0.1
Date: 2026-09-05
Repository codename: agent-harness-loop
Working product name: LoopForge

## 1. Executive Summary

LoopForge is an open-source, continuously running improvement engine for AI agent harnesses.

It helps teams move from manual agent debugging to a trusted closed-loop workflow that runs on a configurable schedule:

```text
monitor traces -> discover harness -> mine issues -> diagnose -> propose harness patch -> generate eval -> acceptance gate -> PR -> rollout -> monitor
```

The target user is an engineer or small agent team building production AI agents. They may already use LangChain, LangGraph, OpenAI Agents SDK, Claude tools, Vercel AI SDK, Mastra, CrewAI, LlamaIndex, AutoGen, custom orchestration, Langfuse, Phoenix, LangSmith, Braintrust, Promptfoo, or plain logs.

LoopForge should fit into those stacks with minimal friction. It should not ask teams to switch frameworks, manually import traces forever, adopt a hosted platform, or expose sensitive production traces to a vendor.

The product should feel like a monitoring service plus an AI eval engineer plus a careful staff engineer. It watches the agent, understands the codebase, drafts the failure analysis, writes tests, proposes changes, gates them, and asks humans to approve release boundaries.

## 2. Product Thesis

Agent quality will be won by teams that close the loop between real usage and harness evolution.

Foundation models improve, but agent reliability lives in the harness:

- System and developer prompts.
- Tool descriptions and schemas.
- Skill instructions.
- Routing policies.
- Context packing.
- Retrieval and memory policies.
- Permission boundaries.
- Confirmation flows.
- Evals, scorers, and acceptance gates.
- Rollout and rollback procedures.

Most teams improve these artifacts manually. They read traces, patch prompts, update tool schemas, and maybe add a regression test. That process works when the team is tiny and traffic is low. It breaks once the agent sees many workflows, many users, many tools, and frequent model launches.

LoopForge makes harness improvement a first-class engineering discipline by continuously watching production traces and continuously refreshing its understanding of the codebase and harness.

## 3. Public Market Context

Public tooling already covers important pieces:

| Area | Existing examples | Gap LoopForge targets |
| --- | --- | --- |
| Tracing and observability | Langfuse, Phoenix, LangSmith, AgentOps | Trace data is visible but not always converted into durable harness changes. |
| Offline evals | Promptfoo, OpenAI Evals, Braintrust, LangSmith, Phoenix | Evals exist but are often manually authored and disconnected from production failures. |
| Prompt optimization | DSPy, GEPA, OPRO, TextGrad, EvoPrompt | Optimizers target prompts/programs but do not own the end-to-end product workflow of issue, eval, gate, PR, rollout. |
| Closed-loop products | LangSmith Engine | Strong product signal, but not a neutral OSS harness standard. |
| Continual harness research | Continual Harness | Strong evidence that harness state can improve from trajectory data; LoopForge adapts this to production software with gates and PR review. |
| Frontier lab launch process | OpenAI system cards and deployment simulation, Anthropic RSP/system cards, Google DeepMind Frontier Safety, Meta Llama model cards | Labs have internal processes; most agent companies need a practical OSS version. |

LoopForge should not try to replace this ecosystem. Its adoption path is integration-first.

## 4. Mission

Make closed-loop agent improvement the default operating model for every agent company.

## 5. Product Goals

### 5.1 Primary Goals

1. Reduce time from production failure to reviewed fix.
2. Increase regression eval coverage from real traces.
3. Improve harness quality without requiring a framework migration.
4. Make model launches safer by replaying representative traces through candidate model and harness combinations.
5. Build trust by making every proposed change evidence-backed, gated, and reviewable.
6. Automatically monitor trace sources on user-defined schedules.
7. Build and maintain a semantic index of the codebase, harness artifacts, tools, Skills, prompts, routes, policies, and evals.
8. Capture the runtime harness manifest for each agent run so recommendations are grounded in the harness that actually executed, not just the repository snapshot.
9. Reduce first value to 30 minutes and reduce first useful integration to 1 hour through automatic connection, discovery, drafting, and setup PRs.
10. Treat harness improvement as an auditable state machine: every proposed edit should have an operation record, provenance, gate status, and post-merge outcome.

### 5.2 Non-Goals

LoopForge should not:

- Become a general-purpose LLM observability dashboard.
- Replace existing trace platforms.
- Silently self-modify production prompts or policies.
- Require a hosted control plane.
- Require all traces to be sent to a third-party service.
- Require users to manually import traces after initial setup.
- Optimize for benchmark leaderboard performance over production reliability.
- Treat system prompts as the only harness layer.
- Hide the rationale for a proposed change.

## 6. Target Users

### 6.1 Primary Persona: Agent Product Engineer

Profile:

- Builds and maintains a production agent.
- Owns prompts, tools, evals, and agent orchestration.
- Has limited time to inspect traces manually.
- Wants pragmatic fixes and regression coverage.

Pain:

- Users report failures that traces can explain only after manual digging.
- Prompt and tool changes are hard to validate.
- Model upgrades create surprising behavior changes.
- Evals lag behind actual production use.
- The codebase and harness drift away from whatever the observability tool thinks exists.

Value:

- Gets a PR containing the harness patch, evidence, and evals.
- Can reject, edit, or merge with confidence.
- Does not need to babysit trace import jobs or manually map every harness file.

### 6.2 Secondary Persona: AI Platform Engineer

Profile:

- Supports many internal agent teams.
- Owns shared eval, tracing, CI, and release infrastructure.

Pain:

- Each team invents its own prompt and eval workflow.
- No common failure ontology across agents.
- Hard to tell which agents are actually improving.

Value:

- Standardizes trace-to-eval-to-PR workflows.
- Enables org-wide quality dashboards without dictating the agent framework.

### 6.3 Secondary Persona: Founder or CTO of an Agent Startup

Profile:

- Needs reliability quickly.
- Cannot build a full internal evals and harness team.

Pain:

- Quality issues block enterprise adoption.
- Customers want evidence that the agent is improving.

Value:

- Adds a credible closed-loop quality process.
- Produces auditable PRs and quality reports for customers.

### 6.4 Secondary Persona: Security or Compliance Reviewer

Profile:

- Reviews AI agent risk, tool access, data handling, and change control.

Pain:

- Agent behavior changes without clear diffs.
- Production traces may contain sensitive data.
- Tool permissions and prompts are not governed.

Value:

- Sees proposed changes as PRs.
- Sees policy gates, redaction, and rollout metadata.

## 7. Jobs To Be Done

1. When a production agent fails repeatedly, identify the pattern and propose a fix.
2. When a user gives negative feedback, convert the trace into an eval and a possible patch.
3. When a new model launches, replay realistic traces and identify harness changes needed before rollout.
4. When a tool is misused, improve the tool description, schema, validation, or routing policy.
5. When a Skill is missing or misfiring, create or update the Skill and add trigger evals.
6. When a prompt change is proposed, prove it does not regress core workflows.
7. When a safety issue appears, add targeted evals and controls without over-refusing benign requests.
8. When context packing loses important information, update context policy and add trace-level tests.

## 8. Product Principles

### 8.1 Evidence Over Vibes

Every issue should link to traces, spans, examples, and eval results.

### 8.2 Automatic Monitoring By Default

After setup, LoopForge should run as a scheduled monitor. Users configure cadence, trace sources, privacy policy, and PR behavior; they should not manually import traces as a regular workflow.

### 8.3 AI-Observed And AI-Drafted By Default

LoopForge should observe traces, discover artifacts, draft issue clusters, draft failure labels, draft evals, draft patches, and draft PRs automatically. The product should not rely on the user to perform manual trace review, manual ontology construction, manual eval authoring, or manual harness mapping as the default workflow.

Human input is still valuable, but it should enter as approval, correction, or policy configuration. Corrections should update the repo-local learning loop so the system drafts better recommendations next time.

### 8.4 Probabilistic Harness Intelligence

Issue discovery, artifact classification, root-cause analysis, and patch planning should be semantic and probabilistic. The system should use model-based judgment, embeddings, uncertainty estimates, and competing hypotheses rather than brittle filename assumptions or hand-written pattern rules.

Objective product contracts should still be checked contractually. The intelligence layer should be probabilistic; the release boundary should be strict.

### 8.5 Codebase-Grounded Diagnosis

LoopForge must understand the codebase before diagnosing failures. It should build an index of prompts, Skills, tool definitions, routes, policies, agent graphs, evals, and the code that assembles them so recommendations are grounded in what the system actually runs.

### 8.6 Runtime Truth Over Repository Guesses

Codebase discovery is necessary but insufficient. Production agents often assemble behavior from feature flags, tenant policies, prompt registries, model routers, A/B tests, retrieved context, and runtime configuration. LoopForge should prefer a runtime harness manifest emitted with every trace over static repository inference whenever both are available.

### 8.7 Canonical Ontology With Local Extensions

LoopForge should ship with a canonical failure ontology, not a disposable starter list. Teams can extend it, but local extensions should map back to canonical outcome, mechanism, and governance layers so reports, evals, integrations, and community packs remain comparable.

### 8.8 Human-Approved Release Boundary By Default

The default output is an AI-drafted PR, not a production mutation. Humans approve release boundaries; they should not be required to author the issue, eval, or patch from scratch.

### 8.9 Patch The Right Layer

The system must decide whether the fix belongs in:

- System prompt.
- Developer prompt.
- Skill trigger or body.
- Tool schema.
- Tool description.
- Router policy.
- Permission policy.
- Context packing.
- Memory/retrieval interface.
- Evaluator.
- Product UI or confirmation flow.
- Application code.

### 8.10 Eval Coverage Is A First-Class Deliverable

A fix without a regression eval is incomplete.

### 8.11 Local-First Trust

Teams should be able to run LoopForge entirely inside their environment.

### 8.12 Stack-Neutral

LoopForge should interoperate through open schemas:

- OpenTelemetry.
- OpenInference.
- JSONL traces.
- Git patches.
- YAML config.
- Standard CI outputs.

### 8.13 Smallest Useful Change

Candidate patches should be focused, explainable, and reversible.

### 8.14 No Harness Sediment

Do not solve every issue by appending more prompt text. Prefer targeted artifacts and evals.

### 8.15 Harness State Is The Product Object

LoopForge should track the harness as evolving state, not a loose pile of prompts and patches. Each trace should connect to the harness state that produced it, and each proposed improvement should create a structured refinement operation that can be audited, gated, accepted, rejected, reverted, or learned from.

### 8.16 Component-Specific Refinement

The refiner should not be a single generic patch generator. It should run component-specific passes for prompts, Skills, tools, policies, context, retrieval, memory interfaces, evals, scorers, and agent graphs. Each pass should understand the edit types, risks, and gates appropriate to that component.

### 8.17 Continuous Drafting, Reviewed Release

LoopForge may observe, diagnose, draft, and simulate continuously. It should not continuously mutate production. Production-facing change remains PR-based and gate-based unless a team explicitly opts into a narrower local apply mode.

### 8.18 Visible Self-Improvement

Self-improvement must be visible enough to earn trust. Every meaningful LoopForge recommendation should answer what the system learned, what it wants to change, why that change is justified, how it will be validated, and how it can be rolled back.

Silent mutation is not acceptable for production-facing harness changes. LoopForge may draft automatically, but it should expose a reviewable harness diff before any accepted patch or PR is created.

### 8.19 Scoped Refinement

Refinement scope should be explicit on every operation:

- `shadow`: observation and draft only.
- `workflow`: one agent, Skill, workflow, or product surface.
- `project`: one repository or deployed agent project.
- `org`: cross-agent or cross-repository policy.

Higher scopes require stronger evidence, more gates, and more explicit review. The default onboarding path should start with `shadow` and `workflow` operations even when the system is capable of broader drafting.

### 8.20 Async And Nonblocking

Monitoring, diagnosis, refinement, gate execution, and post-merge confirmation should never block production agent execution. Long-running improvement work belongs in an async queue with budgets, cancellation, retry, and dead-letter states.

## 9. Product Surface

### 9.1 CLI

The CLI is the primary developer experience.

Example:

```bash
loopforge init
loopforge connect
loopforge discover
loopforge states list
loopforge shadow --last 24h
loopforge pr --eval-only
loopforge monitor start
loopforge issues list
loopforge propose ISSUE-2026-00017
loopforge refinements list
loopforge refinements preview OPERATION-2026-00017-a
loopforge queue list
loopforge queue run-next
loopforge gate PATCH-2026-00017-a
loopforge confirm PATCH-2026-00017-a --observed-traces 50 --recurring-failures 0
loopforge confirmations show CONFIRM-PATCH-2026-00017-a
loopforge review OPERATION-2026-00017-a merged
loopforge learned
loopforge rollback PATCH-2026-00017-a
loopforge pr PATCH-2026-00017-a
```

### 9.2 Monitoring Service

The monitoring service is the default product loop after setup.

It should:

- Poll or subscribe to configured trace sources.
- Rebuild the harness and codebase index on a schedule or after Git changes.
- Mine issues on a configurable cadence.
- Generate candidate issues and patches when confidence clears thresholds.
- Run gates automatically.
- Open PRs automatically only when configured and gates pass.
- Notify maintainers through GitHub, Slack, email, or webhooks.

Example:

```yaml
monitor:
  enabled: true
  schedule: "every 6 hours"
  trace_window: "24 hours"
  min_issue_confidence: 0.78
  min_patch_confidence: 0.82
  open_prs: true
  max_prs_per_day: 3
```

### 9.3 GitHub Action

Runs gates on pull requests:

```yaml
name: LoopForge
on: [pull_request]
jobs:
  loopforge:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: loopforge/loopforge-action@v1
        with:
          suite: core
          candidate-models: gpt-5.5,claude-sonnet-5,gemini-3.7-flash
```

### 9.4 PR Comment

Each PR should include:

- Issue summary.
- Evidence traces.
- Root-cause hypothesis.
- Modified harness artifacts.
- New eval cases.
- Gate results.
- Rollback plan.
- Residual risk.

### 9.5 Local Web UI

Optional. Not required for MVP.

The UI should show:

- Issues grouped by failure mode.
- Trace evidence.
- Candidate patches.
- Eval results.
- Gate decisions.
- Harness artifact history.
- Codebase and harness index.
- Monitor status and schedule.

### 9.6 Library API

For teams that want to embed the workflow:

```python
from loopforge import LoopForge

lf = LoopForge.load(".")
lf.discover()
lf.monitor_once()
issues = lf.mine()
patch = lf.propose(issues[0].id)
report = lf.gate(patch.id)
```

## 10. Canonical Workflow

### 10.1 Setup

1. Install CLI.
2. Run `loopforge init`.
3. Run `loopforge connect` to auto-detect trace sources, test credentials, infer project and environment, and set the monitoring cadence.
4. Run `loopforge discover` to build an AI-drafted codebase and harness index.
5. Run `loopforge shadow --last 24h` to generate AI-drafted issues, eval candidates, and behavior-patch previews.
6. Preview or correct the artifact map only when confidence is too low for the desired autonomy level.
7. Accept generated setup PRs for runtime manifests, trace enrichment, replay, monitor config, and CI gates.
8. Start the monitor.

The first evidence-backed value should arrive in 30 minutes or less for an existing agent repo. The first useful integration PRs should be generated in 60 minutes or less.

### 10.2 Continuous Monitoring Loop

1. Wake on configured schedule, webhook, or manual `monitor once`.
2. Pull new traces from configured sources.
3. Normalize into LoopForge trace schema.
4. Apply privacy policy and build LLM-safe evidence bundles.
5. Refresh the codebase and harness index if the repo changed.
6. Mine recurring or severe failures using probabilistic classifiers and semantic clustering.
7. Rank issues by impact, confidence, trace observability, and eval coverage gap.
8. Produce issue objects.
9. Generate candidate patches and regression evals when confidence clears configured thresholds.
10. Run acceptance gates in an isolated workspace.
11. Open PRs or write patch reports according to policy.
12. Monitor post-merge traces for fix confirmation or regression.

### 10.3 New Model Launch Loop

1. Define candidate model.
2. Replay representative traces.
3. Compare old model plus old harness against candidate model plus old harness.
4. Detect changed behavior.
5. Generate required harness patches.
6. Run broad regression suites.
7. Produce model launch report.
8. Support staged rollout and rollback.

### 10.4 Skill Improvement Loop

1. Detect tasks where a Skill should have triggered but did not.
2. Detect tasks where a Skill triggered unnecessarily.
3. Detect cases where Skill instructions caused poor tool use, excessive refusal, or unfinished work.
4. Patch trigger conditions, anti-trigger conditions, workflow steps, or verification requirements.
5. Generate Skill trigger evals and task completion evals.

### 10.5 Continual Harness Refinement Loop

LoopForge should add a continuous refinement loop that runs after trace monitoring and before PR creation.

1. Select a recent trajectory window by schedule, trace count, severity spike, model change, or post-merge follow-up.
2. Compare the observed traces against the runtime harness manifests and current harness state graph.
3. Run component-specific refiner passes over prompts, Skills, tools, policies, context, retrieval, memory interface, evals, scorers, and agent graph artifacts.
4. Emit refinement operations with CRUD semantics: `create`, `update`, `delete`, or `noop`.
5. Link each operation to traces, issues, evals, candidate patches, confidence, rationale, and risk.
6. Gate operations through replay, evaluator validation, grounding, safety, and regression checks.
7. Convert approved operations into PRs according to the autonomy level.
8. Monitor post-merge traces to determine whether the failure signature actually decreased.

This loop incorporates the strongest lesson from Continual Harness while adapting it to production agent companies: the system should improve from trajectory data continuously, but release trust must remain explicit and reviewable.

### 10.6 Lessons From Recursive Agent Harnesses

Recursive agent harnesses such as Prime Agent show that self-improvement is not only prompt editing. The reusable improvement object can be a memory, supplemental prompt note, Skill, subagent spec, tool contract, context policy, eval, scorer, or workflow artifact.

LoopForge should adopt the useful parts while avoiding the trust pitfalls:

1. Treat harness state as editable state, but keep base system prompts and production artifacts protected behind review.
2. Use small, evidence-backed refinement operations instead of broad rewrites.
3. Require every operation to include expected outcome, validation plan, and rollback plan.
4. Make the diff visible before applying or opening a PR.
5. Prefer local or workflow-scoped refinements before project-wide or org-wide changes.
6. Convert repeated delegation patterns into subagent specifications when that is the right fix.
7. Run automatic refinement asynchronously so trace monitoring and production serving remain decoupled.
8. Surface a "what LoopForge learned" view so teams can understand the improvement loop without reading raw trace files.

## 11. Harness Artifact Model

LoopForge should support a recommended layout while adapting to existing repos. It must not assume teams already know where every harness artifact lives.

### 11.1 Codebase Discovery And Harness Index

During setup and on a recurring schedule, LoopForge should inspect the full codebase to discover the harness artifacts and code paths that shape agent behavior.

Discovery targets:

- System prompts.
- Developer prompts.
- Skill files and Skill-like procedural instructions.
- Tool definitions, tool descriptions, and tool schemas.
- Router policies and model-selection logic.
- Permission and confirmation policies.
- Context packing, summarization, retrieval, and memory interface code.
- Eval suites, datasets, scorers, and launch checks.
- Agent graphs, workflow definitions, and orchestration code.
- Prompt registry usage and remote prompt references.
- Framework-specific configuration for LangChain, LangGraph, OpenAI Agents SDK, Vercel AI SDK, LlamaIndex, CrewAI, AutoGen, Mastra, Pydantic AI, and custom agents.

Discovery should be semantic and probabilistic:

- Use repository parsing, embeddings, model-based artifact classification, import graph context, and developer-provided hints.
- Maintain confidence scores for every discovered artifact and relationship.
- Let users approve or correct the artifact map when needed, but do not require manual mapping for first value.
- Re-index after Git changes, dependency changes, or scheduled monitor runs.
- Avoid brittle assumptions based only on filenames, comments, or isolated string patterns.

The index should represent a graph:

```text
agent -> router -> Skill -> tool -> permission policy -> eval coverage
agent -> context policy -> retrieval/memory interface
issue -> evidence traces -> suspected artifacts -> candidate patch -> evals
```

This index is required for grounded recommendations. If LoopForge cannot identify the relevant harness artifacts with enough confidence, it should downgrade the recommendation, request review, or propose an observability/indexing improvement before proposing a behavioral patch.

### 11.2 Runtime Harness Manifest

Every production trace should ideally include a runtime harness manifest. This manifest is the most trusted description of what actually executed for that run.

Required manifest fields:

- Agent version and deployment environment.
- Model provider, model name, and model configuration.
- System prompt hash and source reference.
- Developer prompt hash and source reference.
- Active Skill IDs and versions.
- Tool names, schema hashes, and implementation versions.
- Router policy hash.
- Permission and confirmation policy hashes.
- Context packing, retrieval, and memory-interface policy hashes.
- Prompt registry references and remote prompt versions.
- Feature flags and experiment IDs.
- Tenant or customer policy IDs when applicable.
- Eval suite and scorer versions used for online scoring.

The manifest should not store full sensitive prompt or policy content inside traces by default. It should store stable hashes, source references, and version IDs that LoopForge can map back to the codebase or prompt registry under the team's access controls.

When codebase discovery and the runtime manifest disagree, LoopForge should prefer the runtime manifest for diagnosis and flag a `HARNESS_INDEX_GAP`.

### 11.3 Harness State Graph

LoopForge should persist a harness state graph that captures the effective state of the agent harness over time.

State graph nodes:

- Runtime harness manifests.
- Codebase-discovered harness artifacts.
- Prompts, Skills, tools, policies, evals, scorers, context builders, memory interfaces, agent graphs, and model configs.
- Refinement operations.
- Patch bundles, gate reports, PR artifacts, rollouts, reviewer outcomes, and post-merge monitoring results.

State graph edges:

- Trace produced by harness state.
- Manifest references artifact.
- Issue implicates artifact.
- Refiner proposes operation.
- Operation creates, updates, deletes, or noops a component.
- Patch implements operation.
- Eval covers operation.
- Gate accepts or rejects operation.
- PR merges, edits, or rejects operation.
- Post-merge monitor confirms, regresses, or finds no measurable effect.

The state graph should answer:

- What harness produced this trace?
- Which traces motivated this change?
- Which component changed?
- What did LoopForge learn from the traces?
- What exact before/after diff is being proposed?
- Did the change pass gates?
- Did humans accept, edit, reject, or revert it?
- Did production behavior improve after merge?
- Is LoopForge repeatedly patching the same artifact, indicating a deeper architecture problem?

### 11.4 Refinement Operation Ledger

Every proposed harness edit should create a structured refinement operation before it becomes a patch or PR.

Required fields:

- `operation_id`
- `operation_type`: `create`, `update`, `delete`, or `noop`
- `component_type`: prompt, sub-agent, Skill, memory interface, tool, policy, eval, scorer, or harness artifact
- `artifact_id` and `artifact_path`
- `scope`: shadow, workflow, project, or org
- `issue_id` and `patch_id`
- `source_trace_ids`
- `source_eval_ids`
- `confidence`
- `rationale`
- `diff_summary`
- `expected_outcome`
- `validation_plan`
- `rollback_plan`
- `preview_diff`
- `provenance`
- `status`: drafted, gated, rejected, merged, or retired

The ledger is a trust primitive. It should let teams audit LoopForge's reasoning, measure recommendation quality, detect patch concentration, and train future refiners from accepted and rejected operations.

Before an operation becomes a patch bundle, the ledger should store a preview diff and an explicit reviewer boundary. For example, a workflow-scoped Skill trigger change may be reviewed by the agent team, while an org-scoped permission policy change should require security review.

### 11.5 Recommended Layout

Recommended layout:

```text
loopforge.yaml
.loopforge/
  index/
  manifests/
  issues/
  patches/
  refinements/
  reports/
harness/
  system.md
  developer.md
  policies/
    safety.md
    privacy.md
  skills/
    code-review.md
    browser.md
    spreadsheet.md
  tools/
    billing.yaml
    search.yaml
    ticketing.yaml
  routing.yaml
  permissions.yaml
  context.yaml
  memory-policy.yaml
evals/
  suites/
    core.yaml
    safety.yaml
    model-launch.yaml
  datasets/
    production-regressions.jsonl
    skill-routing.jsonl
  scorers/
    task_success.py
    tool_sequence.py
```

### 11.6 Artifact Types

| Type | Purpose | Example patch |
| --- | --- | --- |
| System prompt | Global role, chain of command, boundaries | Clarify how tool outputs should be treated as untrusted. |
| Developer prompt | Product-specific operating instructions | Require persistent task completion in a support agent. |
| Skill | Task-specific workflow | Add an anti-trigger for code review when user only asks for explanation. |
| Tool description | Tool use semantics | Clarify that `refund_customer` actually issues money movement. |
| Tool schema | Arguments and validation | Make `customer_id` required and reject email as a substitute. |
| Router policy | Model/tool/agent selection | Route billing disputes to billing specialist first. |
| Permission policy | Allow/deny/confirm actions | Require human confirmation for external email sends. |
| Context policy | Summarization and packing | Preserve latest user constraint over older summary. |
| Memory policy | Retrieval and write rules | Expose memory interface boundaries without owning memory internals. |
| Eval suite | Regression and safety gates | Add a trace replay test for the failed workflow. |

## 12. Failure Ontology

LoopForge needs a canonical failure ontology so teams can compare failure modes across agents. The ontology must be practical, not ornamental: each category should be diagnosable from traces, codebase context, or paired replay. If a category cannot usually be inferred with useful confidence, it should become an observability gap rather than a confident failure label.

This ontology is part of the product surface. It should be versioned, extensible, and stable enough for CI gates, dashboards, PR labels, integrations, and community eval packs. Local teams can add product-specific failure modes, but those modes should map to canonical IDs and layers.

Trace observability levels:

- Strong: usually visible from trace spans, inputs, outputs, tool calls, and user feedback.
- Medium: visible only when traces include richer context such as router decisions, retrieved documents, Skill spans, or approval spans.
- Weak: requires external ground truth, human labels, product state, or richer instrumentation.
- Paired replay: requires comparing baseline and candidate runs.

Failure layers:

| Layer | Meaning | Typical output |
| --- | --- | --- |
| Outcome | User-visible bad result or product quality failure. | Issue, eval case, severity ranking. |
| Mechanism | The likely internal reason the outcome occurred. | Harness patch, code patch, or instrumentation patch. |
| Governance | Missing control, missing eval, missing trace data, unsafe permissioning, or weak review process. | Gate, eval, policy, manifest, or observability improvement. |

LoopForge should avoid patching directly from outcome labels. For example, `TASK_COMPLETION_FAILURE` says the result was bad; it does not explain whether the right fix is a Skill update, tool schema change, routing change, or context policy change.

Runtime failure ontology:

| ID | Layer | Category | Description | Trace observability | Critical notes |
| --- | --- | --- | --- | --- | --- |
| USER_INTENT_MISMATCH | Outcome | Intent understanding | Agent pursued a materially different user goal than the one requested. | Medium | Often overlaps with ambiguity handling and task completion. Use only when the intended goal is clear from the conversation or user feedback. |
| AMBIGUITY_HANDLING_FAILURE | Mechanism | Interaction policy | Agent failed to ask a needed clarifying question, or asked unnecessary clarification when it had enough context. | Medium | Important for agents because many bad side effects begin as ambiguity failures. Needs conversation context and ideally user feedback. |
| PLAN_DECOMPOSITION_ERROR | Mechanism | Planning | Agent chose a poor sequence of steps even though the goal and available tools were appropriate. | Medium | Hard to infer from final output alone. Needs step traces or chain-of-action traces. |
| AGENT_OR_MODEL_ROUTING_ERROR | Mechanism | Routing | Request was routed to the wrong agent, model, sub-agent, or mode. | Medium | Strong only if routing spans are present. Otherwise this is usually an index or observability gap. |
| SKILL_ROUTING_ERROR | Mechanism | Skill routing | Required Skill did not trigger, or an irrelevant Skill triggered. | Medium | Combines prior miss and false-positive categories. Direction should be captured as metadata: `miss`, `false_positive`, or `wrong_skill`. |
| SKILL_PROCEDURE_DEFECT | Mechanism | Skill quality | Correct Skill triggered, but its workflow was incomplete, unsafe, or misaligned. | Medium | Often overlaps with planning and task completion. Use when evidence points to the Skill text or Skill workflow. |
| TOOL_SELECTION_ERROR | Mechanism | Tool use | Agent selected a tool that was inappropriate for the user goal or current state. | Strong when tool spans exist | One of the most useful categories. Requires knowing available tools and their intended semantics from the codebase index. |
| TOOL_ARGUMENT_SEMANTIC_ERROR | Mechanism | Tool use | Agent selected the right tool but supplied arguments that were semantically wrong, unsafe, incomplete, or stale. | Strong when arguments are traced | Better than generic "argument error" because the issue is often semantic, not just schema validity. |
| TOOL_RESULT_INTERPRETATION_ERROR | Mechanism | Tool use | Agent misread, ignored, overtrusted, or incorrectly summarized a tool result. | Medium | Requires tool output and final/action comparison. Very important for grounded agents. |
| ACTION_AUTHORIZATION_ERROR | Governance | Permissions | Agent took or attempted an action without appropriate user, human, policy, or system authorization. | Medium | Merges permission bypass and confirmation miss. Direction can be `missing_confirmation`, `forbidden_action`, or `over_blocked_action`. |
| STATE_OR_SIDE_EFFECT_ERROR | Outcome | State management | Agent caused, failed to prevent, or failed to verify an external state change. | Weak to Medium | Critical for real agents. Needs product state, audit logs, or tool side-effect metadata. |
| CONTEXT_ASSEMBLY_FAILURE | Mechanism | Context | Required context was omitted, stale, overwritten, truncated, or ranked below less relevant context. | Medium | Needs context/retrieval spans. Otherwise often indistinguishable from model reasoning failure. |
| MEMORY_INTERFACE_FAILURE | Mechanism | Memory interface | Retrieved memory was irrelevant, stale, missing, or a proposed memory write was low quality. | Medium | Keep as one category because memory internals may be out of scope. Direction should be `retrieval`, `write`, or `staleness`. |
| GROUNDING_OR_SOURCE_FAILURE | Outcome | Factuality | Agent made unsupported claims, failed to cite available sources, or contradicted provided evidence. | Weak to Medium | "Hallucination" is too broad. This category needs source context, retrieval spans, or human labels. |
| RESPONSE_CONTRACT_FAILURE | Outcome | Output contract | Agent returned a response that violated the expected structure, schema, tone boundary, or channel contract. | Strong | Includes prior format-contract failures. Tone-only cases are weaker unless user or product labels exist. |
| TASK_COMPLETION_FAILURE | Outcome | Task completion | Agent stopped early, skipped required work, or delivered an unusable final result. | Medium | Useful as an outcome label, but should not be the root cause when a more specific category is known. |
| RECOVERY_FAILURE | Mechanism | Resilience | Agent failed to recover from a tool error, missing context, rejected action, or invalid intermediate result. | Strong when error spans exist | Important for production reliability. |
| SAFETY_POLICY_ERROR | Governance | Safety | Agent over-refused benign requests or under-refused disallowed/risky requests. | Medium | Combines over-refusal and under-refusal. Direction must be metadata: `over_refusal` or `under_refusal`. Needs policy context. |
| COST_LATENCY_QUALITY_REGRESSION | Outcome | Operations | Agent behavior became materially slower, more expensive, or more resource-intensive for similar work. | Strong | Mostly metric-derived. It is a quality regression, not necessarily a user-visible failure. |
| MODEL_BEHAVIOR_REGRESSION | Outcome | Model launch | New model changed task success, tool use, safety, formatting, or cost under the same harness. | Paired replay | Not diagnosable from a single trace. Requires baseline and candidate runs. |
| OBSERVABILITY_GAP | Governance | Instrumentation | Trace data is insufficient to confidently diagnose the issue. | Strong | This should be a first-class finding. Sometimes the correct patch is better instrumentation, not prompt or Skill changes. |

Quality-system findings:

| ID | Description | Why separate from runtime failures |
| --- | --- | --- |
| EVAL_COVERAGE_GAP | Known or suspected issue is not covered by existing evals. | This is a testing gap discovered from failures, not itself a user-facing agent failure. |
| HARNESS_INDEX_GAP | LoopForge cannot confidently map behavior to prompts, Skills, tools, routes, policies, or code. | This blocks grounded diagnosis and should trigger discovery/index improvements. |
| JUDGE_UNCERTAINTY_GAP | LLM judges disagree, lack calibration, or cannot score the issue reliably. | This is an evaluation reliability problem, not necessarily an agent behavior problem. |

Retired or merged categories:

- `SKILL_TRIGGER_MISS` and `SKILL_TRIGGER_FALSE_POSITIVE` merge into `SKILL_ROUTING_ERROR`.
- `PERMISSION_BYPASS` and `CONFIRMATION_MISS` merge into `ACTION_AUTHORIZATION_ERROR`.
- `POLICY_OVER_REFUSAL` and `POLICY_UNDER_REFUSAL` merge into `SAFETY_POLICY_ERROR`.
- `FORMAT_CONTRACT_BREAK` becomes `RESPONSE_CONTRACT_FAILURE`.
- `HALLUCINATION` becomes `GROUNDING_OR_SOURCE_FAILURE`.
- `EVAL_GAP` becomes `EVAL_COVERAGE_GAP` and moves out of runtime failures.

Each issue can have multiple labels, but one primary root-cause label. If the trace evidence does not support a specific label, LoopForge should prefer `OBSERVABILITY_GAP`, lower confidence, or request richer instrumentation rather than pretending to know.

## 13. Patch Planning

LoopForge should produce candidate patches with explicit layer selection.

Patch candidates should include:

- Target artifact.
- Rationale.
- Trace evidence.
- Expected behavior change.
- Risk assessment.
- Scope.
- Human-readable before/after diff preview.
- New evals.
- Gate plan.
- Rollback plan.

### 13.1 Layer Selection Heuristics

| Symptom | Preferred patch layer |
| --- | --- |
| Same tool chosen incorrectly across many tasks | Tool description or router policy. |
| Tool arguments invalid despite correct tool | Tool schema, validators, examples. |
| Task type not recognized | Skill trigger or router policy. |
| Model ignores known rule | Prompt hierarchy or eval gate. |
| Safety refusal too broad | Safety policy examples and targeted evals. |
| Context missing in final answer | Context packing policy. |
| New model more verbose or less persistent | Developer prompt and model-specific evals. |
| Output schema invalid | Output contract, parser, schema gate, and eval coverage. |
| One-off app bug | Application code, not harness prompt. |

## 14. Acceptance Gates

Every proposed patch must pass gates before PR merge recommendation.

Gates should be stricter than the recommendation engine. The recommendation engine may be probabilistic; acceptance must require calibrated confidence, grounded evidence, and explicit review.

### 14.1 Required Gates

| Gate | Description | Default severity |
| --- | --- | --- |
| Schema gate | Valid config, trace, eval, and artifact schemas. | Blocking |
| Patch scope gate | Patch only touches declared artifacts. | Blocking |
| Grounding gate | Patch cites codebase artifacts, trace evidence, and eval cases that support the change. | Blocking |
| Runtime manifest gate | Trace evidence maps to the actual harness version, prompt hashes, tool schema hashes, and policy hashes used at runtime. | Blocking for behavior patches |
| Recommendation quality gate | Candidate patch clears confidence, minimality, and risk thresholds before it can become a PR. | Blocking |
| Expected outcome gate | Patch states the measurable behavior change, validation method, and rollback path. | Blocking |
| Diff preview gate | Reviewer can inspect before/after changes for every touched harness artifact. | Blocking |
| Replay gate | Failed traces now pass or improve. | Blocking for targeted issue |
| Regression gate | Existing core eval suite does not degrade beyond threshold. | Blocking |
| Safety gate | Safety evals do not regress. | Blocking |
| Format gate | Required structured outputs remain parseable. | Blocking |
| Cost/latency gate | Cost and latency stay within configured budget. | Warning or blocking |
| Evaluator validation gate | LLM-judge and scorer outputs meet validation-record requirements. | Blocking when evaluator used for blocking decisions |
| Human approval gate | Maintainer review required before merge. | Blocking |

### 14.2 Optional Gates

- Canary gate.
- A/B preference gate.
- Domain expert review.
- Security review.
- Privacy redaction review.
- Customer-specific contract gate.
- Accessibility or localization gate.

### 14.3 Gate Output

Gate reports should be machine-readable and human-readable:

```text
Gate result: rejected
Reason: regression on core/support/refund_policy x 3 cases
Target issue improvement: 5/5 traces fixed
Safety: pass
Cost: +3.1 percent
Recommendation: revise tool description patch; do not merge
```

### 14.4 Recommendation Quality Ladder

LoopForge should expose the quality level of every recommendation:

| Level | Meaning | Allowed action |
| --- | --- | --- |
| Observation | Something notable happened, but root cause is unclear. | Create issue only. |
| Hypothesis | Evidence suggests a likely root cause. | Create issue and request review. |
| Patch candidate | Proposed patch is grounded but not yet gated. | Write patch file; do not open PR. |
| Gated patch | Patch passed target, regression, safety, and grounding gates. | Open PR if policy allows. |
| Trusted pattern | Similar patch type has repeatedly passed and been accepted in this repo. | Open PR with lower review friction, never auto-merge by default. |

Bad recommendations are the fastest way to lose trust. The default system should optimize for high precision over high recall: it is better to miss a marginal patch opportunity than to spam maintainers with confident nonsense.

### 14.5 Side-Effect-Safe Replay

Trace replay must never accidentally repeat production side effects.

Replay should support:

- Recorded tool-output replay.
- Mocked external APIs.
- Frozen time and fixed environment metadata.
- Frozen retrieval snapshots.
- Blocked write tools by default.
- Synthetic approval responses.
- Explicit replay-mode markers in traces and tool spans.
- Tool side-effect classifications such as `read`, `draft`, `write`, `money_movement`, `external_message`, and `destructive`.
- Tenant-safe fixtures for customer-specific policies.

Any eval that would call a side-effecting tool must run against a mock, recorded output, sandbox account, or explicit dry-run implementation. If LoopForge cannot prove replay is side-effect-safe, the replay gate must fail closed.

### 14.6 Evaluator Validation

LoopForge should draft evaluators automatically, but every evaluator needs a validation record before it can influence blocking gates.

Requirements:

- One evaluator per failure mode or product contract.
- Binary pass/fail outputs where possible, with optional explanation fields.
- Clear positive and negative examples.
- Separate train, development, and test slices for judge prompt iteration.
- True positive rate and true negative rate reporting.
- Precision, recall, and confidence interval reporting when enough labels exist.
- Frozen judge prompt and frozen model configuration for each evaluator version.
- Read-test-once discipline for held-out test sets.
- Bootstrap confidence intervals for prevalence estimates.
- `pass^k` reliability measurement for repeated-run reliability.
- `pass@k` capability measurement only when multiple attempts are an intended product behavior.
- Reset-and-replay measurement to estimate repeated-run failure rates.

Evaluator validation should be AI-drafted and AI-maintained. Human labels or corrections are useful but not mandatory for first value. When human labels exist, they should calibrate the evaluator. When they do not exist, LoopForge should downgrade confidence and avoid using that evaluator as a blocking gate until enough evidence accumulates.

### 14.7 Probabilistic Discovery, Contractual Checks

LoopForge should not rely on brittle heuristics for discovery, diagnosis, or patch planning. Those stages should be probabilistic and semantic.

When objective behavior is knowable, LoopForge should use contractual checks:

- Schema validity.
- Required or forbidden side-effect classes.
- Permission and confirmation contracts.
- Output format contracts.
- Tool availability and tool argument contracts.
- Replay sandbox contracts.
- Cost and latency budgets.

Contractual checks are not the intelligence layer; they are release controls. They should be generated, selected, and maintained by the AI loop, then enforced consistently in CI and replay.

## 15. Trust And Safety Model

### 15.1 No Silent Production Mutation

LoopForge can run in three modes:

| Mode | Behavior |
| --- | --- |
| Suggest | Writes issue and patch files only. |
| PR | Opens a PR after gates pass. |
| Apply | Applies local patch for experimentation. Disabled by default. |

Production deployment is always outside the default automatic loop.

### 15.2 Privacy Defaults

Default trace ingestion should:

- Redact emails, phone numbers, secrets, tokens, and common identifiers.
- Hash stable user and session IDs.
- Store raw traces separately from normalized/redacted traces.
- Never include secrets in model calls.
- Allow local-only operation.
- Allow teams to use local models or approved model providers for probabilistic diagnosis.

### 15.3 Security Controls

- Tool call arguments containing secrets are masked.
- External LLM calls are disabled unless configured.
- Patch generator runs with read-only access to the repo except designated output paths.
- PR creation requires explicit credentials.
- Gate runner should run in an isolated process.
- Unsafe issue categories require human or security approval before PR merge or deployment.

### 15.4 Prompt Injection Defense

Tool outputs and traces are untrusted data. LoopForge must never treat trace content as instructions to LoopForge itself.

### 15.5 Recommendation Trust Architecture

Trust is easier to lose than to earn. LoopForge should be designed so low-quality recommendations are rare, visible, and recoverable.

Requirements:

- Default to high-precision recommendations, even if that means fewer patches.
- Require every behavior-changing recommendation to map to one or more refinement operations.
- Produce competing hypotheses when evidence is ambiguous.
- Distinguish trace evidence, codebase evidence, eval evidence, and model inference.
- Require codebase grounding before behavioral patch proposals.
- Require an eval addition or eval update for every behavior-changing patch.
- Use patch confidence, issue confidence, and artifact-discovery confidence separately.
- Cap automated PR volume so maintainers are never flooded.
- Label risky patches for security or domain review.
- Track recommendation acceptance, rejection, and revert rates.
- Track operation acceptance, rejection, merge, revert, and post-merge confirmation rates.
- Detect patch concentration when LoopForge repeatedly proposes edits to the same artifact or component type.
- Demote patch strategies that are repeatedly rejected in a repo.
- Never auto-merge by default.

## 16. Product UX Requirements

### 16.1 First 30 Minutes: Trust-Building Onboarding

A new user should be able to:

1. Install LoopForge.
2. Run `loopforge connect` to auto-detect and connect the likely trace source.
3. Run `loopforge discover` to create an AI-drafted harness map.
4. Run `loopforge shadow --last 24h` to pull traces and generate AI-drafted issue clusters.
5. See a first-value report with issue clusters, trace evidence, manifest coverage, harness-index confidence, replay readiness, and proposed evals.
6. Open or preview an AI-drafted eval PR.
7. See AI-drafted behavior-patch candidates ranked by confidence and autonomy level.
8. See the first refinement-operation ledger entries that explain exactly what LoopForge wants to change and why.

This onboarding path is not the MVP boundary. It is the first trust-building experience inside the broader MVP. The product may already support behavioral patch proposals, but onboarding should make the first visible value an AI-drafted, evidence-backed eval PR and a clear report on what the system can safely automate next.

### 16.2 First 60 Minutes: Useful Integration

Within one hour, a team should be able to generate setup PRs that make the system materially more useful:

1. Runtime harness manifest instrumentation PR.
2. Trace span enrichment PR.
3. Tool side-effect classification PR.
4. Side-effect-safe replay stub PR.
5. CI gate PR.
6. Default monitor config PR.
7. Starter eval suite PR from AI-observed failures.

### 16.3 First Week

A team should be able to:

1. Add CI gate.
2. Connect production trace export, polling, or subscription.
3. Keep the codebase/harness index updated automatically.
4. Create a baseline eval suite.
5. Merge at least one patch PR.
6. Generate a model launch comparison report.

### 16.4 Developer Ergonomics

Commands should be explicit, inspectable, and scriptable. Avoid hidden state.

Bad:

```bash
loopforge improve
```

Good:

```bash
loopforge mine --since 7d
loopforge propose ISSUE-17 --strategy smallest-safe-patch
loopforge gate PATCH-17-a --suite core
```

### 16.5 Autonomy Ramp

Teams should be able to increase LoopForge's autonomy by patch class:

| Level | Allowed behavior | Intended use |
| --- | --- | --- |
| 0. Observe and draft | Monitor traces, discover harness, draft issues, draft evals, draft patches. | Initial shadow mode. |
| 1. Eval PRs | Open AI-drafted PRs that add or update evals only. | First adoption step. |
| 2. Documentation and Skill PRs | Open AI-drafted PRs for Skill docs, examples, and low-risk procedural clarifications. | Early trust expansion. |
| 3. Tool description PRs | Open AI-drafted PRs for tool descriptions and non-permission semantics. | Mature workflow. |
| 4. Prompt and routing PRs | Open AI-drafted PRs for prompts, routing, and context policy changes. | Requires strong gates and reviewer confidence. |
| 5. Permission or side-effect policy PRs | Open AI-drafted PRs for authorization, confirmation, or side-effect behavior. | Requires security review by default. |

The MVP should support multiple levels. Onboarding should start with AI-observed and AI-drafted artifacts immediately, while restricting which artifacts can become PRs until trust gates pass.

## 17. MVP Scope

### 17.1 MVP Includes

- CLI.
- `loopforge connect` guided adapter setup.
- Local monitoring service with configurable schedules.
- Local file-based project.
- SQLite metadata store.
- Automated trace ingestion from configured sources.
- Codebase discovery and semantic harness index.
- Semantic index metadata for artifact tokens, structural anchors, import references, and retrieval text.
- Runtime harness manifest schema and trace linkage.
- Runtime manifest emission SDK helpers.
- Harness state graph sufficient to connect traces, manifests, artifacts, issues, patches, gates, PRs, and refinement operations.
- Refinement operation ledger with CRUD semantics, scope, expected outcome, validation plan, rollback plan, and preview diff.
- Confirmation report schema and post-merge effect classification.
- Refiner queue item schema and local queue commands.
- JSONL trace adapter.
- OpenTelemetry/OpenInference trace mapping.
- Langfuse export adapter.
- Phoenix export adapter.
- LangSmith export/API adapter where API access permits.
- Trace-observability-aware failure ontology.
- Probabilistic issue classification and semantic clustering.
- LLM-assisted diagnosis with local redaction.
- Candidate patch generation for Markdown and YAML harness artifacts.
- Component-specific refiner passes for prompts, Skills, tools, policies, evals, and memory-interface policies.
- Local probabilistic refiner-pass ranking with provider-neutral model interface.
- Subagent-spec recommendations for repeated delegation or specialist-review patterns.
- Async refiner queue with run budgets, retry, cancellation, dead-letter status, and a local worker that drafts patch/refinement artifacts from queued monitor runs.
- Patch concentration gate.
- Eval generation in YAML/JSONL.
- AI-drafted evaluator generation and validation records.
- Setup PR generation for manifests, trace enrichment, side-effect classes, replay stubs, CI, and monitor config.
- Side-effect-safe replay mode with recorded or mocked tool outputs.
- Hard acceptance gates for schemas, patch scope, permissions, safety, and regression results.
- LLM-as-judge scorer support.
- Gate report.
- Git patch export.
- GitHub PR creation.
- Autonomy ramp from read-only monitoring through gated behavior-patch PRs.
- Reviewer outcome tracking in the refinement ledger and issue event stream.
- Rollback artifact generation with opt-in reverse patch application.
- Visible "what LoopForge learned" reporting for issues, refinements, patches, and confirmations.
- Post-merge monitoring for failure-signature recurrence and patch confirmation.

### 17.2 MVP Excludes

- Hosted SaaS.
- Multi-tenant web dashboard.
- Automatic production deployment.
- Full prompt optimizer search.
- Fine-tuning.
- Online model weight updates or reward-model training.
- Owning memory implementation.
- Arbitrary code patches without explicit opt-in.
- Browser-based trace replay UI.
- Auto-merge of behavioral patches.
- Requiring human-authored ontologies or evals before first value.

## 18. Version 1.0 Scope

Version 1.0 should add:

- GitHub App.
- GitLab support.
- Hosted optional control plane.
- Web UI.
- OpenInference and OTLP native collector.
- Braintrust adapter where APIs permit.
- Promptfoo export/import.
- DSPy/GEPA integration for optimizer-backed patch candidates.
- Model launch simulation workflow.
- Canary monitoring workflow.
- Refiner benchmark suite with public fixtures for diagnosis, patch-layer selection, and operation quality.
- Harness co-learning export for successful operations, failed operations, traces, labels, evals, and reviewer outcomes.
- Organization-wide ontology reporting.
- Plugin SDK.

## 19. Integration Strategy

### 19.1 Trace Sources

Priority order:

1. OpenTelemetry/OpenInference.
2. Langfuse export/API.
3. Phoenix export/API.
4. LangSmith export/API.
5. JSONL universal trace format.
6. Braintrust export/API.
7. Custom adapter SDK.

### 19.2 Agent Frameworks

LoopForge should not depend on a framework. It should provide optional helpers for:

- LangChain/LangGraph.
- OpenAI Agents SDK.
- Vercel AI SDK.
- LlamaIndex.
- CrewAI.
- AutoGen/AG2.
- Mastra.
- Pydantic AI.
- Custom HTTP agents.

### 19.3 CI

Priority order:

1. GitHub Actions.
2. Local CLI.
3. GitLab CI.
4. Buildkite/CircleCI.

### 19.4 Evaluators

Support:

- Python scorers.
- TypeScript scorers later.
- LLM-as-judge scorers.
- JSON schema validators.
- Tool-sequence validators.
- Cost/latency budget checks.
- Pairwise comparison.

## 20. Adoption Strategy

### 20.1 Positioning

Do not lead with "self-improving agents." Lead with:

"Turn failed traces into reviewed harness PRs and regression evals."

This is concrete, trustworthy, and buyer-legible.

### 20.2 Distribution

- Open-source GitHub repo.
- `pipx install loopforge`.
- `uv tool install loopforge`.
- Docker image.
- GitHub Action.
- Example integrations for Langfuse, Phoenix, LangSmith, LangGraph, OpenAI Agents SDK.
- Public demo agent with intentionally failing traces.

### 20.3 Trust-Building Features

- Local-only mode.
- Redaction preview.
- Dry-run mode.
- No hidden mutation.
- Every LLM call logged.
- Hard release gates around probabilistic recommendations.
- Codebase grounding for every behavioral patch.
- Recommendation quality ladder.
- PRs include before/after evals.
- Patch size limits.
- Automated PR volume limits.
- Rollback commands.

### 20.4 Recommended Enterprise Pilot

For serious production agent teams, the recommended adoption path is a 30-day trust ramp:

| Period | Mode | Success question |
| --- | --- | --- |
| Days 1-7 | AI-observed shadow monitoring | Does LoopForge find real issues and map them to the harness accurately? |
| Days 8-14 | AI-drafted eval PRs | Are generated evals accepted and useful? |
| Days 15-21 | Low-risk Skill and tool-description PRs | Are behavior-adjacent recommendations precise enough for maintainers? |
| Days 22-30 | Gated behavior-patch PRs for selected patch classes | Do manifest, replay, regression, and reviewer outcomes justify more autonomy? |

The product should support more than this from day one, but this pilot path gives companies a safe way to earn trust before enabling higher autonomy levels.

### 20.5 Community Growth

Make the canonical failure ontology and eval recipes the community hub.

Possible community artifacts:

- `failure-ontology.yaml`.
- `agent-launch-gates.yaml`.
- `skill-trigger-evals/`.
- `tool-misuse-evals/`.
- `prompt-injection-regressions/`.
- `model-upgrade-playbooks/`.

## 21. Success Metrics

### 21.1 Product Metrics

- Time from trace ingestion to first issue.
- Time from issue to gated PR.
- Monitor freshness and trace coverage.
- Codebase index freshness and artifact discovery confidence.
- Percent of patches accepted.
- Percent of accepted patches with eval coverage.
- Targeted issue fix rate.
- Regression rate after merge.
- Model launch regression catch rate.
- Median setup time.
- Number of supported trace adapters.

### 21.2 Adoption Metrics

- GitHub stars and forks.
- Weekly active repos.
- CI gate runs per week.
- PRs opened by LoopForge.
- Accepted patch PRs.
- Community eval packs.
- Framework integrations contributed by community.

### 21.3 Quality Metrics

- False positive issue rate.
- False diagnosis rate.
- Bad recommendation rate.
- Patch revert rate.
- Maintainer edit distance on generated patches.
- Patch rejection reasons.
- LLM judge calibration drift.
- Evaluator true positive and true negative rates.
- Evaluator precision and recall by failure mode.
- Evaluator prevalence estimate confidence intervals.
- Pass^k reliability trend for critical workflows.
- Refinement operation acceptance rate by component type.
- Refinement operation revert rate by component type.
- Post-merge failure-signature reduction.
- Patch concentration score by artifact and component type.
- Refiner abstention quality on low-evidence traces.
- Safety eval pass rate.
- Redaction miss rate.

### 21.4 Trust Launch Thresholds

LoopForge should ship with conservative default thresholds that teams can tune:

| Metric | Default launch target | Why it matters |
| --- | --- | --- |
| Artifact mapping precision | 95 percent on reviewed artifacts | Bad codebase grounding poisons every downstream recommendation. |
| Runtime manifest coverage | 90 percent of production traces for behavior-patch mode | Behavior patches need to know what actually ran. |
| Issue precision | 80 percent of surfaced issues accepted as real by maintainers | Prevents issue spam. |
| Eval PR acceptance rate | 70 percent or higher during onboarding | The first trust experience should feel useful. |
| Behavioral patch PR acceptance rate | 50 percent or higher after ramp-up | Lower rates imply reviewer burden is too high. |
| Patch revert rate | Under 2 percent | Reverts are the clearest sign of trust damage. |
| Refinement operation rejection rate | Under 50 percent after onboarding ramp | High rejection implies the refiner is creating reviewer burden. |
| Post-merge confirmation rate | 70 percent or higher for merged operations with enough traffic | Closed-loop systems need evidence that shipped changes helped. |
| Patch concentration score | Alert when one artifact receives repeated edits without confirmation | Repeated edits can mean the patch layer is wrong or the architecture is weak. |
| Maintainer edit distance | Median under 30 percent for accepted PRs | High edit distance means the generated patch is not close enough. |
| Redaction miss rate | 0 known misses in release qualification | Privacy failures are existential. |
| Side-effect replay escape rate | 0 | Replay must never trigger real production effects. |
| Evaluator validation certificate | Configurable by domain, with minimum evidence before blocking use | Unvalidated evaluators should not block or approve releases. |
| Evaluator true positive rate | 90 percent or higher for blocking evaluators | Blocking gates must catch known failures. |
| Evaluator true negative rate | 90 percent or higher for blocking evaluators | Blocking gates must not create noisy false alarms. |

## 22. Competitive Landscape

LoopForge should acknowledge existing tools and win by composition.

| Tool | Strength | LoopForge relationship |
| --- | --- | --- |
| LangSmith Engine | Productized closed-loop trace issue and fix workflow | Inspiration and possible adapter target; LoopForge is OSS and repo-native. |
| Langfuse | OSS observability, prompts, evals, datasets | Ingest traces, emit datasets, optionally write prompt versions. |
| Phoenix | OSS observability, evals, prompt experiments | Ingest traces, emit experiments/datasets. |
| Braintrust | Strong eval workflows and production scoring | Export evals and ingest traces where possible. |
| Promptfoo | CI evals and red teaming | Emit promptfoo-compatible evals. |
| DSPy/GEPA | Prompt/program optimization | Use as optional optimizer backends. |
| OpenAI Evals | Eval framework | Export compatible eval data where useful. |

## 23. Roadmap

### Phase 0: Spec And Seed Repo

- Product spec.
- Engineering design.
- Canonical schemas.
- Demo traces.
- Demo harness.

### Phase 1: Local MVP

- CLI.
- Config.
- Scheduled monitor.
- Automated trace ingestion.
- Codebase discovery.
- Harness artifact index.
- Runtime harness manifest schema and SDK helpers.
- Harness state graph.
- Refinement operation ledger.
- Redaction.
- Probabilistic issue mining.
- Side-effect-safe replay.
- Autonomy ramp.
- Trust qualification report.
- Patch proposal.
- Component-specific refiner pass abstraction.
- Patch concentration gate.
- Eval generation.
- Local gates.
- Confirmation reports.
- Git patch export.

### Phase 2: PR Workflow

- GitHub PR creation.
- GitHub Action.
- PR comments.
- Gate status checks.
- Patch rollback metadata.
- Operation acceptance/rejection telemetry.
- Post-merge confirmation monitor.

### Phase 3: Continual Refinement

- Harness state graph.
- Component-specific refiner passes.
- Patch concentration detection.
- Failure signature memory.
- Refiner quality gates.
- Refiner benchmark fixtures.

### Phase 4: Integrations

- Langfuse adapter.
- Phoenix adapter.
- LangSmith adapter.
- OpenTelemetry/OpenInference collector.
- Promptfoo export.
- LangChain/LangGraph recipe.
- OpenAI Agents SDK recipe.

### Phase 5: Model Launch Simulator

- Replay prior traces against candidate model.
- Compare behavior deltas.
- Generate launch report.
- Recommend harness updates.
- Canary monitor.

### Phase 6: Optimizer Backends

- DSPy/GEPA optional patch candidates.
- Multi-candidate patch search.
- Budget-aware optimizer runs.
- Evaluator validation tooling.

### Phase 7: Harness Co-Learning Exports

- Export accepted and rejected operations as training data.
- Export trace windows with judge labels and reviewer outcomes.
- Export replay and gate outcomes as process-supervision data.
- Keep model training external to LoopForge unless explicitly enabled.

### Phase 8: Hosted Optional Layer

- Team dashboard.
- Shared issue board.
- Central artifact registry.
- Enterprise SSO.
- Private cloud deployment.

## 24. Risks And Mitigations

### 24.1 Trust-Critical Risk: Bad Recommendations

Bad recommendations or bad patches are the existential product risk. Once a team believes the system wastes reviewer time or makes unsafe changes, it will be removed and may not get another chance.

Mitigation must be architectural:

- Use high recommendation thresholds by default.
- Require codebase grounding and trace evidence for behavioral patches.
- Require a structured refinement operation for every proposed behavioral edit.
- Separate observation, hypothesis, patch candidate, gated patch, and trusted pattern levels.
- Show uncertainty and competing hypotheses.
- Gate patches before PR creation when configured.
- Add regression evals with every behavioral patch.
- Measure post-merge effect on the originating failure signature.
- Warn on repeated edits to the same artifact without measured improvement.
- Cap PR volume.
- Track maintainer rejections, edits, reverts, and muted issue categories.
- Learn repo-local reviewer preferences from accepted and rejected LoopForge PRs.
- Keep low-confidence behavior patches as report-only previews rather than PRs, while still AI-drafting the issue, eval, and patch candidate for learning.

### 24.2 Risk Table

| Risk | Impact | Mitigation |
| --- | --- | --- |
| Bad patches or bad recommendations degrade behavior | Loss of trust | Use the recommendation quality ladder, require grounding, gate all patches, require human review, cap PR volume, and learn from rejections. |
| LLM diagnoses wrong root cause | Wasted time | Evidence requirements, confidence scores, competing hypotheses. |
| Trace privacy leak | Severe | Local-first mode, redaction preview, no external LLM calls by default. |
| Prompt sediment | Harness becomes bloated | Patch right layer, max prompt diff budgets, prompt lint. |
| Repeated patching masks architecture issues | Local fixes accumulate without solving the root cause | Track patch concentration, require post-merge confirmation, and recommend architecture or instrumentation work when repeated operations do not reduce failures. |
| Eval overfitting | False confidence | Holdout suites, production canaries, diverse trace sampling. |
| Evaluator drift | Bad gate decisions | Evaluator validation records, hard gates, frozen judge configs, and periodic revalidation. |
| Too hard to adopt | Low adoption | Automatic discovery, scheduled monitoring, trace adapters, minimal config, framework recipes. |
| Existing tools see it as competitor | Ecosystem friction | Integrate and export rather than replace. |
| Automated changes feel unsafe | Rejection by security teams | PR-only default, audit logs, explicit allowlists. |

## 25. Product Decisions

1. Default mode is local, monitored, and PR-based.
2. The core abstraction is a versioned harness artifact, not a prompt.
3. The first use case is scheduled trace monitoring to gated PR.
4. The first technical integration target is OpenTelemetry/OpenInference plus Langfuse, Phoenix, LangSmith, and JSONL.
5. The first platform integration is GitHub.
6. The first storage backend is SQLite plus files.
7. Onboarding starts with AI-observed reports, AI-drafted eval PRs, and AI-drafted behavior-patch previews, while the MVP can still include broader behavior-patch capability.
8. Observation, failure analysis, evals, patches, and PRs are AI-drafted by default.
9. The failure ontology is canonical and versioned, with local extensions mapped back to canonical layers.
10. Probabilistic diagnosis and patching are logged and confidence-scored.
11. Eval generation is mandatory for every proposed fix unless explicitly disabled.
12. Evaluator validation records are required before evaluators can become blocking gates.
13. Contractual checks are used for objective product contracts, while discovery and diagnosis remain probabilistic.
14. Acceptance gates are stricter than patch generation.
15. Runtime harness manifests are preferred over repository inference when diagnosing a trace.
16. Replay must fail closed unless side-effect safety is proven.
17. LoopForge should understand the codebase before recommending behavior changes.
18. LoopForge should be useful even if the team never uses the optional web UI.
19. Every proposed harness edit should create a refinement operation with CRUD semantics, provenance, confidence, gate status, and reviewer outcome.
20. LoopForge should monitor whether merged operations reduce the originating failure signature before treating a pattern as trusted.
21. LoopForge should export accepted and rejected operations as future co-learning data, but model weight updates are outside the default product boundary.

## 26. Public References

- [LangSmith Engine](https://docs.langchain.com/langsmith/engine)
- [Langfuse](https://github.com/langfuse/langfuse)
- [Arize Phoenix](https://github.com/Arize-ai/phoenix)
- [Promptfoo](https://www.promptfoo.dev/docs/intro/)
- [DSPy](https://github.com/stanfordnlp/dspy)
- [GEPA](https://github.com/CerebrasResearch/gepa)
- [OpenAI Deployment Simulation](https://openai.com/index/deployment-simulation/)
- [OpenAI Model Spec](https://model-spec.openai.com/2025-04-11.html)
- [Anthropic Responsible Scaling Policy reflections](https://www.anthropic.com/news/reflections-on-our-responsible-scaling-policy)
- [Google DeepMind Frontier Safety](https://deepmind.google/frontier-safety/)
- [Meta Llama 4 model card](https://github.com/meta-llama/llama-models/blob/main/models/llama4/MODEL_CARD.md)
- [Continual Harness: Online Adaptation for Self-Improving Foundation Agents](https://arxiv.org/abs/2605.09998)
