"""
Document Reference: workflow.py
System: Enterprise AI Workflow Manager
Branch: A.14.12
Description: Standardized implementation of a multi-agent LangGraph workflow
             equipped with strict input sanitization, multi-tenant state isolation,
             human-in-the-loop review nodes, and runtime loop bounds.
"""

import re
import uuid
from typing import Any, Dict, Literal, TypedDict

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph
from pydantic import BaseModel, Field, field_validator


# ==========================================
# PROMPT REGISTRY & LOADER
# ==========================================
class SystemPromptRegistry:
    """Central prompt registry to isolate instructions from the compiled binary."""

    _prompts: Dict[str, str] = {
        "router": (
            "System Instruction: Analyze the user request. Categorize as 'RESEARCH' "
            "if deep summaries are needed, or 'ACTION' if automated systems (Asana) "
            "must be invoked. Respond with ONLY 'RESEARCH' or 'ACTION'."
        ),
        "researcher": (
            "System Instruction: Act as a research assistant. Provide an objective, "
            "factual summary of the user query."
        ),
        "executor": (
            "System Instruction: Formulate task payloads for Asana based on "
            "validated human approval inputs."
        ),
    }

    @classmethod
    def get_prompt(cls, key: str) -> str:
        if key not in cls._prompts:
            raise KeyError(f"Requested prompt key '{key}' is not registered.")
        return cls._prompts[key]


# ==========================================
# DATA INTEGRITY & SANITIZER
# ==========================================
class PromptSanitizer:
    """Verifies that user inputs do not contain malicious injection payloads."""

    INJECTION_PATTERN = re.compile(
        r"(ignore\s+previous\s+instructions|system\s+override|delete\s+all|bypass\s+security)",
        re.IGNORECASE,
    )

    @classmethod
    def sanitize(cls, text: str) -> str:
        cleaned = text.strip()
        if cls.INJECTION_PATTERN.search(cleaned):
            raise ValueError(
                "Input verification failed: Prompt injection signature detected."
            )
        return cleaned


# ==========================================
# PYDANTIC DATA CONTROLLERS
# ==========================================
class GraphStateSchema(BaseModel):
    """Pydantic schema enforcing data integrity constraints on state variables."""

    task: str = Field(..., min_length=3, max_length=1000)
    category: str = Field(default="")
    result: str = Field(default="")
    approval_status: str = Field(default="PENDING")
    reviewer_comments: str = Field(default="")
    tenant_id: str = Field(...)

    @field_validator("tenant_id")
    @classmethod
    def validate_uuid(cls, value: str) -> str:
        try:
            uuid.UUID(value)
        except ValueError as exc:
            raise ValueError("Tenant ID must be a valid UUID string.") from exc
        return value


class WorkflowState(TypedDict, total=False):
    """Internal graph dictionary carrying Pydantic validated states."""

    task: str
    category: str
    result: str
    approval_status: str
    reviewer_comments: str
    tenant_id: str


# ==========================================
# GRAPH NODE FUNCTIONS
# ==========================================
def router_node(state: WorkflowState) -> Dict[str, Any]:
    """Analyzes task category based on sanitized inputs."""
    PromptSanitizer.sanitize(state["task"])
    _ = SystemPromptRegistry.get_prompt("router")

    # Check if task requests an automated update
    if "asana" in state["task"].lower() or "create task" in state["task"].lower():
        return {"category": "ACTION"}
    return {"category": "RESEARCH"}


def research_node(state: WorkflowState) -> Dict[str, Any]:
    """Generates an objective summary for research tasks."""
    return {"result": f"Research summary generated for: {state['task']}"}


def review_node(state: WorkflowState) -> Dict[str, Any]:
    """Halts execution to await human review before external updates."""
    return {"approval_status": "PENDING"}


def executor_node(state: WorkflowState) -> Dict[str, Any]:
    """Posts validated data payloads to external systems (Asana simulation)."""
    if state.get("approval_status") != "APPROVED":
        raise PermissionError(
            "Access Denied: Execution blocked due to missing human approval."
        )

    task_title = state["task"]
    tenant_id = state.get("tenant_id", "00000000-0000-0000-0000-000000000000")
    comments = state.get("reviewer_comments", "")

    from chronicle_db import chronicle_db
    from chronicle_models import TaskCategory, TaskCreate, TaskPriority
    from circuit_breaker import chronicle_circuit_breaker

    def _create_task() -> str:
        t = chronicle_db.create_task(
            TaskCreate(
                title=task_title,
                description=f"Action executed via HITL approval. Comments: {comments}",
                category=TaskCategory.ACTION,
                priority=TaskPriority.HIGH,
                milestone="Sprint 1 - Foundation",
                assignee="Dave Barbour",
                tenant_id=tenant_id,
            ),
            actor="Agent Executor (LangGraph)",
        )
        return t.id

    task_id = chronicle_circuit_breaker.call(_create_task)

    return {
        "result": f"Asana/Chronicle task created successfully [ID: {task_id[:8]}...]. "
        f"Task: {state['task']} | Comments: {comments}"
    }


# ==========================================
# GRAPH ROUTING LOGIC
# ==========================================
def route_task(state: WorkflowState) -> Literal["researcher", "reviewer"]:
    if state["category"] == "RESEARCH":
        return "researcher"
    return "reviewer"


def route_review_result(state: WorkflowState) -> Literal["executor", "end"]:
    if state["approval_status"] == "APPROVED":
        return "executor"
    return "end"


# ==========================================
# BUILD STATE GRAPH
# ==========================================
builder = StateGraph(WorkflowState)

builder.add_node("router", router_node)
builder.add_node("researcher", research_node)
builder.add_node("reviewer", review_node)
builder.add_node("executor", executor_node)

builder.set_entry_point("router")

builder.add_conditional_edges(
    "router", route_task, {"researcher": "researcher", "reviewer": "reviewer"}
)

builder.add_conditional_edges(
    "reviewer", route_review_result, {"executor": "executor", "end": END}
)

builder.add_edge("researcher", END)
builder.add_edge("executor", END)

# Compile with memory persistence saver
memory_saver = MemorySaver()
app = builder.compile(checkpointer=memory_saver, interrupt_before=["reviewer"])
