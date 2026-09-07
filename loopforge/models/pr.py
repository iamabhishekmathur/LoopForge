"""Pull request artifact model."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class PullRequestArtifact:
    pr_id: str
    patch_id: str
    issue_id: str
    title: str
    body: str
    branch_name: str
    status: str = "drafted"
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PullRequestArtifact":
        return cls(
            pr_id=str(data["pr_id"]),
            patch_id=str(data["patch_id"]),
            issue_id=str(data["issue_id"]),
            title=str(data["title"]),
            body=str(data["body"]),
            branch_name=str(data["branch_name"]),
            status=str(data.get("status") or "drafted"),
            metadata=dict(data.get("metadata") or {}),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "1",
            "pr_id": self.pr_id,
            "patch_id": self.patch_id,
            "issue_id": self.issue_id,
            "title": self.title,
            "body": self.body,
            "branch_name": self.branch_name,
            "status": self.status,
            "metadata": self.metadata,
        }
