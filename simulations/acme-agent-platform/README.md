# Acme Agent Platform Simulation

This simulation models a larger agent-native company codebase with multiple agents, shared harness policy, side-effecting tools, and a LangSmith-style trace export.

It is intentionally more realistic than the small cancellation fixture:

- `support_agent` handles subscription and plan questions.
- `billing_agent` handles refunds and invoices.
- `escalation_agent` sends high-touch customer escalations.
- Shared harness files define prompts, Skills, routing, permissions, context assembly, and eval seeds.
- The runtime has a real enforcement flaw: it records policy but only logs confirmation warnings instead of blocking destructive tool calls.
- The trace export includes clean runs, recurring unsafe side effects, retrieval misses, and escalation noise.

Run it from the LoopForge repo root:

```bash
python simulations/acme-agent-platform/run_simulation.py
```

The script resets local `.loopforge` output, runs the customer-facing LoopForge commands, and writes `simulation-output.md`.

Expected high-level result:

- LoopForge discovers a multi-agent harness and ignores the observability export as source data.
- LoopForge ingests 12 trace records from the simulated LangSmith source.
- LoopForge mines one high-confidence authorization issue from recurring cancellation traces.
- LoopForge drafts an eval, validates it against positive and negative examples, queues refinement work, proposes a patch, runs gates, writes a resolution plan, and builds a dashboard.
- The resolution plan should rank runtime enforcement and trace instrumentation above a wording-only patch because the policy already requires confirmation.
