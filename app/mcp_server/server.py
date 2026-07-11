import time
from typing import Any
from app.database import (
    get_customer_by_name,
    get_open_issues,
    get_issue_history,
    get_next_actions,
    create_next_action
)
from app.metrics import log_mcp_call
from app.logger import get_logger

logger = get_logger(__name__)


class AcmeMCPServer:
    """
    Custom MCP (Model Context Protocol) Server for Acme Operations.
    
    MCP separates tool definitions from core agent logic.
    The agent calls this server to execute tools rather than
    calling database functions directly.
    
    This makes tools:
    - Reusable across different agents
    - Independently testable
    - Replaceable without changing agent code
    """

    def __init__(self):
        self.name = "acme-mcp-server"
        self.version = "1.0.0"
        self.tools = self._register_tools()
        logger.info(f"MCP Server initialised | tools={list(self.tools.keys())}")

    def _register_tools(self) -> dict:
        """Register all available tools with their schemas."""
        return {
            "get_customer_profile": {
                "description": "Get customer profile by name",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "customer_name": {
                            "type": "string",
                            "description": "The name of the customer to look up"
                        }
                    },
                    "required": ["customer_name"]
                }
            },
            "get_open_issues": {
                "description": "Get all open issues for a customer",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "customer_id": {
                            "type": "integer",
                            "description": "The customer ID"
                        }
                    },
                    "required": ["customer_id"]
                }
            },
            "get_issue_history": {
                "description": "Get history and updates for a specific issue",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "issue_id": {
                            "type": "integer",
                            "description": "The issue ID"
                        }
                    },
                    "required": ["issue_id"]
                }
            },
            "get_next_actions": {
                "description": "Get existing next actions for an issue",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "issue_id": {
                            "type": "integer",
                            "description": "The issue ID"
                        }
                    },
                    "required": ["issue_id"]
                }
            },
            "create_next_action": {
                "description": "Create a recommended next action for an issue. Admin only.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "issue_id": {
                            "type": "integer",
                            "description": "The issue ID"
                        },
                        "action_text": {
                            "type": "string",
                            "description": "The recommended action"
                        },
                        "assigned_to": {
                            "type": "string",
                            "description": "Who should perform the action"
                        },
                        "due_date": {
                            "type": "string",
                            "description": "Due date in YYYY-MM-DD format"
                        }
                    },
                    "required": ["issue_id", "action_text", "assigned_to", "due_date"]
                }
            }
        }

    def list_tools(self) -> dict:
        """Returns all available tools and their schemas."""
        return {
            "server": self.name,
            "version": self.version,
            "tools": self.tools
        }

    def call_tool(self, tool_name: str, arguments: dict) -> dict:
        """
        Execute a tool by name with given arguments.
        This is the core MCP pattern — standardised tool execution.
        """
        start = time.time()

        if tool_name not in self.tools:
            error = f"Unknown tool: {tool_name}"
            log_mcp_call(self.name, tool_name, 0, False, error)
            return {"error": error}

        try:
            logger.info(f"MCP tool call | tool={tool_name} | args={arguments}")
            result = self._execute_tool(tool_name, arguments)
            duration = (time.time() - start) * 1000
            log_mcp_call(self.name, tool_name, duration, True)
            return {
                "tool": tool_name,
                "result": result,
                "duration_ms": round(duration, 2)
            }

        except Exception as e:
            duration = (time.time() - start) * 1000
            log_mcp_call(self.name, tool_name, duration, False, str(e))
            logger.error(f"MCP tool error | tool={tool_name} | error={e}")
            return {"error": str(e)}

    def _execute_tool(self, tool_name: str, arguments: dict) -> Any:
        """Routes tool calls to the correct database function."""
        if tool_name == "get_customer_profile":
            customer = get_customer_by_name(arguments["customer_name"])
            if not customer:
                return {"error": f"Customer not found: {arguments['customer_name']}"}
            return {"customer": customer}

        elif tool_name == "get_open_issues":
            issues = get_open_issues(arguments["customer_id"])
            return {
                "issues": issues,
                "total_open": len(issues),
                "critical": sum(1 for i in issues if i["priority"] == "critical"),
                "high": sum(1 for i in issues if i["priority"] == "high")
            }

        elif tool_name == "get_issue_history":
            history = get_issue_history(arguments["issue_id"])
            return {
                "history": history,
                "total_updates": len(history)
            }

        elif tool_name == "get_next_actions":
            actions = get_next_actions(arguments["issue_id"])
            return {"next_actions": actions}

        elif tool_name == "create_next_action":
            success = create_next_action(
                arguments["issue_id"],
                arguments["action_text"],
                arguments["assigned_to"],
                arguments["due_date"]
            )
            return {
                "success": success,
                "message": "Next action created successfully"
            }

        else:
            raise ValueError(f"Tool not implemented: {tool_name}")


# Singleton instance
mcp_server = AcmeMCPServer()