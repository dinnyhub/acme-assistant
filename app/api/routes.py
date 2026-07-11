import time
import uuid
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from app.auth.auth import get_current_user, require_role, get_user_role
from app.agent.agent import run_agent
from app.logger import get_logger
from app.metrics import log_security_event
from app.security.data_sanitiser import (
    detect_sensitive_data,
    sanitise_for_llm,
    request_human_approval,
    HumanApprovalTimeout,
    get_pending_approvals,
    approve_request,
    reject_request
)

logger = get_logger(__name__)
router = APIRouter()


# ── Request/Response models ────────────────────────────────────────
class QueryRequest(BaseModel):
    query: str


class QueryResponse(BaseModel):
    response: str
    username: str
    role: str
    duration_ms: float


class MCPToolRequest(BaseModel):
    tool_name: str
    arguments: dict


# ── Agent routes ───────────────────────────────────────────────────
@router.post("/query",
    response_model=QueryResponse,
    tags=["Agent"],
    summary="Send a query to the AI agent"
)
async def query_agent(
    request: QueryRequest,
    user: dict = Depends(get_current_user)
):
    """
    Main endpoint — sends a query to the AI agent.
    Checks for sensitive data before hitting the LLM.
    Requests human approval if sensitive data is detected.
    Sanitises data before sending to LLM.
    All authenticated users can use this endpoint.
    """
    start = time.time()
    user_role = get_user_role(user)
    username = user["username"]

    try:
        # Step 1 — Detect sensitive data in query
        sensitive_data = detect_sensitive_data(request.query)

        # Step 2 — If sensitive data found request human approval
        if sensitive_data:
            approval_id = str(uuid.uuid4())
            logger.warning(
                f"Sensitive data detected in query | "
                f"types={list(sensitive_data.keys())} | "
                f"user={username}"
            )
            try:
                approved = await request_human_approval(
                    approval_id=approval_id,
                    query=request.query,
                    sensitive_data=sensitive_data,
                    username=username,
                    timeout_seconds=60
                )
                if not approved:
                    raise HTTPException(
                        status_code=403,
                        detail="Query rejected by security officer — contains sensitive data."
                    )
            except HumanApprovalTimeout as e:
                raise HTTPException(status_code=403, detail=str(e))

        # Step 3 — Sanitise query before sending to LLM
        sanitised_query = sanitise_for_llm(
            request.query,
            {"username": username, "role": user_role}
        )

        # Step 4 — Run agent with sanitised query
        logger.info(
            f"Query received | user={username} | "
            f"role={user_role} | query={sanitised_query[:50]}"
        )
        response = await run_agent(
            query=sanitised_query,
            user_role=user_role,
            username=username
        )
        duration = (time.time() - start) * 1000
        return QueryResponse(
            response=response,
            username=username,
            role=user_role,
            duration_ms=round(duration, 2)
        )

    except HTTPException:
        raise
    except Exception as e:
        log_security_event(
            event_type="query_error",
            approval_id="none",
            sensitive_data_types=[],
            requested_by=username,
            outcome="error"
        )
        logger.error(f"QueryError | {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


# ── Customer routes ────────────────────────────────────────────────
@router.get("/customers",
    tags=["Customers"],
    summary="List all customers"
)
async def list_customers(
    user: dict = Depends(get_current_user)
):
    """List all customers. All authenticated users can access this."""
    from app.database import execute_query
    customers = execute_query("SELECT * FROM customers ORDER BY name")
    return {"customers": customers}


@router.get("/customers/{customer_id}/issues",
    tags=["Customers"],
    summary="Get open issues for a customer"
)
async def get_customer_issues(
    customer_id: int,
    user: dict = Depends(get_current_user)
):
    """Get open issues for a specific customer."""
    from app.database import get_open_issues
    issues = get_open_issues(customer_id)
    return {"issues": issues, "total": len(issues)}


# ── Issue routes ───────────────────────────────────────────────────
@router.get("/issues/{issue_id}/history",
    tags=["Issues"],
    summary="Get history for a specific issue"
)
async def get_issue_history(
    issue_id: int,
    user: dict = Depends(get_current_user)
):
    """Get history for a specific issue."""
    from app.database import get_issue_history
    history = get_issue_history(issue_id)
    return {"history": history, "total_updates": len(history)}


@router.post("/issues/{issue_id}/next-action",
    tags=["Issues"],
    summary="Create next action — Admin only"
)
async def create_next_action(
    issue_id: int,
    action_text: str,
    assigned_to: str,
    due_date: str,
    user: dict = Depends(require_role("admin"))
):
    """Create a next action for an issue. Admin only."""
    from app.database import create_next_action
    success = create_next_action(issue_id, action_text, assigned_to, due_date)
    return {"success": success, "message": "Next action created"}


@router.put("/issues/{issue_id}/status",
    tags=["Issues"],
    summary="Update issue status — Support/Admin only"
)
async def update_issue_status(
    issue_id: int,
    new_status: str,
    user: dict = Depends(require_role("support_user"))
):
    """Update issue status. Support user and admin only."""
    from app.database import update_issue_status
    success = update_issue_status(issue_id, new_status)
    return {"success": success, "message": f"Status updated to {new_status}"}


# ── MCP routes ─────────────────────────────────────────────────────
@router.get("/mcp/tools",
    tags=["MCP Server"],
    summary="List all available MCP tools"
)
async def list_mcp_tools(
    user: dict = Depends(get_current_user)
):
    """Returns all tools registered on the MCP server."""
    from app.mcp_server.server import mcp_server
    return mcp_server.list_tools()


@router.post("/mcp/call",
    tags=["MCP Server"],
    summary="Call an MCP tool directly"
)
async def call_mcp_tool(
    request: MCPToolRequest,
    user: dict = Depends(get_current_user)
):
    """Directly call an MCP tool by name with arguments."""
    from app.mcp_server.server import mcp_server
    result = mcp_server.call_tool(request.tool_name, request.arguments)
    return result


# ── Security routes ────────────────────────────────────────────────
@router.get("/security/pending-approvals",
    tags=["Security"],
    summary="Get all pending human approvals"
)
async def list_pending_approvals(
    user: dict = Depends(require_role("admin"))
):
    """
    Returns all queries waiting for human approval.
    Admin only — security officers use this to review and approve.
    """
    return {"pending_approvals": get_pending_approvals()}


@router.post("/security/approve/{approval_id}",
    tags=["Security"],
    summary="Approve a pending query"
)
async def approve_query(
    approval_id: str,
    user: dict = Depends(require_role("admin"))
):
    """
    Security officer approves a pending query.
    Logs who approved and when.
    Admin only.
    """
    success = approve_request(approval_id, user["username"])
    if not success:
        raise HTTPException(status_code=404, detail="Approval request not found")
    return {
        "approved": True,
        "approval_id": approval_id,
        "approved_by": user["username"]
    }


@router.post("/security/reject/{approval_id}",
    tags=["Security"],
    summary="Reject a pending query"
)
async def reject_query(
    approval_id: str,
    user: dict = Depends(require_role("admin"))
):
    """
    Security officer rejects a pending query.
    Logs who rejected and when.
    Admin only.
    """
    success = reject_request(approval_id, user["username"])
    if not success:
        raise HTTPException(status_code=404, detail="Approval request not found")
    return {
        "rejected": True,
        "approval_id": approval_id,
        "rejected_by": user["username"]
    }