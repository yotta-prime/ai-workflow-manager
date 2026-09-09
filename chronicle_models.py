"""
Document Reference: chronicle_models.py
System: Project Chronicle - Enterprise AI Workflow Manager
Branch: A.14.12
Description: Data contracts and Pydantic schemas for Tasks, Portfolio, and Audit Trails.
"""

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, List, Optional

from pydantic import BaseModel, Field, field_validator


class TaskStatus(str, Enum):
    TODO = "TODO"
    IN_REVIEW = "IN_REVIEW"
    IN_PROGRESS = "IN_PROGRESS"
    DONE = "DONE"
    BLOCKED = "BLOCKED"


class TaskPriority(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class TaskCategory(str, Enum):
    ACTION = "ACTION"
    RESEARCH = "RESEARCH"
    SCHEDULE = "SCHEDULE"
    GOVERNANCE = "GOVERNANCE"


class TaskCreate(BaseModel):
    title: str = Field(..., min_length=3, max_length=200)
    description: str = Field(default="", max_length=2000)
    category: TaskCategory = Field(default=TaskCategory.ACTION)
    priority: TaskPriority = Field(default=TaskPriority.MEDIUM)
    milestone: str = Field(default="Sprint 1 - Foundation")
    assignee: str = Field(default="Dave Barbour")
    due_date: Optional[str] = Field(default=None)
    tenant_id: str = Field(...)

    @field_validator("tenant_id")
    @classmethod
    def validate_uuid(cls, value: str) -> str:
        try:
            uuid.UUID(value)
        except ValueError as exc:
            raise ValueError("Tenant ID must be a valid UUID string.") from exc
        return value


class TaskUpdate(BaseModel):
    title: Optional[str] = Field(default=None, min_length=3, max_length=200)
    description: Optional[str] = Field(default=None, max_length=2000)
    status: Optional[TaskStatus] = None
    priority: Optional[TaskPriority] = None
    category: Optional[TaskCategory] = None
    assignee: Optional[str] = None
    milestone: Optional[str] = None
    due_date: Optional[str] = None
    reviewer_comments: Optional[str] = None
    approval_status: Optional[str] = None


class Task(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    title: str
    description: str = ""
    category: TaskCategory = TaskCategory.ACTION
    status: TaskStatus = TaskStatus.TODO
    priority: TaskPriority = TaskPriority.MEDIUM
    milestone: str = "Sprint 1 - Foundation"
    assignee: str = "Dave Barbour"
    due_date: Optional[str] = None
    thread_id: Optional[str] = None
    approval_status: str = "PENDING"
    reviewer_comments: str = ""
    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    updated_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


class AuditLogEntry(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    task_id: str
    tenant_id: str
    timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    actor: str = "Dave Barbour (TPM)"
    action: str
    previous_state: Optional[str] = None
    new_state: Optional[str] = None
    comments: str = ""


class PortfolioSummary(BaseModel):
    total_tasks: int
    by_status: Dict[str, int]
    by_priority: Dict[str, int]
    by_category: Dict[str, int]
    completion_rate_percent: float
    pending_approvals: int
    milestones: List[str]
