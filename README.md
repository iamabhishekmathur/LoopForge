# Agent Harness Loop

Working product name: LoopForge

LoopForge is an open-source, repo-native monitoring and improvement engine for AI agent harnesses. It continuously watches traces, discovers the harness from the codebase, drafts recurring failure analysis, and turns issues into reviewed harness patches, validated regression evals, and CI gates.

The goal is simple: make agent teams closed-loop by default.

## Why This Exists

Most agent teams already have some combination of logs, traces, prompt files, tool definitions, and evals. The hard part is connecting them into a reliable improvement loop:

```text
monitor traces -> discover harness -> failure issue -> diagnosed root cause -> candidate harness patch -> eval coverage -> gate -> PR -> rollout -> monitor
```

Today that loop is usually manual. Engineers inspect traces, guess at prompt or tool changes, hand-write a few evals, and hope the next model launch does not break the harness in a new way.

LoopForge makes that loop explicit, scheduled, probabilistic, grounded in the codebase, and reviewable.

The key product stance is: draft continuously, release visibly. LoopForge can observe traces, infer recurring issues, draft harness changes, generate evals, and run gates automatically, but every production-facing recommendation should carry trace evidence, codebase grounding, a before/after diff preview, expected outcome, validation plan, rollback plan, and scoped reviewer boundary.

## Core Promise

Given configured trace sources and a codebase, LoopForge should:

1. Monitor traces automatically on a configured cadence.
2. Link each trace to the runtime harness manifest for what actually executed.
3. Discover system prompts, Skills, tools, routes, policies, context code, and evals from the repository.
4. Identify recurring harness failures with probabilistic, semantic analysis.
5. Draft issue clusters, evals, patches, and PRs automatically.
6. Explain the likely root cause with trace, manifest, and codebase evidence.
7. Propose the smallest useful patch to the right harness layer.
8. Generate and validate regression evals that would have caught the failure.
9. Run acceptance gates against the patch.
10. Open a PR with the diff, evidence, eval results, and rollback notes.
11. Monitor post-merge traces to confirm whether the failure signature decreased.

LoopForge should never silently mutate production behavior.

Refinement scope is explicit: `shadow`, `workflow`, `project`, or `org`. Higher scopes require stronger evidence, stronger gates, and more explicit review.

## Harness Layers

LoopForge treats the harness as a versioned set of artifacts, not just a prompt:

```text
harness/
  system.md
  developer.md
  skills/
    spreadsheet.md
    browser.md
    code-review.md
  tools/
    search.yaml
    billing.yaml
    ticketing.yaml
  routing.yaml
  permissions.yaml
  context.yaml
  memory-policy.yaml
evals/
  suites/
  datasets/
  scorers/
loopforge.yaml
```

The project can also adapt to existing layouts. Teams should not have to reorganize their agent repo to try it.

## Reference
- [Trace Source Setup](docs/trace-source-setup.md)
- [Confirmation Report Schema](schemas/confirmation-report.schema.json)
- [Eval Example Schema](schemas/eval-example.schema.json)
- [Evaluator Definition Schema](schemas/evaluator-definition.schema.json)
- [Evaluator Validation Schema](schemas/evaluator-validation.schema.json)
- [Failure Diagnosis Schema](schemas/failure-diagnosis.schema.json)
- [Gate Report Schema](schemas/gate-report.schema.json)
- [Harness Artifact Schema](schemas/harness-artifact.schema.json)
- [Harness State Schema](schemas/harness-state.schema.json)
- [Issue Event Schema](schemas/issue-event.schema.json)
- [Issue Schema](schemas/issue.schema.json)
- [Monitor Run Schema](schemas/monitor-run.schema.json)
- [Patch Bundle Schema](schemas/patch-bundle.schema.json)
- [PR Artifact Schema](schemas/pr-artifact.schema.json)
- [Redaction Preview Schema](schemas/redaction-preview.schema.json)
- [Refinement Operation Schema](schemas/refinement-operation.schema.json)
- [Refiner Queue Item Schema](schemas/refiner-queue-item.schema.json)
- [Replay Report Schema](schemas/replay-report.schema.json)
- [Resolution Plan Schema](schemas/resolution-plan.schema.json)
- [Runtime Harness Manifest Schema](schemas/runtime-harness-manifest.schema.json)
- [Trace Schema](schemas/trace.schema.json)
- [Trace Sync State Schema](schemas/trace-sync-state.schema.json)
- [Trace Trajectory Schema](schemas/trace-trajectory.schema.json)

## Install Into An Agent Repo

Run these commands from the root of the customer's agent codebase.

### 1. Install LoopForge

For local development from this repository:

```bash
python -m pip install -e ".[dev]"
```

For a packaged install after release:

```bash
pipx install loopforge
```

Success looks like:

```bash
loopforge --help
```

### 2. Initialize The Repo

```bash
loopforge init
```

For common agent stacks, start with a framework recipe:

```bash
loopforge init --framework langgraph
loopforge init --framework openai-agents
loopforge init --framework vercel-ai
```

This creates `loopforge.yaml` and a local `.loopforge/` workspace. The config file tells LoopForge what project it is inspecting, where traces come from, how monitoring should run, and which gates must pass before a patch becomes reviewable.

Success looks like:

```text
loopforge.yaml
.loopforge/agent-profile.md
.loopforge/connectors/
.loopforge/issues/
.loopforge/patches/
.loopforge/reports/
```

### 3. Point LoopForge At Traces

Edit `loopforge.yaml` so `traces.sources` points at the customer's observability system. See [Trace Source Setup](docs/trace-source-setup.md) for provider choices, credential guidance, cloud storage paths, expected trace fields, and troubleshooting.

Generate a starter block when the traces live in a known provider:

```bash
loopforge connectors sample-config langsmith
loopforge connectors sample-config langfuse
loopforge connectors sample-config http
```

Local JSONL traces:

```yaml
traces:
  sources:
    - id: local-jsonl
      type: jsonl
      path: traces/*.jsonl
```

Recorded provider export for offline validation:

```yaml
traces:
  sources:
    - id: staging-langsmith
      type: langsmith
      fixture_path: observability/langsmith/runs.json
```

Hosted provider endpoint:

```yaml
traces:
  sources:
    - id: prod-langsmith
      type: langsmith
      base_url: https://api.smith.langchain.com
      project: support-agent
      limit: 100
      pagination: cursor
```

Use environment variables for hosted credentials, such as `LANGSMITH_API_KEY`, `LANGFUSE_PUBLIC_KEY`, or `BRAINTRUST_API_KEY`.

Success looks like:

```bash
loopforge connectors doctor
```

The connector should report `ready` for local files, recorded fixtures, or fully credentialed hosted sources.

### 4. Run The Safety Gate

```bash
loopforge readiness
```

This checks project shape, connector usability, packaged schemas, and a local redaction preview. If it fails, fix this before asking engineers to trust any recommendation.

### 5. Build The First Harness Index

```bash
loopforge discover
```

Success looks like a list of discovered harness artifacts: system prompts, Skills, tool definitions, routing policy, context policy, permission policy, and eval datasets where present.

### 6. Run The First Closed Loop

```bash
loopforge monitor --once --last 24h
loopforge queue run-next
loopforge issues list
loopforge refinements list
```

If LoopForge finds a recurring issue, inspect the recommendation:

```bash
loopforge issues show ISSUE-0001
loopforge issues resolution-plan ISSUE-0001
loopforge evals show EVAL-0001
loopforge refinements preview REFINE-0001-0001
loopforge gate PATCH-0001
loopforge pr --dry-run PATCH-0001
```

The right first outcome is not automatic mutation. It is a trace-backed issue, a grounded harness patch, a drafted regression eval, gates, and a reviewable PR artifact.

## AI Issue Judge

LoopForge can identify issues with a pluggable judge. The default mode is local and offline, but teams can opt into recorded AI-judge fixtures for repeatable testing or a live OpenAI-compatible chat endpoint for model-based issue discovery.

Recorded judge fixture:

```yaml
analysis:
  issue_judge: json_file
  issue_judge_path: observability/judges/issue-diagnosis.json
```

Live OpenAI-compatible judge:

```yaml
analysis:
  issue_judge: openai_compatible
  issue_judge_endpoint: https://api.openai.com/v1/chat/completions
  issue_judge_model: gpt-4.1-mini
  issue_judge_api_key_env: OPENAI_API_KEY

redaction:
  external_llm_allowed: true
```

Live judging stays off unless `redaction.external_llm_allowed` is explicitly true. The judge receives compact traces, trajectories, harness-artifact summaries, and any local fallback diagnosis. It must either return a confidence-bearing diagnosis or abstain. Patch generation and PR opening remain gated separately.

## Fast Adoption Path

The first 30 minutes should prove LoopForge can inspect the repo, read traces, and draft evidence-backed artifacts without changing production behavior:

```text
loopforge demo --path /tmp/loopforge-demo --force
loopforge init
loopforge init --framework langgraph
loopforge readiness
loopforge redact preview
loopforge connectors doctor
loopforge discover
loopforge states list
loopforge shadow --last 24h
loopforge issues show ISSUE_ID
loopforge issues resolution-plan ISSUE_ID
loopforge evals show EVAL_ID
```

After the first trusted run, use the gated patch workflow:

```text
loopforge monitor --once
loopforge propose ISSUE_ID
loopforge propose ISSUE_ID --layer system_prompt
loopforge refinements list
loopforge refinements preview OPERATION_ID
loopforge queue list
loopforge queue run-next
loopforge gate PATCH_ID
loopforge confirm PATCH_ID --observed-traces 50 --recurring-failures 0
loopforge confirmations list
loopforge review OPERATION_ID merged
loopforge learned
loopforge rollback PATCH_ID
loopforge pr --dry-run PATCH_ID
loopforge pr open PR_ID
```

`loopforge monitor --once` writes a queued refiner job after trace ingestion and issue mining. `loopforge queue run-next` processes that job asynchronously and drafts patch/refinement artifacts without blocking trace collection.

Each configured trace source writes local sync state under `.loopforge/connectors`, including high-watermark timestamps and last trace IDs. Hosted adapters can use that state to request incremental windows when the provider API supports timestamp or cursor-style parameters.

For teams using OpenTelemetry, OpenInference, Langfuse, Phoenix, LangSmith, Braintrust, or custom trace JSON, monitoring and ingestion should be adapter-based. Direct S3/GCS/warehouse polling is not implemented yet; use a scheduled export into local JSONL or expose an internal HTTP endpoint, then let LoopForge run on a schedule.

For teams using GitHub, PR generation should work out of the box. GitLab and local patch export can follow.

## Customer Test Gate

Before putting LoopForge in front of a teammate, run the finite readiness path:

```bash
python -m loopforge demo --path /tmp/loopforge-demo --force
cd /tmp/loopforge-demo
python -m loopforge readiness
python -m loopforge refinements preview REFINE-0001-0001
python -m loopforge redact preview
```

Then run the same gate in the candidate agent repository:

```bash
python -m loopforge init --framework generic  # only if loopforge.yaml is not present yet
python -m loopforge readiness
python -m loopforge onboard --last 24h
python -m loopforge refinements list
```

`loopforge readiness` passes only when the project is initialized, configured trace connectors are usable, packaged schemas parse, and the local redaction preview finds no sensitive-looking values. This is intentionally conservative: bad recommendations or privacy surprises erode trust faster than any feature can rebuild it.

## Simulation

LoopForge includes two local simulations. The compact [simulations/support-cancel-agent](simulations/support-cancel-agent) scenario models a flawed support agent harness, a LangSmith-style observability export, and the full LoopForge run from connector checks through PR artifact generation:

```bash
python simulations/support-cancel-agent/run_simulation.py
```

The larger [simulations/acme-agent-platform](simulations/acme-agent-platform) scenario models a multi-agent support company with support, billing, and escalation agents, noisy production traces, validated evals, gates, and issue resolution planning:

```bash
python simulations/acme-agent-platform/run_simulation.py
```

Each generated `simulation-output.md` shows the exact outputs a new user should expect, including discovered harness artifacts, `ISSUE-0001`, `EVAL-0001`, `PATCH-0001`, a gate report, a resolution plan, and a dry-run PR artifact.

Hosted trace sources can be configured with either a recorded fixture for local
validation or a live HTTP endpoint:

```yaml
traces:
  sources:
    - id: prod-langsmith
      type: langsmith
      base_url: https://api.smith.langchain.com
      project: support-agent
      limit: 100
```

## Development

Run the CLI from source:

```bash
python -m loopforge --help
python -m loopforge init
python -m loopforge init --framework openai-agents
python -m loopforge onboard
python -m loopforge doctor
python -m loopforge readiness
python -m loopforge demo --path /tmp/loopforge-demo --force
python -m loopforge redact preview
python -m loopforge connectors list
python -m loopforge connectors doctor
python -m loopforge connectors sample-config langsmith
python -m loopforge discover
python -m loopforge manifest show
python -m loopforge states list
python -m loopforge states show
python -m loopforge monitor --once
python -m loopforge monitor --list-runs
python -m loopforge queue list
python -m loopforge queue run-next
python -m loopforge dashboard build
python -m loopforge evals list
python -m loopforge issues resolution-plan ISSUE-0001
python -m loopforge propose ISSUE-0001
python -m loopforge patches list
python -m loopforge refinements list
python -m loopforge refinements preview REFINE-0001-0001
python -m loopforge replay PATCH-0001
python -m loopforge gate PATCH-0001
python -m loopforge confirm PATCH-0001 --observed-traces 50 --recurring-failures 0
python -m loopforge confirmations list
python -m loopforge review REFINE-0001-0001 merged
python -m loopforge learned
python -m loopforge rollback PATCH-0001
python -m loopforge pr --dry-run PATCH-0001
python -m loopforge pr open PR-PATCH-0001
python -m loopforge schemas validate
```

Real GitHub PR opening is disabled by default. To enable it, set `open_prs: true`
and keep `max_prs_per_day` above zero in `loopforge.yaml`; LoopForge will still
require a clean working tree, a gated patch, and a drafted PR artifact.

Run the fixture-backed shadow loop:

```bash
cd fixtures/support-agent
PYTHONPATH=../.. python -m loopforge shadow --last 24h
PYTHONPATH=../.. python -m loopforge monitor --once --last 24h
PYTHONPATH=../.. python -m loopforge monitor --list-runs
PYTHONPATH=../.. python -m loopforge queue list
PYTHONPATH=../.. python -m loopforge queue run-next
PYTHONPATH=../.. python -m loopforge issues list
PYTHONPATH=../.. python -m loopforge issues show ISSUE-0001
PYTHONPATH=../.. python -m loopforge issues resolution-plan ISSUE-0001
PYTHONPATH=../.. python -m loopforge evals list
PYTHONPATH=../.. python -m loopforge evals show EVAL-0001
PYTHONPATH=../.. python -m loopforge propose ISSUE-0001
PYTHONPATH=../.. python -m loopforge patches show PATCH-0001
PYTHONPATH=../.. python -m loopforge refinements list
PYTHONPATH=../.. python -m loopforge refinements preview REFINE-0001-0001
PYTHONPATH=../.. python -m loopforge gate PATCH-0001
PYTHONPATH=../.. python -m loopforge confirm PATCH-0001 --observed-traces 10 --recurring-failures 0
PYTHONPATH=../.. python -m loopforge confirmations list
PYTHONPATH=../.. python -m loopforge review REFINE-0001-0001 merged
PYTHONPATH=../.. python -m loopforge learned
PYTHONPATH=../.. python -m loopforge rollback PATCH-0001
PYTHONPATH=../.. python -m loopforge pr --dry-run PATCH-0001
```

Run tests:

```bash
pytest
```

Run with Docker:

```bash
docker build -t loopforge .
docker run --rm -v "$PWD:/workspace" -w /workspace loopforge monitor --once
```

GitHub Actions example: [examples/github-action.yml](examples/github-action.yml).

Runtime SDK example: [examples/runtime_sdk.py](examples/runtime_sdk.py).

Framework runtime examples:

- [LangGraph-style runtime metadata](examples/langgraph_runtime.py)
- [OpenAI Agents SDK-style runtime metadata](examples/openai_agents_runtime.py)

Release checklist: [RELEASE.md](RELEASE.md).
