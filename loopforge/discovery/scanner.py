"""Codebase scanner for harness artifacts."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path

from loopforge.models.harness import HarnessArtifact


TEXT_SUFFIXES = {".md", ".txt", ".yaml", ".yml", ".json", ".jsonl", ".py", ".ts", ".tsx", ".js"}
SKIP_PARTS = {".git", ".loopforge", "__pycache__", ".pytest_cache", "node_modules", ".venv", "venv"}
TRACE_DATA_PARTS = {"traces", "observability", "logs"}


def discover_harness_artifacts(root: Path) -> list[HarnessArtifact]:
    artifacts: list[HarnessArtifact] = []
    indexed_at = datetime.now(timezone.utc).isoformat()

    for path in _iter_candidate_files(root):
        relative_path = path.relative_to(root).as_posix()
        content = _safe_read(path)
        if content is None:
            continue
        artifact = classify_artifact(relative_path, content, indexed_at)
        if artifact is not None:
            artifacts.append(artifact)

    return _with_relationships(artifacts)


def classify_artifact(path: str, content: str, indexed_at: str) -> HarnessArtifact | None:
    lowered_path = path.lower()
    lowered_content = content.lower()
    evidence: list[str] = []
    metadata: dict[str, object] = _content_metadata(content)

    if _looks_like_tool_definition(lowered_path, lowered_content):
        tool_name = _extract_scalar(content, "name")
        side_effect_class = _extract_scalar(content, "side_effect_class")
        if tool_name:
            evidence.append("declares tool name")
            metadata["tool_name"] = tool_name
        if side_effect_class:
            evidence.append("declares side_effect_class")
            metadata["side_effect_class"] = side_effect_class
        artifact_id = _artifact_id("tool", tool_name or path)
        return HarnessArtifact(
            artifact_id=artifact_id,
            artifact_type="tool_definition",
            path=path,
            symbol_or_anchor=tool_name,
            summary=f"Tool definition for {tool_name or path}.",
            confidence=0.92 if tool_name and side_effect_class else 0.82,
            discovered_by=["content_classifier", "repo_scanner"],
            last_indexed_at=indexed_at,
            metadata={"evidence": evidence, **metadata},
        )

    if "requires_confirmation" in lowered_content and "tools:" in lowered_content:
        tools = _extract_indented_keys_after(content, "tools")
        metadata["tools"] = tools
        return HarnessArtifact(
            artifact_id=_artifact_id("permission", path),
            artifact_type="permission_policy",
            path=path,
            summary="Permission policy with tool confirmation rules.",
            confidence=0.88,
            discovered_by=["content_classifier", "repo_scanner"],
            last_indexed_at=indexed_at,
            metadata={"evidence": ["declares tools", "declares requires_confirmation"], **metadata},
        )

    if _looks_like_system_prompt(lowered_path, lowered_content):
        return HarnessArtifact(
            artifact_id=_artifact_id("system-prompt", path),
            artifact_type="system_prompt",
            path=path,
            summary="System-level agent instructions.",
            confidence=0.81,
            discovered_by=["content_classifier", "repo_scanner"],
            last_indexed_at=indexed_at,
            metadata={
                "evidence": ["instructional prompt language", "harness path context"],
                **metadata,
            },
        )

    if _looks_like_skill(lowered_path, lowered_content):
        return HarnessArtifact(
            artifact_id=_artifact_id("skill", path),
            artifact_type="skill",
            path=path,
            summary="Agent skill instructions or workflow guidance.",
            confidence=0.79,
            discovered_by=["content_classifier", "repo_scanner"],
            last_indexed_at=indexed_at,
            metadata={"evidence": ["skill path or skill instructions"], **metadata},
        )

    if _looks_like_policy(lowered_path, lowered_content, "routing"):
        return HarnessArtifact(
            artifact_id=_artifact_id("routing", path),
            artifact_type="routing_policy",
            path=path,
            summary="Routing policy or agent dispatch guidance.",
            confidence=0.76,
            discovered_by=["content_classifier", "repo_scanner"],
            last_indexed_at=indexed_at,
            metadata={"evidence": ["routing policy signals"], **metadata},
        )

    if _looks_like_policy(lowered_path, lowered_content, "context"):
        return HarnessArtifact(
            artifact_id=_artifact_id("context", path),
            artifact_type="context_policy",
            path=path,
            summary="Context assembly or retrieval policy.",
            confidence=0.76,
            discovered_by=["content_classifier", "repo_scanner"],
            last_indexed_at=indexed_at,
            metadata={"evidence": ["context policy signals"], **metadata},
        )

    if lowered_path.endswith(".jsonl") and _looks_like_eval_dataset(content):
        return HarnessArtifact(
            artifact_id=_artifact_id("eval-dataset", path),
            artifact_type="eval_dataset",
            path=path,
            summary="JSONL eval or trace dataset.",
            confidence=0.74,
            discovered_by=["content_classifier", "repo_scanner"],
            last_indexed_at=indexed_at,
            metadata={
                "evidence": ["jsonl records with agent inputs or expected behavior"],
                **metadata,
            },
        )

    return None


def write_harness_index(root: Path, artifacts: list[HarnessArtifact]) -> Path:
    index_dir = root / ".loopforge" / "index"
    index_dir.mkdir(parents=True, exist_ok=True)
    path = index_dir / "harness-artifacts.json"
    payload = {
        "schema_version": "1",
        "artifact_count": len(artifacts),
        "artifacts": [artifact.to_dict() for artifact in artifacts],
    }
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return path


def _iter_candidate_files(root: Path) -> list[Path]:
    candidates: list[Path] = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        parts = path.relative_to(root).parts
        if any(part in SKIP_PARTS for part in parts):
            continue
        if any(part in TRACE_DATA_PARTS for part in parts):
            continue
        if path.suffix.lower() not in TEXT_SUFFIXES:
            continue
        candidates.append(path)
    return sorted(candidates)


def _safe_read(path: Path) -> str | None:
    try:
        content = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return None
    if len(content) > 250_000:
        return None
    return content


def _looks_like_tool_definition(path: str, content: str) -> bool:
    yaml_or_json_spec = path.endswith((".yaml", ".yml", ".json"))
    if yaml_or_json_spec:
        return (
            "name:" in content
            and ("description:" in content or "arguments:" in content)
            and ("side_effect_class:" in content or "parameters:" in content or "arguments:" in content)
        )
    code_tool_markers = ("@tool", "register_tool", "define_tool", "tool_definition")
    return (
        any(marker in content for marker in code_tool_markers)
        and "description" in content
        and ("side_effect_class" in content or "parameters" in content or "arguments" in content)
    )


def _looks_like_system_prompt(path: str, content: str) -> bool:
    if "you are " in content and ("agent" in content or "assistant" in content):
        return True
    return "system" in path and ("prompt" in path or "harness" in path)


def _looks_like_skill(path: str, content: str) -> bool:
    return "skill" in path and ("instructions" in content or "workflow" in content or "use when" in content)


def _looks_like_policy(path: str, content: str, policy_name: str) -> bool:
    return policy_name in path and ("policy" in content or policy_name in content)


def _looks_like_eval_dataset(content: str) -> bool:
    for line in content.splitlines()[:5]:
        stripped = line.strip()
        if not stripped:
            continue
        try:
            payload = json.loads(stripped)
        except json.JSONDecodeError:
            return False
        return "expected_behavior" in payload or "inputs" in payload or "spans" in payload
    return False


def _content_metadata(content: str) -> dict[str, object]:
    lines = content.splitlines()
    return {
        "sha256": hashlib.sha256(content.encode("utf-8")).hexdigest(),
        "line_count": len(lines),
        "size_bytes": len(content.encode("utf-8")),
        "signals": _content_signals(content),
        "semantic_tokens": _semantic_tokens(content),
        "anchors": _anchors(content),
        "imports": _imports(content),
        "embedding_text": _embedding_text(content),
    }


def _content_signals(content: str) -> list[str]:
    lowered = content.lower()
    signals = []
    for token in (
        "system",
        "tool",
        "skill",
        "requires_confirmation",
        "side_effect_class",
        "model",
        "router",
        "memory",
        "eval",
    ):
        if token in lowered:
            signals.append(token)
    return signals


def _semantic_tokens(content: str) -> list[str]:
    lowered = content.lower()
    tokens = []
    vocabulary = (
        "authorization",
        "confirmation",
        "destructive",
        "side effect",
        "routing",
        "retrieval",
        "memory",
        "evaluation",
        "scorer",
        "subagent",
        "handoff",
        "tool call",
        "schema",
        "context",
    )
    for token in vocabulary:
        if token in lowered:
            tokens.append(token.replace(" ", "_"))
    return tokens


def _anchors(content: str) -> list[dict[str, object]]:
    anchors: list[dict[str, object]] = []
    for line_number, line in enumerate(content.splitlines(), start=1):
        stripped = line.strip()
        if stripped.startswith("#"):
            anchors.append(
                {
                    "kind": "heading",
                    "line": line_number,
                    "text": stripped.lstrip("#").strip(),
                }
            )
        match = re.match(r"^(class|def|async def|function|export function)\s+([A-Za-z_][\w]*)", stripped)
        if match:
            anchors.append(
                {
                    "kind": "symbol",
                    "line": line_number,
                    "text": match.group(2),
                }
            )
    return anchors[:20]


def _imports(content: str) -> list[str]:
    imports = []
    for line in content.splitlines():
        stripped = line.strip()
        if stripped.startswith(("import ", "from ")) or stripped.startswith("const ") and "require(" in stripped:
            imports.append(stripped)
    return imports[:20]


def _embedding_text(content: str) -> str:
    non_empty = [line.strip() for line in content.splitlines() if line.strip()]
    return " ".join(non_empty[:12])[:1000]


def _extract_scalar(content: str, key: str) -> str | None:
    prefix = f"{key}:"
    for line in content.splitlines():
        stripped = line.strip()
        if stripped.startswith(prefix):
            value = stripped.split(":", 1)[1].strip()
            return value.strip("\"'") or None
    return None


def _extract_indented_keys_after(content: str, key: str) -> list[str]:
    lines = content.splitlines()
    for index, line in enumerate(lines):
        if line.strip() != f"{key}:":
            continue
        keys: list[str] = []
        for child in lines[index + 1 :]:
            if not child.startswith("  "):
                break
            stripped = child.strip()
            if stripped.endswith(":"):
                keys.append(stripped[:-1])
        return keys
    return []


def _with_relationships(artifacts: list[HarnessArtifact]) -> list[HarnessArtifact]:
    tool_by_name = {
        str(artifact.metadata.get("tool_name")): artifact
        for artifact in artifacts
        if artifact.artifact_type == "tool_definition" and artifact.metadata.get("tool_name")
    }
    updated: list[HarnessArtifact] = []
    for artifact in artifacts:
        relationships = list(artifact.relationships)
        if artifact.artifact_type == "permission_policy":
            for tool_name in artifact.metadata.get("tools", []):
                tool = tool_by_name.get(str(tool_name))
                if tool:
                    relationships.append(
                        {
                            "type": "governs_tool",
                            "target_artifact_id": tool.artifact_id,
                            "confidence": 0.91,
                            "evidence": [f"policy references tool `{tool_name}`"],
                        }
                    )
        updated.append(
            HarnessArtifact(
                artifact_id=artifact.artifact_id,
                artifact_type=artifact.artifact_type,
                path=artifact.path,
                symbol_or_anchor=artifact.symbol_or_anchor,
                summary=artifact.summary,
                confidence=artifact.confidence,
                discovered_by=artifact.discovered_by,
                last_indexed_at=artifact.last_indexed_at,
                relationships=relationships,
                metadata=artifact.metadata,
            )
        )
    return updated


def _artifact_id(prefix: str, value: str) -> str:
    slug = "".join(char.lower() if char.isalnum() else "-" for char in value).strip("-")
    while "--" in slug:
        slug = slug.replace("--", "-")
    return f"{prefix}-{slug or 'artifact'}"
