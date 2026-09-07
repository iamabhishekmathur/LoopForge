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

LoopForge should never silently mutate production behavior.

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

## Documents

- [Product Spec](docs/product-spec.md)
- [Engineering Design](docs/engineering-design.md)
- [Evaluator Validation Schema](schemas/evaluator-validation.schema.json)
- [Gate Report Schema](schemas/gate-report.schema.json)
- [Harness Artifact Schema](schemas/harness-artifact.schema.json)
- [Issue Event Schema](schemas/issue-event.schema.json)
- [Issue Schema](schemas/issue.schema.json)
- [Runtime Harness Manifest Schema](schemas/runtime-harness-manifest.schema.json)
- [Trace Schema](schemas/trace.schema.json)
- [Trace Trajectory Schema](schemas/trace-trajectory.schema.json)

## MVP Wedge

The first 30 minute onboarding experience should build trust before asking for behavior-patch trust:

```text
loopforge init
loopforge connect
loopforge discover
loopforge shadow --last 24h
loopforge issues show ISSUE_ID
loopforge eval add --from-issue ISSUE_ID
loopforge pr --eval-only
```

The broader MVP can still support gated behavior-patch PRs:

```text
loopforge propose --issue ISSUE_ID
loopforge gate --patch PATCH_ID
loopforge pr --patch PATCH_ID
```

For teams using OpenTelemetry, OpenInference, Langfuse, Phoenix, LangSmith, Braintrust, or custom trace JSON, monitoring and ingestion should be adapter-based.

For teams using GitHub, PR generation should work out of the box. GitLab and local patch export can follow.

## Development

Run the CLI from source:

```bash
python -m loopforge --help
python -m loopforge init
python -m loopforge doctor
python -m loopforge schemas validate
```

Run the fixture-backed shadow loop:

```bash
cd fixtures/support-agent
PYTHONPATH=../.. python -m loopforge shadow --last 24h
PYTHONPATH=../.. python -m loopforge issues list
PYTHONPATH=../.. python -m loopforge issues show ISSUE-0001
```

Run tests:

```bash
pytest
```

## Design Principles

- Evidence over vibes.
- Automatic monitoring by default.
- AI-observed and AI-drafted by default.
- Probabilistic harness intelligence.
- Canonical failure ontology with local extensions.
- Codebase-grounded diagnosis.
- Runtime manifests over repository guesses.
- Validated evaluators before blocking gates.
- Human-approved release boundary by default.
- Local-first and self-hostable.
- Stack-neutral trace ingestion.
- Git-native harness artifacts.
- Small patches to the correct layer.
- Every accepted fix strengthens eval coverage.
- No production mutation without an explicit gate.
- Trust ramp from read-only monitoring to eval PRs to gated behavior-patch PRs.
- Privacy-preserving defaults.
- Works with existing tools rather than replacing them.

## Public Inspiration

LoopForge is meant to interoperate with, not replace, the existing ecosystem:

- [LangSmith Engine](https://docs.langchain.com/langsmith/engine) for trace-to-issue-to-fix workflows.
- [Langfuse](https://github.com/langfuse/langfuse) for open-source tracing, evals, prompts, datasets, and experiments.
- [Arize Phoenix](https://github.com/Arize-ai/phoenix) for open-source AI observability and evaluation.
- [Promptfoo](https://www.promptfoo.dev/docs/intro/) for prompt and LLM app evals in CI.
- [DSPy](https://github.com/stanfordnlp/dspy) and [GEPA](https://github.com/CerebrasResearch/gepa) for prompt and program optimization.
- [OpenAI Deployment Simulation](https://openai.com/index/deployment-simulation/) as a public example of replaying realistic conversations against candidate models.
- [Anthropic Responsible Scaling Policy](https://www.anthropic.com/news/reflections-on-our-responsible-scaling-policy) as an example of gated capability evaluation and mitigation.
- [Google DeepMind Frontier Safety](https://deepmind.google/frontier-safety/) as an example of lifecycle safety evaluation.
- [Meta Llama model cards](https://github.com/meta-llama/llama-models/blob/main/models/llama4/MODEL_CARD.md) as an example of system-level protections, red teaming, and app-context evaluation.
