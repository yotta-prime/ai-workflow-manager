"""
Document Reference: mcp_server.py
System: Project Chronicle - Enterprise AI Workflow Manager
Branch: A.14.12
Description: Stdio Model Context Protocol (MCP) server exposing Chronicle
             Task Management, Kanban, and LangGraph tools to Antigravity CLI (agy).
"""

import json
import sys
import uuid
from typing import Any, Dict, List

from langchain_core.runnables import RunnableConfig

from chronicle_db import chronicle_db
from chronicle_models import (
    TaskCategory,
    TaskCreate,
    TaskPriority,
    TaskStatus,
    TaskUpdate,
)
from excel_service import generate_portfolio_excel
from workflow import WorkflowState
from workflow import app as workflow_app

DEFAULT_TENANT = "00000000-0000-0000-0000-000000000000"

TOOLS: List[Dict[str, Any]] = [
    {
        "name": "chronicle_list_tasks",
        "description": (
            "List project tasks and schedule items from the Chronicle Kanban board."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "tenant_id": {
                    "type": "string",
                    "description": "UUID tenant identifier. Defaults to system tenant.",
                    "default": DEFAULT_TENANT,
                },
                "status": {
                    "type": "string",
                    "enum": ["TODO", "IN_REVIEW", "IN_PROGRESS", "DONE", "BLOCKED"],
                    "description": "Optional filter by task status",
                },
                "milestone": {
                    "type": "string",
                    "description": "Optional filter by project milestone",
                },
            },
        },
    },
    {
        "name": "chronicle_create_task",
        "description": "Create a new scheduled task in Project Chronicle.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "Title of the task"},
                "description": {
                    "type": "string",
                    "description": "Technical description and criteria",
                },
                "category": {
                    "type": "string",
                    "enum": ["ACTION", "RESEARCH", "SCHEDULE", "GOVERNANCE"],
                    "default": "ACTION",
                },
                "priority": {
                    "type": "string",
                    "enum": ["LOW", "MEDIUM", "HIGH", "CRITICAL"],
                    "default": "MEDIUM",
                },
                "milestone": {"type": "string", "default": "Sprint 1 - Foundation"},
                "assignee": {"type": "string", "default": "Dave Barbour"},
                "due_date": {"type": "string", "description": "YYYY-MM-DD due date"},
                "tenant_id": {"type": "string", "default": DEFAULT_TENANT},
            },
            "required": ["title"],
        },
    },
    {
        "name": "chronicle_update_task",
        "description": "Update task status or comments on the Kanban board.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "task_id": {"type": "string", "description": "UUID of the task"},
                "tenant_id": {"type": "string", "default": DEFAULT_TENANT},
                "status": {
                    "type": "string",
                    "enum": ["TODO", "IN_REVIEW", "IN_PROGRESS", "DONE", "BLOCKED"],
                },
                "priority": {
                    "type": "string",
                    "enum": ["LOW", "MEDIUM", "HIGH", "CRITICAL"],
                },
                "reviewer_comments": {"type": "string"},
            },
            "required": ["task_id"],
        },
    },
    {
        "name": "chronicle_get_portfolio_summary",
        "description": "Get executive KPI metrics (completion, approvals).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "tenant_id": {"type": "string", "default": DEFAULT_TENANT},
            },
        },
    },
    {
        "name": "chronicle_export_excel_report",
        "description": "Export 21 CFR Part 11 audited Excel workbook (.xlsx).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "output_path": {
                    "type": "string",
                    "description": "Destination file path for the .xlsx workbook",
                },
                "tenant_id": {"type": "string", "default": DEFAULT_TENANT},
            },
            "required": ["output_path"],
        },
    },
    {
        "name": "chronicle_execute_workflow",
        "description": "Dispatch a task request to the LangGraph multi-agent system.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "task": {
                    "type": "string",
                    "description": "Task instruction for the multi-agent graph",
                },
                "tenant_id": {"type": "string", "default": DEFAULT_TENANT},
                "thread_id": {
                    "type": "string",
                    "description": "Thread identifier for persistent checkpoints",
                },
            },
            "required": ["task"],
        },
    },
]


def handle_tool_call(name: str, arguments: Dict[str, Any]) -> Any:
    tenant_id = arguments.get("tenant_id", DEFAULT_TENANT)
    chronicle_db.seed_default_portfolio(tenant_id)

    if name == "chronicle_list_tasks":
        status = arguments.get("status")
        milestone = arguments.get("milestone")
        tasks = chronicle_db.list_tasks(tenant_id, status=status, milestone=milestone)
        return [t.model_dump() for t in tasks]

    elif name == "chronicle_create_task":
        task_in = TaskCreate(
            title=arguments["title"],
            description=arguments.get("description", ""),
            category=TaskCategory(arguments.get("category", "ACTION")),
            priority=TaskPriority(arguments.get("priority", "MEDIUM")),
            milestone=arguments.get("milestone", "Sprint 1 - Foundation"),
            assignee=arguments.get("assignee", "Dave Barbour"),
            due_date=arguments.get("due_date"),
            tenant_id=tenant_id,
        )
        task = chronicle_db.create_task(task_in, actor="Antigravity MCP Agent")
        return task.model_dump()

    elif name == "chronicle_update_task":
        task_id = arguments["task_id"]
        update_data: Dict[str, Any] = {}
        if "status" in arguments and arguments["status"]:
            update_data["status"] = TaskStatus(arguments["status"])
        if "priority" in arguments and arguments["priority"]:
            update_data["priority"] = TaskPriority(arguments["priority"])
        if "reviewer_comments" in arguments:
            update_data["reviewer_comments"] = arguments["reviewer_comments"]
        updates = TaskUpdate(**update_data)
        updated = chronicle_db.update_task(
            task_id, tenant_id, updates, actor="Antigravity MCP Agent"
        )
        if not updated:
            raise ValueError(f"Task {task_id} not found.")
        return updated.model_dump()

    elif name == "chronicle_get_portfolio_summary":
        summary = chronicle_db.get_portfolio_summary(tenant_id)
        return summary.model_dump()

    elif name == "chronicle_export_excel_report":
        out_path = arguments["output_path"]
        excel_bytes = generate_portfolio_excel(tenant_id)
        with open(out_path, "wb") as f:
            f.write(excel_bytes)
        return {
            "status": "SUCCESS",
            "bytes_written": len(excel_bytes),
            "file_path": out_path,
        }

    elif name == "chronicle_execute_workflow":
        task_desc = arguments["task"]
        thread_id = arguments.get("thread_id", str(uuid.uuid4()))
        config: RunnableConfig = {
            "configurable": {"thread_id": thread_id, "tenant_id": tenant_id}
        }
        initial_state: WorkflowState = {
            "task": task_desc,
            "tenant_id": tenant_id,
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
            for node_state in event.values():
                if isinstance(node_state, dict):
                    output_state.update(node_state)
        is_action = "asana" in task_desc.lower() or "create task" in task_desc.lower()
        return {
            "status": "PAUSED_FOR_REVIEW" if is_action else "SUCCESS",
            "thread_id": thread_id,
            "state": output_state,
        }

    else:
        raise ValueError(f"Unknown tool: {name}")


def main() -> None:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
            req_id = req.get("id")
            method = req.get("method")

            if method == "initialize":
                resp = {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "protocolVersion": "2024-11-05",
                        "capabilities": {"tools": {}},
                        "serverInfo": {
                            "name": "ai-workflow-mcp-server",
                            "version": "1.14.12",
                        },
                    },
                }
                sys.stdout.write(json.dumps(resp) + "\n")
                sys.stdout.flush()

            elif method == "notifications/initialized":
                pass  # Client acknowledgement

            elif method == "tools/list":
                resp = {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {"tools": TOOLS},
                }
                sys.stdout.write(json.dumps(resp) + "\n")
                sys.stdout.flush()

            elif method == "tools/call":
                params = req.get("params", {})
                name = params.get("name")
                args = params.get("arguments", {})
                try:
                    result = handle_tool_call(name, args)
                    resp = {
                        "jsonrpc": "2.0",
                        "id": req_id,
                        "result": {
                            "content": [
                                {
                                    "type": "text",
                                    "text": json.dumps(result, indent=2),
                                }
                            ]
                        },
                    }
                except Exception as exc:
                    resp = {
                        "jsonrpc": "2.0",
                        "id": req_id,
                        "error": {"code": -32603, "message": str(exc)},
                    }
                sys.stdout.write(json.dumps(resp) + "\n")
                sys.stdout.flush()

            elif method == "ping":
                resp = {"jsonrpc": "2.0", "id": req_id, "result": {}}
                sys.stdout.write(json.dumps(resp) + "\n")
                sys.stdout.flush()

            else:
                resp = {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "error": {"code": -32601, "message": f"Method not found: {method}"},
                }
                sys.stdout.write(json.dumps(resp) + "\n")
                sys.stdout.flush()

        except Exception as err:
            err_resp = {
                "jsonrpc": "2.0",
                "id": None,
                "error": {"code": -32700, "message": f"Parse error: {str(err)}"},
            }
            sys.stdout.write(json.dumps(err_resp) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    main()
