"""
Document Reference: server.py
System: Project Chronicle - Enterprise AI Workflow Manager
Branch: A.14.12
Description: Production FastAPI gateway providing Multi-Agent LangGraph orchestration,
             Kanban task management, 21 CFR Part 11 audit trails, and Excel exports.
"""

import uuid
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, Query, Response
from fastapi.middleware.cors import CORSMiddleware
from langchain_core.runnables import RunnableConfig
from pydantic import BaseModel, Field

from chronicle_db import chronicle_db
from chronicle_models import (
    AuditLogEntry,
    PortfolioSummary,
    Task,
    TaskCreate,
    TaskUpdate,
)
from circuit_breaker import chronicle_circuit_breaker
from excel_service import generate_portfolio_excel
from workflow import GraphStateSchema, WorkflowState
from workflow import app as workflow_app

server = FastAPI(
    title="Project Chronicle: Enterprise AI Workflow Manager API",
    version="1.14.12",
    docs_url="/api/docs",
)

# Strict CORS configuration
server.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
)


# ==========================================
# REQUEST SCHEMAS
# ==========================================
class ExecuteRequest(BaseModel):
    task: str = Field(..., min_length=3, max_length=1000)
    tenant_id: str = Field(...)
    thread_id: str = Field(...)


class ApprovalRequest(BaseModel):
    thread_id: str = Field(...)
    tenant_id: str = Field(...)
    approved: bool = Field(...)
    comments: str = Field(default="")


# ==========================================
# WORKFLOW ORCHESTRATION ROUTES
# ==========================================
@server.post("/api/workflow/execute")
async def execute_workflow(payload: ExecuteRequest) -> Dict[str, Any]:
    """Initiates the state graph execution, blocking at interrupt boundaries."""
    try:
        GraphStateSchema(
            task=payload.task,
            tenant_id=payload.tenant_id,
            category="",
            result="",
            approval_status="PENDING",
            reviewer_comments="",
        )

        config: RunnableConfig = {
            "configurable": {
                "thread_id": payload.thread_id,
                "tenant_id": payload.tenant_id,
            }
        }

        initial_state: WorkflowState = {
            "task": payload.task,
            "tenant_id": payload.tenant_id,
            "category": "",
            "result": "",
            "approval_status": "PENDING",
            "reviewer_comments": "",
        }

        events = workflow_app.stream(initial_state, config=config)
        output_state: Dict[str, Any] = dict(initial_state)
        for event in events:
            if "__interrupt__" in event:
                break
            output_state = dict(event)

        is_action = (
            "asana" in payload.task.lower() or "create task" in payload.task.lower()
        )
        return {
            "status": "PAUSED_FOR_REVIEW" if is_action else "SUCCESS",
            "state": output_state,
        }

    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve)) from ve
    except Exception:
        raise HTTPException(
            status_code=500, detail="An error occurred during workflow execution."
        ) from None


@server.post("/api/workflow/approve")
async def approve_workflow(payload: ApprovalRequest) -> Dict[str, Any]:
    """Resumes graph execution following human approval."""
    try:
        config: RunnableConfig = {
            "configurable": {
                "thread_id": payload.thread_id,
                "tenant_id": payload.tenant_id,
            }
        }

        current_state = workflow_app.get_state(config)
        if not current_state.values:
            raise HTTPException(status_code=404, detail="No active thread found.")

        approval_status = "APPROVED" if payload.approved else "REJECTED"

        workflow_app.update_state(
            config,
            {"approval_status": approval_status, "reviewer_comments": payload.comments},
            as_node="reviewer",
        )

        # Resume graph execution
        events = workflow_app.stream(None, config=config)
        final_state: Dict[str, Any] = {}
        for event in events:
            final_state = dict(event)

        return {"status": "COMPLETED", "state": final_state}

    except HTTPException:
        raise
    except Exception:
        raise HTTPException(
            status_code=500, detail="An error occurred during approval routing."
        ) from None


# ==========================================
# KANBAN & TASK MANAGEMENT ROUTES
# ==========================================
@server.get("/api/tasks", response_model=List[Task])
async def list_tasks(
    tenant_id: str = Query(..., description="UUID tenant identifier"),
    status: Optional[str] = Query(None, description="Filter by task status"),
    milestone: Optional[str] = Query(None, description="Filter by milestone"),
) -> List[Task]:
    """Lists tasks for a specific tenant, automatically seeding defaults if empty."""
    try:
        uuid.UUID(tenant_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=400, detail="Tenant ID must be a valid UUID string."
        ) from exc

    chronicle_db.seed_default_portfolio(tenant_id)
    return chronicle_db.list_tasks(tenant_id, status=status, milestone=milestone)


@server.post("/api/tasks", response_model=Task)
async def create_task(payload: TaskCreate) -> Task:
    """Creates a new managed task in the local Kanban/portfolio repository."""
    return chronicle_db.create_task(payload, actor="Dave Barbour (User)")


@server.patch("/api/tasks/{task_id}", response_model=Task)
async def update_task(
    task_id: str, payload: TaskUpdate, tenant_id: str = Query(...)
) -> Task:
    """Updates task properties, such as moving columns on the Kanban board."""
    updated = chronicle_db.update_task(task_id, tenant_id, payload)
    if not updated:
        raise HTTPException(status_code=404, detail="Task not found.")
    return updated


@server.delete("/api/tasks/{task_id}")
async def delete_task(task_id: str, tenant_id: str = Query(...)) -> Dict[str, bool]:
    """Deletes a task and logs the action in the GxP audit trail."""
    success = chronicle_db.delete_task(task_id, tenant_id)
    if not success:
        raise HTTPException(status_code=404, detail="Task not found.")
    return {"deleted": True}


@server.get("/api/portfolio/summary", response_model=PortfolioSummary)
async def get_portfolio_summary(tenant_id: str = Query(...)) -> PortfolioSummary:
    """Returns real-time executive KPI metrics across the task portfolio."""
    chronicle_db.seed_default_portfolio(tenant_id)
    return chronicle_db.get_portfolio_summary(tenant_id)


@server.get("/api/tasks/audit", response_model=List[AuditLogEntry])
async def get_audit_trail(
    tenant_id: str = Query(...), task_id: Optional[str] = Query(None)
) -> List[AuditLogEntry]:
    """Returns 21 CFR Part 11 compliant audit trail records."""
    return chronicle_db.get_audit_logs(tenant_id, task_id)


@server.get("/api/tasks/export/excel")
async def export_excel(tenant_id: str = Query(...)) -> Response:
    """Generates and streams an audited multi-tab Excel (.xlsx) report."""
    chronicle_db.seed_default_portfolio(tenant_id)
    excel_bytes = generate_portfolio_excel(tenant_id)
    filename = f"Project_Chronicle_Portfolio_{tenant_id[:8]}.xlsx"
    return Response(
        content=excel_bytes,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@server.get("/api/health")
async def health_check() -> Dict[str, Any]:
    """Returns system and circuit breaker health telemetry."""
    return {
        "status": "UP",
        "branch": "A.14.12",
        "circuit_breaker": chronicle_circuit_breaker.get_status(),
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(server, host="0.0.0.0", port=8000)  # noqa: S104
