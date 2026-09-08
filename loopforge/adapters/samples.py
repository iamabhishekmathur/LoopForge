"""Sample trace source configs for customer onboarding."""

from __future__ import annotations


SAMPLE_CONFIGS: dict[str, str] = {
    "jsonl": """traces:
  sources:
    - id: local-jsonl
      type: jsonl
      path: traces/*.jsonl
""",
    "langsmith": """traces:
  sources:
    - id: prod-langsmith
      type: langsmith
      base_url: https://api.smith.langchain.com
      project: YOUR_LANGSMITH_PROJECT
      limit: 100
      pagination: cursor
""",
    "langfuse": """traces:
  sources:
    - id: prod-langfuse
      type: langfuse
      base_url: https://cloud.langfuse.com
      limit: 100
      pagination: cursor
""",
    "braintrust": """traces:
  sources:
    - id: prod-braintrust
      type: braintrust
      base_url: https://api.braintrust.dev
      project: YOUR_BRAINTRUST_PROJECT
      limit: 100
      pagination: cursor
""",
    "phoenix": """traces:
  sources:
    - id: prod-phoenix
      type: phoenix
      base_url: http://localhost:6006
      project: YOUR_PHOENIX_PROJECT
      limit: 100
""",
    "opentelemetry": """traces:
  sources:
    - id: otel-collector
      type: opentelemetry
      url: http://localhost:4318/v1/traces
      limit: 100
""",
    "openinference": """traces:
  sources:
    - id: openinference
      type: openinference
      url: http://localhost:4318/v1/traces
      limit: 100
""",
    "http": """traces:
  sources:
    - id: internal-trace-api
      type: http
      url: https://internal.example.com/agent-traces?project=YOUR_AGENT&limit=100
      pagination: cursor
      max_pages: 5
""",
    "fixture": """traces:
  sources:
    - id: offline-provider-fixture
      type: langsmith
      fixture_path: observability/langsmith/runs.json
""",
    "s3": """traces:
  sources:
    - id: s3-export
      type: jsonl
      path: traces/exported-from-s3/*.jsonl
""",
    "gcs": """traces:
  sources:
    - id: gcs-export
      type: jsonl
      path: traces/exported-from-gcs/*.jsonl
""",
}


def sample_config(provider: str) -> str:
    normalized = provider.lower()
    if normalized not in SAMPLE_CONFIGS:
        choices = ", ".join(sorted(SAMPLE_CONFIGS))
        raise ValueError(f"unknown connector sample {provider!r}; choose one of: {choices}")
    return SAMPLE_CONFIGS[normalized]


def sample_config_names() -> list[str]:
    return sorted(SAMPLE_CONFIGS)
