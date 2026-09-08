"""SQLite persistence for the local LoopForge spine."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from .paths import LOCAL_DIR


SCHEMA = """
create table if not exists traces (
  trace_id text primary key,
  started_at text not null,
  payload_json text not null
);

create table if not exists trace_trajectories (
  trajectory_id text primary key,
  trace_id text not null,
  payload_json text not null,
  foreign key(trace_id) references traces(trace_id)
);

create table if not exists issues (
  issue_id text primary key,
  status text not null,
  payload_json text not null
);

create table if not exists issue_events (
  event_id text primary key,
  issue_id text not null,
  event_type text not null,
  payload_json text not null,
  created_at text not null,
  foreign key(issue_id) references issues(issue_id)
);

create table if not exists harness_artifacts (
  artifact_id text primary key,
  artifact_type text not null,
  path text not null,
  confidence real not null,
  payload_json text not null
);

create table if not exists eval_examples (
  eval_id text primary key,
  issue_id text not null,
  status text not null,
  payload_json text not null,
  foreign key(issue_id) references issues(issue_id)
);

create table if not exists evaluator_definitions (
  evaluator_id text primary key,
  eval_id text not null,
  issue_id text not null,
  status text not null,
  payload_json text not null,
  foreign key(eval_id) references eval_examples(eval_id),
  foreign key(issue_id) references issues(issue_id)
);

create table if not exists evaluator_validation_records (
  evaluator_id text primary key,
  validation_status text not null,
  blocking_gate_eligible integer not null,
  payload_json text not null,
  foreign key(evaluator_id) references evaluator_definitions(evaluator_id)
);

create table if not exists patch_bundles (
  patch_id text primary key,
  issue_id text not null,
  status text not null,
  payload_json text not null,
  foreign key(issue_id) references issues(issue_id)
);

create table if not exists gate_reports (
  gate_report_id text primary key,
  patch_id text not null,
  status text not null,
  recommendation text not null,
  payload_json text not null,
  foreign key(patch_id) references patch_bundles(patch_id)
);

create table if not exists pr_artifacts (
  pr_id text primary key,
  patch_id text not null,
  issue_id text not null,
  status text not null,
  payload_json text not null,
  foreign key(patch_id) references patch_bundles(patch_id),
  foreign key(issue_id) references issues(issue_id)
);

create table if not exists monitor_runs (
  run_id text primary key,
  status text not null,
  started_at text not null,
  finished_at text,
  payload_json text not null
);

create table if not exists runtime_manifests (
  manifest_id text primary key,
  created_at text not null,
  payload_json text not null
);
"""


class Store:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(path)
        self.connection.row_factory = sqlite3.Row
        self.connection.executescript(SCHEMA)
        self.connection.commit()

    @classmethod
    def for_project(cls, root: Path) -> "Store":
        return cls(root / LOCAL_DIR / "db.sqlite")

    def close(self) -> None:
        self.connection.close()

    def upsert_trace(self, trace: dict[str, Any]) -> None:
        self.connection.execute(
            """
            insert into traces(trace_id, started_at, payload_json)
            values (?, ?, ?)
            on conflict(trace_id) do update set
              started_at=excluded.started_at,
              payload_json=excluded.payload_json
            """,
            (
                trace["trace_id"],
                trace["started_at"],
                json.dumps(trace, sort_keys=True),
            ),
        )
        self.connection.commit()

    def upsert_trajectory(self, trajectory: dict[str, Any]) -> None:
        self.connection.execute(
            """
            insert into trace_trajectories(trajectory_id, trace_id, payload_json)
            values (?, ?, ?)
            on conflict(trajectory_id) do update set
              trace_id=excluded.trace_id,
              payload_json=excluded.payload_json
            """,
            (
                trajectory["trajectory_id"],
                trajectory["trace_id"],
                json.dumps(trajectory, sort_keys=True),
            ),
        )
        self.connection.commit()

    def upsert_issue(self, issue: dict[str, Any]) -> None:
        self.connection.execute(
            """
            insert into issues(issue_id, status, payload_json)
            values (?, ?, ?)
            on conflict(issue_id) do update set
              status=excluded.status,
              payload_json=excluded.payload_json
            """,
            (
                issue["issue_id"],
                issue["status"],
                json.dumps(issue, sort_keys=True),
            ),
        )
        self.connection.commit()

    def upsert_harness_artifact(self, artifact: dict[str, Any]) -> None:
        self.connection.execute(
            """
            insert into harness_artifacts(artifact_id, artifact_type, path, confidence, payload_json)
            values (?, ?, ?, ?, ?)
            on conflict(artifact_id) do update set
              artifact_type=excluded.artifact_type,
              path=excluded.path,
              confidence=excluded.confidence,
              payload_json=excluded.payload_json
            """,
            (
                artifact["artifact_id"],
                artifact["artifact_type"],
                artifact["path"],
                artifact["confidence"],
                json.dumps(artifact, sort_keys=True),
            ),
        )
        self.connection.commit()

    def add_issue_event(self, event: dict[str, Any]) -> None:
        self.connection.execute(
            """
            insert or ignore into issue_events(event_id, issue_id, event_type, payload_json, created_at)
            values (?, ?, ?, ?, ?)
            """,
            (
                event["event_id"],
                event["issue_id"],
                event["event_type"],
                json.dumps(event, sort_keys=True),
                event["created_at"],
            ),
        )
        self.connection.commit()

    def list_issues(self) -> list[dict[str, Any]]:
        rows = self.connection.execute(
            "select payload_json from issues order by issue_id"
        ).fetchall()
        return [json.loads(row["payload_json"]) for row in rows]

    def get_issue(self, issue_id: str) -> dict[str, Any] | None:
        row = self.connection.execute(
            "select payload_json from issues where issue_id = ?",
            (issue_id,),
        ).fetchone()
        return json.loads(row["payload_json"]) if row else None

    def list_harness_artifacts(self) -> list[dict[str, Any]]:
        rows = self.connection.execute(
            "select payload_json from harness_artifacts order by artifact_type, path"
        ).fetchall()
        return [json.loads(row["payload_json"]) for row in rows]

    def upsert_eval_example(self, eval_example: dict[str, Any]) -> None:
        self.connection.execute(
            """
            insert into eval_examples(eval_id, issue_id, status, payload_json)
            values (?, ?, ?, ?)
            on conflict(eval_id) do update set
              issue_id=excluded.issue_id,
              status=excluded.status,
              payload_json=excluded.payload_json
            """,
            (
                eval_example["eval_id"],
                eval_example["issue_id"],
                eval_example["status"],
                json.dumps(eval_example, sort_keys=True),
            ),
        )
        self.connection.commit()

    def upsert_evaluator_definition(self, evaluator: dict[str, Any]) -> None:
        self.connection.execute(
            """
            insert into evaluator_definitions(evaluator_id, eval_id, issue_id, status, payload_json)
            values (?, ?, ?, ?, ?)
            on conflict(evaluator_id) do update set
              eval_id=excluded.eval_id,
              issue_id=excluded.issue_id,
              status=excluded.status,
              payload_json=excluded.payload_json
            """,
            (
                evaluator["evaluator_id"],
                evaluator["eval_id"],
                evaluator["issue_id"],
                evaluator["status"],
                json.dumps(evaluator, sort_keys=True),
            ),
        )
        self.connection.commit()

    def upsert_evaluator_validation_record(self, validation: dict[str, Any]) -> None:
        self.connection.execute(
            """
            insert into evaluator_validation_records(
              evaluator_id, validation_status, blocking_gate_eligible, payload_json
            )
            values (?, ?, ?, ?)
            on conflict(evaluator_id) do update set
              validation_status=excluded.validation_status,
              blocking_gate_eligible=excluded.blocking_gate_eligible,
              payload_json=excluded.payload_json
            """,
            (
                validation["evaluator_id"],
                validation["validation_status"],
                1 if validation["blocking_gate_eligible"] else 0,
                json.dumps(validation, sort_keys=True),
            ),
        )
        self.connection.commit()

    def list_eval_examples(self) -> list[dict[str, Any]]:
        rows = self.connection.execute(
            "select payload_json from eval_examples order by eval_id"
        ).fetchall()
        return [json.loads(row["payload_json"]) for row in rows]

    def get_eval_example(self, eval_id: str) -> dict[str, Any] | None:
        row = self.connection.execute(
            "select payload_json from eval_examples where eval_id = ?",
            (eval_id,),
        ).fetchone()
        return json.loads(row["payload_json"]) if row else None

    def get_evaluator_for_eval(self, eval_id: str) -> dict[str, Any] | None:
        row = self.connection.execute(
            "select payload_json from evaluator_definitions where eval_id = ?",
            (eval_id,),
        ).fetchone()
        return json.loads(row["payload_json"]) if row else None

    def get_validation_for_evaluator(self, evaluator_id: str) -> dict[str, Any] | None:
        row = self.connection.execute(
            "select payload_json from evaluator_validation_records where evaluator_id = ?",
            (evaluator_id,),
        ).fetchone()
        return json.loads(row["payload_json"]) if row else None

    def list_validations_for_issue(self, issue_id: str) -> list[dict[str, Any]]:
        rows = self.connection.execute(
            """
            select v.payload_json
            from evaluator_validation_records v
            join evaluator_definitions e on e.evaluator_id = v.evaluator_id
            where e.issue_id = ?
            order by v.evaluator_id
            """,
            (issue_id,),
        ).fetchall()
        return [json.loads(row["payload_json"]) for row in rows]

    def list_evals_for_issue(self, issue_id: str) -> list[dict[str, Any]]:
        rows = self.connection.execute(
            "select payload_json from eval_examples where issue_id = ? order by eval_id",
            (issue_id,),
        ).fetchall()
        return [json.loads(row["payload_json"]) for row in rows]

    def upsert_patch_bundle(self, patch: dict[str, Any]) -> None:
        self.connection.execute(
            """
            insert into patch_bundles(patch_id, issue_id, status, payload_json)
            values (?, ?, ?, ?)
            on conflict(patch_id) do update set
              issue_id=excluded.issue_id,
              status=excluded.status,
              payload_json=excluded.payload_json
            """,
            (
                patch["patch_id"],
                patch["issue_id"],
                patch["status"],
                json.dumps(patch, sort_keys=True),
            ),
        )
        self.connection.commit()

    def list_patch_bundles(self) -> list[dict[str, Any]]:
        rows = self.connection.execute(
            "select payload_json from patch_bundles order by patch_id"
        ).fetchall()
        return [json.loads(row["payload_json"]) for row in rows]

    def get_patch_bundle(self, patch_id: str) -> dict[str, Any] | None:
        row = self.connection.execute(
            "select payload_json from patch_bundles where patch_id = ?",
            (patch_id,),
        ).fetchone()
        return json.loads(row["payload_json"]) if row else None

    def upsert_gate_report(self, report: dict[str, Any]) -> None:
        self.connection.execute(
            """
            insert into gate_reports(gate_report_id, patch_id, status, recommendation, payload_json)
            values (?, ?, ?, ?, ?)
            on conflict(gate_report_id) do update set
              patch_id=excluded.patch_id,
              status=excluded.status,
              recommendation=excluded.recommendation,
              payload_json=excluded.payload_json
            """,
            (
                report["gate_report_id"],
                report["patch_id"],
                report["status"],
                report["recommendation"],
                json.dumps(report, sort_keys=True),
            ),
        )
        self.connection.commit()

    def get_gate_report_for_patch(self, patch_id: str) -> dict[str, Any] | None:
        row = self.connection.execute(
            "select payload_json from gate_reports where patch_id = ? order by gate_report_id desc",
            (patch_id,),
        ).fetchone()
        return json.loads(row["payload_json"]) if row else None

    def list_gate_reports(self) -> list[dict[str, Any]]:
        rows = self.connection.execute(
            "select payload_json from gate_reports order by gate_report_id"
        ).fetchall()
        return [json.loads(row["payload_json"]) for row in rows]

    def upsert_pr_artifact(self, pr_artifact: dict[str, Any]) -> None:
        self.connection.execute(
            """
            insert into pr_artifacts(pr_id, patch_id, issue_id, status, payload_json)
            values (?, ?, ?, ?, ?)
            on conflict(pr_id) do update set
              patch_id=excluded.patch_id,
              issue_id=excluded.issue_id,
              status=excluded.status,
              payload_json=excluded.payload_json
            """,
            (
                pr_artifact["pr_id"],
                pr_artifact["patch_id"],
                pr_artifact["issue_id"],
                pr_artifact["status"],
                json.dumps(pr_artifact, sort_keys=True),
            ),
        )
        self.connection.commit()

    def list_pr_artifacts(self) -> list[dict[str, Any]]:
        rows = self.connection.execute(
            "select payload_json from pr_artifacts order by pr_id"
        ).fetchall()
        return [json.loads(row["payload_json"]) for row in rows]

    def get_pr_artifact(self, pr_id: str) -> dict[str, Any] | None:
        row = self.connection.execute(
            "select payload_json from pr_artifacts where pr_id = ?",
            (pr_id,),
        ).fetchone()
        return json.loads(row["payload_json"]) if row else None

    def upsert_monitor_run(self, run: dict[str, Any]) -> None:
        self.connection.execute(
            """
            insert into monitor_runs(run_id, status, started_at, finished_at, payload_json)
            values (?, ?, ?, ?, ?)
            on conflict(run_id) do update set
              status=excluded.status,
              finished_at=excluded.finished_at,
              payload_json=excluded.payload_json
            """,
            (
                run["run_id"],
                run["status"],
                run["started_at"],
                run.get("finished_at"),
                json.dumps(run, sort_keys=True),
            ),
        )
        self.connection.commit()

    def list_monitor_runs(self) -> list[dict[str, Any]]:
        rows = self.connection.execute(
            "select payload_json from monitor_runs order by started_at desc"
        ).fetchall()
        return [json.loads(row["payload_json"]) for row in rows]

    def get_monitor_run(self, run_id: str) -> dict[str, Any] | None:
        row = self.connection.execute(
            "select payload_json from monitor_runs where run_id = ?",
            (run_id,),
        ).fetchone()
        return json.loads(row["payload_json"]) if row else None

    def upsert_runtime_manifest(self, manifest: dict[str, Any]) -> None:
        self.connection.execute(
            """
            insert into runtime_manifests(manifest_id, created_at, payload_json)
            values (?, ?, ?)
            on conflict(manifest_id) do update set
              created_at=excluded.created_at,
              payload_json=excluded.payload_json
            """,
            (
                manifest["manifest_id"],
                manifest["created_at"],
                json.dumps(manifest, sort_keys=True),
            ),
        )
        self.connection.commit()

    def list_runtime_manifests(self) -> list[dict[str, Any]]:
        rows = self.connection.execute(
            "select payload_json from runtime_manifests order by created_at desc"
        ).fetchall()
        return [json.loads(row["payload_json"]) for row in rows]

    def get_runtime_manifest(self, manifest_id: str) -> dict[str, Any] | None:
        row = self.connection.execute(
            "select payload_json from runtime_manifests where manifest_id = ?",
            (manifest_id,),
        ).fetchone()
        return json.loads(row["payload_json"]) if row else None
