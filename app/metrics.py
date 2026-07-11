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
    "errors": []
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
            "errors": errors[-50:]
        }
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