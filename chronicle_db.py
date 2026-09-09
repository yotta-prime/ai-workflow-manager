"""
Document Reference: chronicle_db.py
System: Project Chronicle - Enterprise AI Workflow Manager
Branch: A.14.12
Description: SQLite storage engine with 21 CFR Part 11 compliant GxP audit trail.
"""

import json
import os
import sqlite3
import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from chronicle_models import (
    AuditLogEntry,
    PortfolioSummary,
    Task,
    TaskCategory,
    TaskCreate,
    TaskPriority,
    TaskStatus,
    TaskUpdate,
)

DEFAULT_DB_PATH = os.environ.get(
    "CHRONICLE_DB_PATH", os.path.join(os.path.dirname(__file__), "data", "chronicle.db")
)


class ChronicleDatabase:
    def __init__(self, db_path: str = DEFAULT_DB_PATH) -> None:
        self.db_path = db_path
        os.makedirs(os.path.dirname(os.path.abspath(self.db_path)), exist_ok=True)
        self.init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def init_db(self) -> None:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS tasks (
                    id TEXT PRIMARY KEY,
                    tenant_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    description TEXT,
                    category TEXT NOT NULL,
                    status TEXT NOT NULL,
                    priority TEXT NOT NULL,
                    milestone TEXT NOT NULL,
                    assignee TEXT NOT NULL,
                    due_date TEXT,
                    thread_id TEXT,
                    approval_status TEXT NOT NULL,
                    reviewer_comments TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS audit_logs (
                    id TEXT PRIMARY KEY,
                    task_id TEXT NOT NULL,
                    tenant_id TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    actor TEXT NOT NULL,
                    action TEXT NOT NULL,
                    previous_state TEXT,
                    new_state TEXT,
                    comments TEXT
                )
            """)
            conn.commit()

    def create_task(
        self,
        task_in: TaskCreate,
        actor: str = "System",
        thread_id: Optional[str] = None,
    ) -> Task:
        task_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        approval_status = (
            "PENDING" if task_in.category == TaskCategory.ACTION else "APPROVED"
        )
        initial_status = (
            TaskStatus.IN_REVIEW
            if task_in.category == TaskCategory.ACTION
            else TaskStatus.TODO
        )

        task = Task(
            id=task_id,
            tenant_id=task_in.tenant_id,
            title=task_in.title,
            description=task_in.description,
            category=task_in.category,
            status=initial_status,
            priority=task_in.priority,
            milestone=task_in.milestone,
            assignee=task_in.assignee,
            due_date=task_in.due_date,
            thread_id=thread_id,
            approval_status=approval_status,
            reviewer_comments="",
            created_at=now,
            updated_at=now,
        )

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO tasks (
                    id, tenant_id, title, description, category, status, priority,
                    milestone, assignee, due_date, thread_id, approval_status,
                    reviewer_comments, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    task.id,
                    task.tenant_id,
                    task.title,
                    task.description,
                    task.category.value,
                    task.status.value,
                    task.priority.value,
                    task.milestone,
                    task.assignee,
                    task.due_date,
                    task.thread_id,
                    task.approval_status,
                    task.reviewer_comments,
                    task.created_at,
                    task.updated_at,
                ),
            )

            audit_id = str(uuid.uuid4())
            cursor.execute(
                """
                INSERT INTO audit_logs (
                    id, task_id, tenant_id, timestamp, actor, action,
                    previous_state, new_state, comments
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    audit_id,
                    task.id,
                    task.tenant_id,
                    now,
                    actor,
                    "CREATE",
                    None,
                    json.dumps(task.model_dump()),
                    "Task created",
                ),
            )
            conn.commit()

        return task

    def get_task(self, task_id: str, tenant_id: str) -> Optional[Task]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM tasks WHERE id = ? AND tenant_id = ?",
                (task_id, tenant_id),
            )
            row = cursor.fetchone()
            if not row:
                return None
            return self._row_to_task(row)

    def list_tasks(
        self,
        tenant_id: str,
        status: Optional[str] = None,
        milestone: Optional[str] = None,
    ) -> List[Task]:
        query = "SELECT * FROM tasks WHERE tenant_id = ?"
        params: List[Any] = [tenant_id]

        if status:
            query += " AND status = ?"
            params.append(status)
        if milestone:
            query += " AND milestone = ?"
            params.append(milestone)

        query += " ORDER BY created_at DESC"

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            rows = cursor.fetchall()
            return [self._row_to_task(r) for r in rows]

    def update_task(
        self,
        task_id: str,
        tenant_id: str,
        updates: TaskUpdate,
        actor: str = "Dave Barbour (Supervisor)",
    ) -> Optional[Task]:
        current = self.get_task(task_id, tenant_id)
        if not current:
            return None

        update_dict = updates.model_dump(exclude_unset=True)
        if not update_dict:
            return current

        now = datetime.now(timezone.utc).isoformat()
        clauses = ["updated_at = ?"]
        params: List[Any] = [now]

        for k, v in update_dict.items():
            clauses.append(f"{k} = ?")
            params.append(v.value if isinstance(v, Enum) else v)

        params.extend([task_id, tenant_id])

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                f"UPDATE tasks SET {', '.join(clauses)} WHERE id = ? AND tenant_id = ?",  # noqa: S608
                params,
            )

            audit_id = str(uuid.uuid4())
            cursor.execute(
                """
                INSERT INTO audit_logs (
                    id, task_id, tenant_id, timestamp, actor, action,
                    previous_state, new_state, comments
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    audit_id,
                    task_id,
                    tenant_id,
                    now,
                    actor,
                    "UPDATE",
                    json.dumps(current.model_dump()),
                    json.dumps(update_dict),
                    updates.reviewer_comments or "Task updated",
                ),
            )
            conn.commit()

        return self.get_task(task_id, tenant_id)

    def delete_task(
        self, task_id: str, tenant_id: str, actor: str = "Dave Barbour"
    ) -> bool:
        current = self.get_task(task_id, tenant_id)
        if not current:
            return False

        now = datetime.now(timezone.utc).isoformat()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "DELETE FROM tasks WHERE id = ? AND tenant_id = ?", (task_id, tenant_id)
            )

            audit_id = str(uuid.uuid4())
            cursor.execute(
                """
                INSERT INTO audit_logs (
                    id, task_id, tenant_id, timestamp, actor, action,
                    previous_state, new_state, comments
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    audit_id,
                    task_id,
                    tenant_id,
                    now,
                    actor,
                    "DELETE",
                    json.dumps(current.model_dump()),
                    None,
                    "Task deleted",
                ),
            )
            conn.commit()
        return True

    def get_audit_logs(
        self, tenant_id: str, task_id: Optional[str] = None
    ) -> List[AuditLogEntry]:
        query = "SELECT * FROM audit_logs WHERE tenant_id = ?"
        params: List[Any] = [tenant_id]
        if task_id:
            query += " AND task_id = ?"
            params.append(task_id)
        query += " ORDER BY timestamp DESC"

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            rows = cursor.fetchall()
            return [
                AuditLogEntry(
                    id=r["id"],
                    task_id=r["task_id"],
                    tenant_id=r["tenant_id"],
                    timestamp=r["timestamp"],
                    actor=r["actor"],
                    action=r["action"],
                    previous_state=r["previous_state"],
                    new_state=r["new_state"],
                    comments=r["comments"],
                )
                for r in rows
            ]

    def get_portfolio_summary(self, tenant_id: str) -> PortfolioSummary:
        tasks = self.list_tasks(tenant_id)
        total = len(tasks)
        by_status: Dict[str, int] = {s.value: 0 for s in TaskStatus}
        by_priority: Dict[str, int] = {p.value: 0 for p in TaskPriority}
        by_category: Dict[str, int] = {c.value: 0 for c in TaskCategory}
        milestones_set = set()
        pending_approvals = 0

        for t in tasks:
            by_status[t.status.value] = by_status.get(t.status.value, 0) + 1
            by_priority[t.priority.value] = by_priority.get(t.priority.value, 0) + 1
            by_category[t.category.value] = by_category.get(t.category.value, 0) + 1
            milestones_set.add(t.milestone)
            if t.approval_status == "PENDING" or t.status == TaskStatus.IN_REVIEW:
                pending_approvals += 1

        done_count = by_status.get(TaskStatus.DONE.value, 0)
        completion_rate = round((done_count / total * 100.0), 1) if total > 0 else 0.0

        return PortfolioSummary(
            total_tasks=total,
            by_status=by_status,
            by_priority=by_priority,
            by_category=by_category,
            completion_rate_percent=completion_rate,
            pending_approvals=pending_approvals,
            milestones=sorted(list(milestones_set)),
        )

    def seed_default_portfolio(self, tenant_id: str) -> None:
        existing = self.list_tasks(tenant_id)
        if existing:
            return

        seeds = [
            TaskCreate(
                title="Author CSA Computer Software Assurance Plan",
                description=(
                    "Formulate GAMP 5 Category 5 validation strategy under FDA CSA."
                ),
                category=TaskCategory.GOVERNANCE,
                priority=TaskPriority.CRITICAL,
                milestone="Sprint 1 - Foundation",
                assignee="Dave Barbour",
                due_date="2026-09-15",
                tenant_id=tenant_id,
            ),
            TaskCreate(
                title="Conduct FMEA Threat Model & RPN Scoring",
                description=(
                    "Evaluate risks RM-001 through RM-010 for prompt injection and "
                    "circuit breakers."
                ),
                category=TaskCategory.RESEARCH,
                priority=TaskPriority.HIGH,
                milestone="Sprint 1 - Foundation",
                assignee="Dave Barbour",
                due_date="2026-09-18",
                tenant_id=tenant_id,
            ),
            TaskCreate(
                title="Configure Asana Mock Task Service & Circuit Breaker",
                description=(
                    "Establish isolated task orchestration engine with offline-first "
                    "SQLite fallback."
                ),
                category=TaskCategory.ACTION,
                priority=TaskPriority.HIGH,
                milestone="Sprint 1 - Foundation",
                assignee="Dave Barbour",
                due_date="2026-09-20",
                tenant_id=tenant_id,
            ),
            TaskCreate(
                title="Execute 21 CFR Part 11 Audit Trail Verification",
                description=(
                    "Verify immutable append-only state tracking for supervisory "
                    "electronic signatures."
                ),
                category=TaskCategory.SCHEDULE,
                priority=TaskPriority.MEDIUM,
                milestone="Sprint 2 - Verification",
                assignee="Dave Barbour",
                due_date="2026-09-25",
                tenant_id=tenant_id,
            ),
        ]

        for s in seeds:
            task = self.create_task(s, actor="System Seeder")
            # Set first task as IN_PROGRESS, second as DONE
            if "CSA" in task.title:
                self.update_task(
                    task.id,
                    tenant_id,
                    TaskUpdate(status=TaskStatus.IN_PROGRESS),
                    actor="System Seeder",
                )
            elif "FMEA" in task.title:
                self.update_task(
                    task.id,
                    tenant_id,
                    TaskUpdate(status=TaskStatus.DONE),
                    actor="System Seeder",
                )

    def _row_to_task(self, row: sqlite3.Row) -> Task:
        return Task(
            id=row["id"],
            tenant_id=row["tenant_id"],
            title=row["title"],
            description=row["description"] or "",
            category=TaskCategory(row["category"]),
            status=TaskStatus(row["status"]),
            priority=TaskPriority(row["priority"]),
            milestone=row["milestone"],
            assignee=row["assignee"],
            due_date=row["due_date"],
            thread_id=row["thread_id"],
            approval_status=row["approval_status"],
            reviewer_comments=row["reviewer_comments"] or "",
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )


chronicle_db = ChronicleDatabase()
