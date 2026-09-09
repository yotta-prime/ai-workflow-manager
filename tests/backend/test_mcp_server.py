"""
Document Reference: tests/backend/test_mcp_server.py
System: Project Chronicle - Enterprise AI Workflow Manager
Branch: A.14.12
Description: Unit and protocol tests for mcp_server.py ensuring 21 CFR Part 11
             tool compliance and JSON-RPC 2.0 message adherence.
"""

import io
import json
import os
import sys
import tempfile
import uuid
from typing import Any, Dict, List

import pytest

from mcp_server import DEFAULT_TENANT, handle_tool_call, main


class TestMcpServerTools:
    """Tests for handle_tool_call across all 6 Chronicle tools."""

    def test_chronicle_list_tasks(self) -> None:
        tenant_id = str(uuid.uuid4())
        tasks = handle_tool_call("chronicle_list_tasks", {"tenant_id": tenant_id})
        assert isinstance(tasks, list)
        assert len(tasks) > 0

    def test_chronicle_list_tasks_filtered(self) -> None:
        tenant_id = str(uuid.uuid4())
        tasks = handle_tool_call(
            "chronicle_list_tasks", {"tenant_id": tenant_id, "status": "TODO"}
        )
        assert isinstance(tasks, list)
        for t in tasks:
            assert t["status"] == "TODO"

    def test_chronicle_create_task(self) -> None:
        tenant_id = str(uuid.uuid4())
        created = handle_tool_call(
            "chronicle_create_task",
            {
                "tenant_id": tenant_id,
                "title": "MCP Test Task",
                "description": "Created via MCP tool",
                "category": "ACTION",
                "priority": "HIGH",
            },
        )
        assert created["title"] == "MCP Test Task"
        assert created["status"] in ["IN_REVIEW", "TODO"]
        assert created["priority"] == "HIGH"

    def test_chronicle_update_task(self) -> None:
        tenant_id = str(uuid.uuid4())
        tasks = handle_tool_call("chronicle_list_tasks", {"tenant_id": tenant_id})
        task_id = tasks[0]["id"]

        updated = handle_tool_call(
            "chronicle_update_task",
            {
                "tenant_id": tenant_id,
                "task_id": task_id,
                "status": "DONE",
                "reviewer_comments": "Validated in test",
            },
        )
        assert updated["status"] == "DONE"
        assert updated["reviewer_comments"] == "Validated in test"

    def test_chronicle_update_task_not_found(self) -> None:
        with pytest.raises(ValueError, match="not found"):
            handle_tool_call(
                "chronicle_update_task",
                {
                    "tenant_id": str(uuid.uuid4()),
                    "task_id": str(uuid.uuid4()),
                    "status": "DONE",
                },
            )

    def test_chronicle_get_portfolio_summary(self) -> None:
        tenant_id = str(uuid.uuid4())
        summary = handle_tool_call(
            "chronicle_get_portfolio_summary", {"tenant_id": tenant_id}
        )
        assert "total_tasks" in summary
        assert "completion_rate_percent" in summary
        assert summary["total_tasks"] > 0

    def test_chronicle_export_excel_report(self) -> None:
        tenant_id = str(uuid.uuid4())
        with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as tmp:
            tmp_path = tmp.name
        try:
            res = handle_tool_call(
                "chronicle_export_excel_report",
                {"tenant_id": tenant_id, "output_path": tmp_path},
            )
            assert res["status"] == "SUCCESS"
            assert res["bytes_written"] > 0
            assert os.path.exists(tmp_path)
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    def test_chronicle_execute_workflow_research(self) -> None:
        tenant_id = str(uuid.uuid4())
        res = handle_tool_call(
            "chronicle_execute_workflow",
            {"task": "Analyze GAMP 5 requirements", "tenant_id": tenant_id},
        )
        assert res["status"] == "SUCCESS"
        assert "Analyze GAMP 5 requirements" in res["state"]["result"]

    def test_chronicle_execute_workflow_action(self) -> None:
        tenant_id = str(uuid.uuid4())
        res = handle_tool_call(
            "chronicle_execute_workflow",
            {"task": "Create task on Asana: IQ/OQ Plan", "tenant_id": tenant_id},
        )
        assert res["status"] == "PAUSED_FOR_REVIEW"

    def test_unknown_tool(self) -> None:
        with pytest.raises(ValueError, match="Unknown tool"):
            handle_tool_call("invalid_tool_name", {})


class TestMcpServerProtocol:
    """Tests for MCP JSON-RPC 2.0 stdio protocol."""

    def _run_mcp_lines(self, lines: List[str]) -> List[Dict[str, Any]]:
        input_data = "\n".join(lines) + "\n"
        old_stdin = sys.stdin
        old_stdout = sys.stdout
        sys.stdin = io.StringIO(input_data)
        out_buf = io.StringIO()
        sys.stdout = out_buf

        try:
            main()
        finally:
            sys.stdin = old_stdin
            sys.stdout = old_stdout

        output_str = out_buf.getvalue().strip()
        results: List[Dict[str, Any]] = []
        for line in output_str.split("\n"):
            line = line.strip()
            if line:
                results.append(json.loads(line))
        return results

    def test_initialize_and_notifications(self) -> None:
        reqs = [
            json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize"}),
            json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}),
            json.dumps({"jsonrpc": "2.0", "id": 2, "method": "ping"}),
        ]
        resps = self._run_mcp_lines(reqs)
        assert len(resps) == 2
        assert resps[0]["id"] == 1
        assert resps[0]["result"]["serverInfo"]["name"] == "ai-workflow-mcp-server"
        assert resps[1]["id"] == 2
        assert resps[1]["result"] == {}

    def test_tools_list(self) -> None:
        reqs = [
            json.dumps({"jsonrpc": "2.0", "id": 10, "method": "tools/list"}),
        ]
        resps = self._run_mcp_lines(reqs)
        assert len(resps) == 1
        tools = resps[0]["result"]["tools"]
        assert len(tools) == 6
        tool_names = [t["name"] for t in tools]
        assert "chronicle_list_tasks" in tool_names
        assert "chronicle_export_excel_report" in tool_names

    def test_tools_call_success(self) -> None:
        reqs = [
            json.dumps({
                "jsonrpc": "2.0",
                "id": 20,
                "method": "tools/call",
                "params": {
                    "name": "chronicle_get_portfolio_summary",
                    "arguments": {"tenant_id": DEFAULT_TENANT},
                },
            }),
        ]
        resps = self._run_mcp_lines(reqs)
        assert len(resps) == 1
        content = json.loads(resps[0]["result"]["content"][0]["text"])
        assert "total_tasks" in content

    def test_tools_call_error(self) -> None:
        reqs = [
            json.dumps({
                "jsonrpc": "2.0",
                "id": 30,
                "method": "tools/call",
                "params": {
                    "name": "non_existent_tool",
                    "arguments": {},
                },
            }),
        ]
        resps = self._run_mcp_lines(reqs)
        assert len(resps) == 1
        assert "error" in resps[0]
        assert resps[0]["error"]["code"] == -32603

    def test_method_not_found(self) -> None:
        reqs = [
            json.dumps({"jsonrpc": "2.0", "id": 40, "method": "unknown/method"}),
        ]
        resps = self._run_mcp_lines(reqs)
        assert len(resps) == 1
        assert resps[0]["error"]["code"] == -32601

    def test_parse_error(self) -> None:
        reqs = ["{ invalid json :::"]
        resps = self._run_mcp_lines(reqs)
        assert len(resps) == 1
        assert resps[0]["error"]["code"] == -32700
