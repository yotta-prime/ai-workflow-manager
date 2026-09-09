# Antigravity CLI (agy) Project Directives

This project implements an intelligent multi-agent graph registered as a local Model Context Protocol (MCP) server.

## Execution Rules
- All manual operational tasks that write to external systems must be halted in an active review state until supervisor credentials sign off.
- Execute unit validations via `agy` using:
  ```bash
  agy run pytest tests/backend/
  ```
- Local CLI-based state routing should register endpoints within the local .agents/mcp_config.json matrix.
