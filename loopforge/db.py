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

create table if not exists hypothesis_findings (
  finding_id text primary key,
  trace_id text not null,
  finding_type text not null,
  status text not null,
  confidence real not null,
  payload_json text not null,
  foreign key(trace_id) references traces(trace_id)
);

create table if not exists resolution_plans (
  plan_id text primary key,
  issue_id text not null,
  status text not null,
  generated_at text not null,
  payload_json text not null,
  foreign key(issue_id) references issues(issue_id)
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

create table if not exists refinement_operations (
  operation_id text primary key,
  operation_type text not null,
  component_type text not null,
  issue_id text not null,
  patch_id text not null,
  status text not null,
  created_at text not null,
  payload_json text not null,
  foreign key(issue_id) references issues(issue_id),
  foreign key(patch_id) references patch_bundles(patch_id)
);

create table if not exists gate_reports (
  gate_report_id text primary key,
  patch_id text not null,
  status text not null,
  recommendation text not null,
  payload_json text not null,
  foreign key(patch_id) references patch_bundles(patch_id)
);

create table if not exists confirmation_reports (
  confirmation_id text primary key,
  patch_id text not null,
  issue_id text not null,
  status text not null,
  outcome text not null,
  payload_json text not null,
  foreign key(patch_id) references patch_bundles(patch_id),
  foreign key(issue_id) references issues(issue_id)
);

create table if not exists replay_reports (
  replay_id text primary key,
  patch_id text not null,
  status text not null,
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

create table if not exists harness_states (
  state_id text primary key,
  source text not null,
  created_at text not null,
  payload_json text not null
);

create table if not exists refiner_queue (
  queue_item_id text primary key,
  trigger text not null,
  status text not null,
  trace_window text not null,
  target_scope text not null,
  created_at text not null,
  started_at text,
  finished_at text,
  payload_json text not null
);

create table if not exists search_sessions (
  session_id text primary key,
  issue_id text not null,
  status text not null,
  created_at text not null,
  updated_at text not null,
  payload_json text not null,
  foreign key(issue_id) references issues(issue_id)
);

create table if not exists experiment_cases (
  case_id text primary key,
  session_id text not null,
  trace_id text not null,
  split text not null,
  created_at text not null,
  payload_json text not null,
  foreign key(session_id) references search_sessions(session_id)
);

create table if not exists experiment_candidates (
  candidate_id text primary key,
  session_id text not null,
  round_number integer not null,
  status text not null,
  created_at text not null,
  payload_json text not null,
  foreign key(session_id) references search_sessions(session_id)
);

create table if not exists candidate_evaluations (
  evaluation_id text primary key,
  session_id text not null,
  candidate_id text not null,
  split text not null,
  status text not null,
  created_at text not null,
  payload_json text not null,
  foreign key(session_id) references search_sessions(session_id),
  foreign key(candidate_id) references experiment_candidates(candidate_id)
);

create table if not exists pareto_snapshots (
  snapshot_id text primary key,
  session_id text not null,
  round_number integer not null,
  created_at text not null,
  payload_json text not null,
  foreign key(session_id) references search_sessions(session_id)
);

create table if not exists search_events (
  event_id text primary key,
  session_id text not null,
  candidate_id text,
  event_type text not null,
  created_at text not null,
  payload_json text not null,
  foreign key(session_id) references search_sessions(session_id)
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

    def upsert_hypothesis_finding(self, finding: dict[str, Any]) -> None:
        self.connection.execute(
            """
            insert into hypothesis_findings(
              finding_id, trace_id, finding_type, status, confidence, payload_json
            )
            values (?, ?, ?, ?, ?, ?)
            on conflict(finding_id) do update set
              trace_id=excluded.trace_id,
              finding_type=excluded.finding_type,
              status=excluded.status,
              confidence=excluded.confidence,
              payload_json=excluded.payload_json
            """,
            (
                finding["finding_id"],
                finding["trace_id"],
                finding["finding_type"],
                finding["status"],
                finding["confidence"],
                json.dumps(finding, sort_keys=True),
            ),
        )
        self.connection.commit()

    def delete_hypothesis_findings_for_traces(self, trace_ids: list[str]) -> None:
        if not trace_ids:
            return
        placeholders = ",".join("?" for _ in trace_ids)
        self.connection.execute(
            f"delete from hypothesis_findings where trace_id in ({placeholders})",
            trace_ids,
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

    def list_issue_events(self) -> list[dict[str, Any]]:
        rows = self.connection.execute(
            "select payload_json from issue_events order by created_at desc"
        ).fetchall()
        return [json.loads(row["payload_json"]) for row in rows]

    def list_issues(self) -> list[dict[str, Any]]:
        rows = self.connection.execute(
            "select payload_json from issues order by issue_id"
        ).fetchall()
        return [json.loads(row["payload_json"]) for row in rows]

    def list_traces(self, limit: int | None = None) -> list[dict[str, Any]]:
        query = "select payload_json from traces order by started_at desc"
        params: tuple[Any, ...] = ()
        if limit is not None:
            query += " limit ?"
            params = (limit,)
        rows = self.connection.execute(query, params).fetchall()
        return [json.loads(row["payload_json"]) for row in rows]

    def list_hypothesis_findings(self) -> list[dict[str, Any]]:
        rows = self.connection.execute(
            """
            select payload_json from hypothesis_findings
            order by confidence desc, finding_id
            """
        ).fetchall()
        return [json.loads(row["payload_json"]) for row in rows]

    def get_hypothesis_finding(self, finding_id: str) -> dict[str, Any] | None:
        row = self.connection.execute(
            "select payload_json from hypothesis_findings where finding_id = ?",
            (finding_id,),
        ).fetchone()
        return json.loads(row["payload_json"]) if row else None

    def get_issue(self, issue_id: str) -> dict[str, Any] | None:
        row = self.connection.execute(
            "select payload_json from issues where issue_id = ?",
            (issue_id,),
        ).fetchone()
        return json.loads(row["payload_json"]) if row else None

    def upsert_resolution_plan(self, plan: dict[str, Any]) -> None:
        self.connection.execute(
            """
            insert into resolution_plans(plan_id, issue_id, status, generated_at, payload_json)
            values (?, ?, ?, ?, ?)
            on conflict(plan_id) do update set
              issue_id=excluded.issue_id,
              status=excluded.status,
              generated_at=excluded.generated_at,
              payload_json=excluded.payload_json
            """,
            (
                plan["plan_id"],
                plan["issue_id"],
                plan["status"],
                plan["generated_at"],
                json.dumps(plan, sort_keys=True),
            ),
        )
        self.connection.commit()

    def get_resolution_plan_for_issue(self, issue_id: str) -> dict[str, Any] | None:
        row = self.connection.execute(
            """
            select payload_json from resolution_plans
            where issue_id = ?
            order by generated_at desc
            """,
            (issue_id,),
        ).fetchone()
        return json.loads(row["payload_json"]) if row else None

    def list_resolution_plans(self) -> list[dict[str, Any]]:
        rows = self.connection.execute(
            "select payload_json from resolution_plans order by generated_at desc"
        ).fetchall()
        return [json.loads(row["payload_json"]) for row in rows]

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

    def list_patch_bundles_for_issue(self, issue_id: str) -> list[dict[str, Any]]:
        rows = self.connection.execute(
            "select payload_json from patch_bundles where issue_id = ? order by patch_id",
            (issue_id,),
        ).fetchall()
        return [json.loads(row["payload_json"]) for row in rows]

    def get_patch_bundle(self, patch_id: str) -> dict[str, Any] | None:
        row = self.connection.execute(
            "select payload_json from patch_bundles where patch_id = ?",
            (patch_id,),
        ).fetchone()
        return json.loads(row["payload_json"]) if row else None

    def upsert_refinement_operation(self, operation: dict[str, Any]) -> None:
        self.connection.execute(
            """
            insert into refinement_operations(
              operation_id, operation_type, component_type, issue_id, patch_id,
              status, created_at, payload_json
            )
            values (?, ?, ?, ?, ?, ?, ?, ?)
            on conflict(operation_id) do update set
              operation_type=excluded.operation_type,
              component_type=excluded.component_type,
              issue_id=excluded.issue_id,
              patch_id=excluded.patch_id,
              status=excluded.status,
              created_at=excluded.created_at,
              payload_json=excluded.payload_json
            """,
            (
                operation["operation_id"],
                operation["operation_type"],
                operation["component_type"],
                operation["issue_id"],
                operation["patch_id"],
                operation["status"],
                operation["created_at"],
                json.dumps(operation, sort_keys=True),
            ),
        )
        self.connection.commit()

    def list_refinement_operations(self) -> list[dict[str, Any]]:
        rows = self.connection.execute(
            "select payload_json from refinement_operations order by created_at desc, operation_id"
        ).fetchall()
        return [json.loads(row["payload_json"]) for row in rows]

    def list_refinement_operations_for_patch(self, patch_id: str) -> list[dict[str, Any]]:
        rows = self.connection.execute(
            """
            select payload_json from refinement_operations
            where patch_id = ?
            order by operation_id
            """,
            (patch_id,),
        ).fetchall()
        return [json.loads(row["payload_json"]) for row in rows]

    def get_refinement_operation(self, operation_id: str) -> dict[str, Any] | None:
        row = self.connection.execute(
            "select payload_json from refinement_operations where operation_id = ?",
            (operation_id,),
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

    def list_gate_reports_for_issue(self, issue_id: str) -> list[dict[str, Any]]:
        rows = self.connection.execute(
            """
            select g.payload_json
            from gate_reports g
            join patch_bundles p on p.patch_id = g.patch_id
            where p.issue_id = ?
            order by g.gate_report_id
            """,
            (issue_id,),
        ).fetchall()
        return [json.loads(row["payload_json"]) for row in rows]

    def upsert_confirmation_report(self, report: dict[str, Any]) -> None:
        self.connection.execute(
            """
            insert into confirmation_reports(
              confirmation_id, patch_id, issue_id, status, outcome, payload_json
            )
            values (?, ?, ?, ?, ?, ?)
            on conflict(confirmation_id) do update set
              patch_id=excluded.patch_id,
              issue_id=excluded.issue_id,
              status=excluded.status,
              outcome=excluded.outcome,
              payload_json=excluded.payload_json
            """,
            (
                report["confirmation_id"],
                report["patch_id"],
                report["issue_id"],
                report["status"],
                report["outcome"],
                json.dumps(report, sort_keys=True),
            ),
        )
        self.connection.commit()

    def list_confirmation_reports(self) -> list[dict[str, Any]]:
        rows = self.connection.execute(
            "select payload_json from confirmation_reports order by confirmation_id"
        ).fetchall()
        return [json.loads(row["payload_json"]) for row in rows]

    def get_confirmation_report(self, confirmation_id: str) -> dict[str, Any] | None:
        row = self.connection.execute(
            "select payload_json from confirmation_reports where confirmation_id = ?",
            (confirmation_id,),
        ).fetchone()
        return json.loads(row["payload_json"]) if row else None

    def upsert_replay_report(self, report: dict[str, Any]) -> None:
        self.connection.execute(
            """
            insert into replay_reports(replay_id, patch_id, status, payload_json)
            values (?, ?, ?, ?)
            on conflict(replay_id) do update set
              patch_id=excluded.patch_id,
              status=excluded.status,
              payload_json=excluded.payload_json
            """,
            (
                report["replay_id"],
                report["patch_id"],
                report["status"],
                json.dumps(report, sort_keys=True),
            ),
        )
        self.connection.commit()

    def list_replay_reports(self) -> list[dict[str, Any]]:
        rows = self.connection.execute(
            "select payload_json from replay_reports order by replay_id"
        ).fetchall()
        return [json.loads(row["payload_json"]) for row in rows]

    def get_replay_report_for_patch(self, patch_id: str) -> dict[str, Any] | None:
        row = self.connection.execute(
            "select payload_json from replay_reports where patch_id = ? order by replay_id desc",
            (patch_id,),
        ).fetchone()
        return json.loads(row["payload_json"]) if row else None

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

    def upsert_harness_state(self, state: dict[str, Any]) -> None:
        self.connection.execute(
            """
            insert into harness_states(state_id, source, created_at, payload_json)
            values (?, ?, ?, ?)
            on conflict(state_id) do update set
              source=excluded.source,
              created_at=excluded.created_at,
              payload_json=excluded.payload_json
            """,
            (
                state["state_id"],
                state["source"],
                state["created_at"],
                json.dumps(state, sort_keys=True),
            ),
        )
        self.connection.commit()

    def list_harness_states(self) -> list[dict[str, Any]]:
        rows = self.connection.execute(
            "select payload_json from harness_states order by created_at desc"
        ).fetchall()
        return [json.loads(row["payload_json"]) for row in rows]

    def get_harness_state(self, state_id: str) -> dict[str, Any] | None:
        row = self.connection.execute(
            "select payload_json from harness_states where state_id = ?",
            (state_id,),
        ).fetchone()
        return json.loads(row["payload_json"]) if row else None

    def upsert_refiner_queue_item(self, item: dict[str, Any]) -> None:
        self.connection.execute(
            """
            insert into refiner_queue(
              queue_item_id, trigger, status, trace_window, target_scope,
              created_at, started_at, finished_at, payload_json
            )
            values (?, ?, ?, ?, ?, ?, ?, ?, ?)
            on conflict(queue_item_id) do update set
              trigger=excluded.trigger,
              status=excluded.status,
              trace_window=excluded.trace_window,
              target_scope=excluded.target_scope,
              created_at=excluded.created_at,
              started_at=excluded.started_at,
              finished_at=excluded.finished_at,
              payload_json=excluded.payload_json
            """,
            (
                item["queue_item_id"],
                item["trigger"],
                item["status"],
                item["trace_window"],
                item["target_scope"],
                item["created_at"],
                item.get("started_at"),
                item.get("finished_at"),
                json.dumps(item, sort_keys=True),
            ),
        )
        self.connection.commit()

    def list_refiner_queue_items(self) -> list[dict[str, Any]]:
        rows = self.connection.execute(
            "select payload_json from refiner_queue order by created_at desc"
        ).fetchall()
        return [json.loads(row["payload_json"]) for row in rows]

    def get_refiner_queue_item(self, queue_item_id: str) -> dict[str, Any] | None:
        row = self.connection.execute(
            "select payload_json from refiner_queue where queue_item_id = ?",
            (queue_item_id,),
        ).fetchone()
        return json.loads(row["payload_json"]) if row else None

    def get_next_refiner_queue_item(self) -> dict[str, Any] | None:
        row = self.connection.execute(
            """
            select payload_json from refiner_queue
            where status in ('queued', 'failed')
            order by created_at
            limit 1
            """
        ).fetchone()
        return json.loads(row["payload_json"]) if row else None

    def upsert_search_session(self, session: dict[str, Any]) -> None:
        self.connection.execute(
            """
            insert into search_sessions(
              session_id, issue_id, status, created_at, updated_at, payload_json
            ) values (?, ?, ?, ?, ?, ?)
            on conflict(session_id) do update set
              status=excluded.status,
              updated_at=excluded.updated_at,
              payload_json=excluded.payload_json
            """,
            (
                session["session_id"], session["issue_id"], session["status"],
                session["created_at"], session["updated_at"],
                json.dumps(session, sort_keys=True),
            ),
        )
        self.connection.commit()

    def get_search_session(self, session_id: str) -> dict[str, Any] | None:
        row = self.connection.execute(
            "select payload_json from search_sessions where session_id = ?", (session_id,)
        ).fetchone()
        return json.loads(row["payload_json"]) if row else None

    def list_search_sessions(self) -> list[dict[str, Any]]:
        return self._list_experiment_records("search_sessions", "created_at desc")

    def upsert_experiment_case(self, case: dict[str, Any]) -> None:
        self.connection.execute(
            """
            insert into experiment_cases(case_id, session_id, trace_id, split, created_at, payload_json)
            values (?, ?, ?, ?, ?, ?)
            on conflict(case_id) do update set payload_json=excluded.payload_json
            """,
            (
                case["case_id"], case["session_id"], case["trace_id"], case["split"],
                case["created_at"], json.dumps(case, sort_keys=True),
            ),
        )
        self.connection.commit()

    def list_experiment_cases(
        self, session_id: str, *, split: str | None = None
    ) -> list[dict[str, Any]]:
        query = "select payload_json from experiment_cases where session_id = ?"
        params: tuple[Any, ...] = (session_id,)
        if split is not None:
            query += " and split = ?"
            params = (session_id, split)
        query += " order by case_id"
        rows = self.connection.execute(query, params).fetchall()
        return [json.loads(row["payload_json"]) for row in rows]

    def upsert_experiment_candidate(self, candidate: dict[str, Any]) -> None:
        self.connection.execute(
            """
            insert into experiment_candidates(
              candidate_id, session_id, round_number, status, created_at, payload_json
            ) values (?, ?, ?, ?, ?, ?)
            on conflict(candidate_id) do update set
              status=excluded.status,
              payload_json=excluded.payload_json
            """,
            (
                candidate["candidate_id"], candidate["session_id"],
                candidate["round_number"], candidate["status"], candidate["created_at"],
                json.dumps(candidate, sort_keys=True),
            ),
        )
        self.connection.commit()

    def get_experiment_candidate(self, candidate_id: str) -> dict[str, Any] | None:
        row = self.connection.execute(
            "select payload_json from experiment_candidates where candidate_id = ?",
            (candidate_id,),
        ).fetchone()
        return json.loads(row["payload_json"]) if row else None

    def list_experiment_candidates(self, session_id: str) -> list[dict[str, Any]]:
        rows = self.connection.execute(
            """
            select payload_json from experiment_candidates
            where session_id = ? order by round_number, candidate_id
            """,
            (session_id,),
        ).fetchall()
        return [json.loads(row["payload_json"]) for row in rows]

    def list_all_experiment_candidates(self) -> list[dict[str, Any]]:
        rows = self.connection.execute(
            """
            select payload_json from experiment_candidates
            order by created_at, round_number, candidate_id
            """
        ).fetchall()
        return [json.loads(row["payload_json"]) for row in rows]

    def upsert_candidate_evaluation(self, evaluation: dict[str, Any]) -> None:
        self.connection.execute(
            """
            insert into candidate_evaluations(
              evaluation_id, session_id, candidate_id, split, status, created_at, payload_json
            ) values (?, ?, ?, ?, ?, ?, ?)
            on conflict(evaluation_id) do update set
              status=excluded.status,
              payload_json=excluded.payload_json
            """,
            (
                evaluation["evaluation_id"], evaluation["session_id"],
                evaluation["candidate_id"], evaluation["split"], evaluation["status"],
                evaluation["created_at"], json.dumps(evaluation, sort_keys=True),
            ),
        )
        self.connection.commit()

    def list_candidate_evaluations(
        self, session_id: str, *, candidate_id: str | None = None
    ) -> list[dict[str, Any]]:
        query = "select payload_json from candidate_evaluations where session_id = ?"
        params: tuple[Any, ...] = (session_id,)
        if candidate_id is not None:
            query += " and candidate_id = ?"
            params = (session_id, candidate_id)
        query += " order by created_at, evaluation_id"
        rows = self.connection.execute(query, params).fetchall()
        return [json.loads(row["payload_json"]) for row in rows]

    def list_all_candidate_evaluations(self) -> list[dict[str, Any]]:
        rows = self.connection.execute(
            "select payload_json from candidate_evaluations order by created_at, evaluation_id"
        ).fetchall()
        return [json.loads(row["payload_json"]) for row in rows]

    def upsert_pareto_snapshot(self, snapshot: dict[str, Any]) -> None:
        self.connection.execute(
            """
            insert into pareto_snapshots(
              snapshot_id, session_id, round_number, created_at, payload_json
            ) values (?, ?, ?, ?, ?)
            on conflict(snapshot_id) do update set payload_json=excluded.payload_json
            """,
            (
                snapshot["snapshot_id"], snapshot["session_id"], snapshot["round_number"],
                snapshot["created_at"], json.dumps(snapshot, sort_keys=True),
            ),
        )
        self.connection.commit()

    def list_pareto_snapshots(self, session_id: str) -> list[dict[str, Any]]:
        rows = self.connection.execute(
            """
            select payload_json from pareto_snapshots
            where session_id = ? order by round_number, created_at
            """,
            (session_id,),
        ).fetchall()
        return [json.loads(row["payload_json"]) for row in rows]

    def add_search_event(self, event: dict[str, Any]) -> None:
        self.connection.execute(
            """
            insert or ignore into search_events(
              event_id, session_id, candidate_id, event_type, created_at, payload_json
            ) values (?, ?, ?, ?, ?, ?)
            """,
            (
                event["event_id"], event["session_id"], event.get("candidate_id"),
                event["event_type"], event["created_at"],
                json.dumps(event, sort_keys=True),
            ),
        )
        self.connection.commit()

    def list_search_events(self, session_id: str) -> list[dict[str, Any]]:
        rows = self.connection.execute(
            """
            select payload_json from search_events
            where session_id = ? order by created_at, event_id
            """,
            (session_id,),
        ).fetchall()
        return [json.loads(row["payload_json"]) for row in rows]

    def _list_experiment_records(self, table: str, order: str) -> list[dict[str, Any]]:
        allowed = {"search_sessions"}
        if table not in allowed:
            raise ValueError(f"unsupported experiment table: {table}")
        rows = self.connection.execute(
            f"select payload_json from {table} order by {order}"
        ).fetchall()
        return [json.loads(row["payload_json"]) for row in rows]
