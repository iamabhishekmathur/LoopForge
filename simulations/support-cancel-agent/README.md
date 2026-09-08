# Support Cancellation Agent Simulation

This simulation is a small agent repo with:

- A deliberately flawed support-agent harness.
- A destructive `cancel_subscription` tool definition.
- A recorded LangSmith-style observability export under `observability/langsmith/runs.json`.
- A runnable LoopForge scenario that ingests the provider fixture, mines failures, drafts evals, proposes a harness patch, runs gates, drafts a PR artifact, and writes a local dashboard.

Run it from the repository root:

```bash
python simulations/support-cancel-agent/run_simulation.py
```

The script bootstraps ignored local `.loopforge` state, resets prior generated artifacts, and writes `simulations/support-cancel-agent/simulation-output.md` with the exact command outputs.

Expected high-level result:

- `simulated-langsmith` is reported as a ready trace connector.
- LoopForge discovers the system prompt, Skill, permission policy, routing/context policy, and tool definition.
- LoopForge mines `ISSUE-0001` for side-effecting cancellation without approval.
- LoopForge drafts `EVAL-0001`.
- LoopForge drafts `PATCH-0001` against `harness/tools/cancel_subscription.yaml`.
- Gates pass with human review required.
