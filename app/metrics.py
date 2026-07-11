import json
import os
from datetime import datetime
from app.logger import get_logger

logger = get_logger(__name__)
    
metrics_store = {
    "api_requests": [],
    "agent_calls": [],
    "tool_calls": [],
    "mcp_calls": [],
    "llm_calls": [],
    "errors": [],
    "security_events": [],
    "auth_events": [],
    "database_events": []
}

def log_api_request(
    endpoint: str,
    method: str,
    status_code: int,
    duration_ms: float,
    user_role: str = "unknown"
):
    entry = {
        "timestamp": datetime.now().isoformat(),
        "type": "api_request",
        "endpoint": endpoint,
        "method": method,
        "status_code": status_code,
        "duration_ms": round(duration_ms, 2),
        "user_role": user_role,
        "success": status_code < 400
    }
    metrics_store["api_requests"].append(entry)
    logger.info(f"API | {method} {endpoint} | {status_code} | {duration_ms:.2f}ms | role={user_role}")
    _save_metrics()

def log_llm_call(
    model: str,
    prompt_tokens: int,
    response_tokens: int,
    duration_ms: float,
    success: bool,
    error: str | None = None
):
    entry = {
        "timestamp": datetime.now().isoformat(),
        "type": "llm_call",
        "model": model,
        "prompt_tokens": prompt_tokens,
        "response_tokens": response_tokens,
        "total_tokens": prompt_tokens + response_tokens,
        "duration_ms": round(duration_ms, 2),
        "success": success,
        "error": error
    }
    metrics_store["llm_calls"].append(entry)
    logger.info(f"LLM | {model} | tokens={prompt_tokens+response_tokens} | {duration_ms:.2f}ms | success={success}")
    _save_metrics()

def log_tool_call(
    tool_name: str,
    input_data: dict,
    duration_ms: float,
    success: bool,
    error: str | None = None
):
    entry = {
        "timestamp": datetime.now().isoformat(),
        "type": "tool_call",
        "tool_name": tool_name,
        "duration_ms": round(duration_ms, 2),
        "success": success,
        "error": error
    }
    metrics_store["tool_calls"].append(entry)
    logger.info(f"TOOL | {tool_name} | {duration_ms:.2f}ms | success={success}")
    _save_metrics()

def log_mcp_call(
    server: str,
    tool: str,
    duration_ms: float,
    success: bool,
    error: str | None = None
):
    entry = {
        "timestamp": datetime.now().isoformat(),
        "type": "mcp_call",
        "server": server,
        "tool": tool,
        "duration_ms": round(duration_ms, 2),
        "success": success,
        "error": error
    }
    metrics_store["mcp_calls"].append(entry)
    logger.info(f"MCP | {server}.{tool} | {duration_ms:.2f}ms | success={success}")
    _save_metrics()

def log_error(
    source: str,
    error_type: str,
    message: str,
    user_role: str = "unknown"
):
    entry = {
        "timestamp": datetime.now().isoformat(),
        "type": "error",
        "source": source,
        "error_type": error_type,
        "message": message,
        "user_role": user_role
    }
    metrics_store["errors"].append(entry)
    logger.error(f"ERROR | {source} | {error_type} | {message}")
    _save_metrics()

def get_metrics_summary() -> dict:
    api_requests = metrics_store["api_requests"]
    llm_calls = metrics_store["llm_calls"]
    tool_calls = metrics_store["tool_calls"]
    mcp_calls = metrics_store["mcp_calls"]
    errors = metrics_store["errors"]

    return {
        "generated_at": datetime.now().isoformat(),
        "summary": {
            "total_api_requests": len(api_requests),
            "successful_api_requests": sum(1 for r in api_requests if r["success"]),
            "failed_api_requests": sum(1 for r in api_requests if not r["success"]),
            "avg_api_latency_ms": round(
                sum(r["duration_ms"] for r in api_requests) / len(api_requests), 2
            ) if api_requests else 0,
            "total_llm_calls": len(llm_calls),
            "successful_llm_calls": sum(1 for r in llm_calls if r["success"]),
            "total_tokens_used": sum(r["total_tokens"] for r in llm_calls),
            "avg_llm_latency_ms": round(
                sum(r["duration_ms"] for r in llm_calls) / len(llm_calls), 2
            ) if llm_calls else 0,
            "total_tool_calls": len(tool_calls),
            "successful_tool_calls": sum(1 for r in tool_calls if r["success"]),
            "total_mcp_calls": len(mcp_calls),
            "successful_mcp_calls": sum(1 for r in mcp_calls if r["success"]),
            "total_errors": len(errors),
        },
        "tool_call_breakdown": _breakdown_by_field(tool_calls, "tool_name"),
        "api_endpoint_breakdown": _breakdown_by_field(api_requests, "endpoint"),
        "error_breakdown": _breakdown_by_field(errors, "error_type"),
        "raw": {
            "api_requests": api_requests[-50:],
            "llm_calls": llm_calls[-50:],
            "tool_calls": tool_calls[-50:],
            "mcp_calls": mcp_calls[-50:],
            "errors": errors[-50:],
            "security_events": metrics_store["security_events"][-50:],
            "database_events": metrics_store["database_events"][-50:]  
        },
        "total_agent_calls": len(metrics_store["agent_calls"]),
        "successful_agent_calls": sum(1 for r in metrics_store["agent_calls"] if r.get("success")),
        "total_auth_events": len(metrics_store["security_events"]),
        "total_database_events": len(metrics_store["database_events"]),
    }

def _breakdown_by_field(items: list, field: str) -> dict:
    breakdown = {}
    for item in items:
        value = item.get(field, "unknown")
        breakdown[value] = breakdown.get(value, 0) + 1
    return breakdown

def _save_metrics():
    os.makedirs("logs", exist_ok=True)
    with open("logs/metrics.json", "w") as f:
        json.dump(get_metrics_summary(), f, indent=2)

def log_security_event(
    event_type: str,
    approval_id: str,
    sensitive_data_types: list,
    requested_by: str,
    outcome: str,
    approved_by: str | None = None
):
    """Log security events for Power BI monitoring."""
    entry = {
        "timestamp": datetime.now().isoformat(),
        "type": "security_event",
        "event_type": event_type,
        "approval_id": approval_id,
        "sensitive_data_types": sensitive_data_types,
        "requested_by": requested_by,
        "outcome": outcome,
        "approved_by": approved_by
    }
    metrics_store["security_events"].append(entry)
    logger.warning(
        f"SECURITY | {event_type} | approval_id={approval_id} | "
        f"types={sensitive_data_types} | requested_by={requested_by} | "
        f"outcome={outcome} | approved_by={approved_by}"
    )
    _save_metrics()

def log_agent_event(
    event_type: str,
    username: str,
    user_role: str,
    query_preview: str,
    duration_ms: float,
    success: bool,
    tools_called: list | None = None,
    error: str | None = None
):
    """Log agent start, end, and outcome for Power BI monitoring."""
    entry = {
        "timestamp": datetime.now().isoformat(),
        "type": "agent_event",
        "event_type": event_type,
        "username": username,
        "user_role": user_role,
        "query_preview": query_preview[:100],
        "duration_ms": round(duration_ms, 2),
        "success": success,
        "tools_called": tools_called or [],
        "error": error
    }
    metrics_store["agent_calls"].append(entry)
    logger.info(
        f"AGENT | {event_type} | user={username} | "
        f"role={user_role} | duration={duration_ms:.2f}ms | "
        f"success={success} | tools={tools_called}"
    )
    _save_metrics()


def log_auth_event(
    event_type: str,
    username: str,
    user_role: str,
    success: bool,
    error: str | None = None
):
    """Log authentication and authorisation events for Power BI."""
    entry = {
        "timestamp": datetime.now().isoformat(),
        "type": "auth_event",
        "event_type": event_type,
        "username": username,
        "user_role": user_role,
        "success": success,
        "error": error
    }
    metrics_store["security_events"].append(entry)
    logger.info(
        f"AUTH | {event_type} | user={username} | "
        f"role={user_role} | success={success}"
    )
    _save_metrics()


def log_database_event(
    operation: str,
    table: str,
    duration_ms: float,
    rows_returned: int,
    success: bool,
    error: str | None = None
):
    """Log database operations for Power BI monitoring."""
    entry = {
        "timestamp": datetime.now().isoformat(),
        "type": "database_event",
        "operation": operation,
        "table": table,
        "duration_ms": round(duration_ms, 2),
        "rows_returned": rows_returned,
        "success": success,
        "error": error
    }
    metrics_store["database_events"].append(entry)
    logger.info(
        f"DB | {operation} | table={table} | "
        f"rows={rows_returned} | duration={duration_ms:.2f}ms | "
        f"success={success}"
    )
    _save_metrics()