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
