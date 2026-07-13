import re
import time
import uuid
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from app.auth.auth import get_current_user, require_role, get_user_role
from app.agent.agent import run_agent
from app.logger import get_logger
from app.metrics import log_security_event
from app.security.data_sanitiser import (
    detect_sensitive_data,
    sanitise_for_llm,
    pending_approvals,
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

    Security flow:
    Step 1: Check if query was pre-approved (contains [approved:UUID] marker)
            If yes — skip sensitive data check, sanitise and run agent.
    Step 2: Detect sensitive data in original query.
            If found — store approval request and return 403 immediately.
    Step 3: User approves via /security/self-approve endpoint.
    Step 4: User resends query with [approved:UUID] marker — goes to Step 1.
    Step 5: Sanitise query and run agent.
    """
    start = time.time()
    user_role = get_user_role(user)
    username = user["username"]

    try:
        # Step 1 — Check if query was pre-approved by user
        approval_match = re.search(r'\[approved:([a-f0-9-]+)\]', request.query)
        if approval_match:
            # Remove the approval marker but keep the real data
            # User has approved — pass original query to LLM as is
            clean_query = request.query.replace(
                approval_match.group(0), ''
            ).strip()

            logger.info(
                f"Pre-approved query — passing original data to LLM | "
                f"user={username} | approval_id={approval_match.group(1)}"
            )
            response = await run_agent(
                query=clean_query,
                user_role=user_role,
                username=username,
                session_id=username
            )
            duration = (time.time() - start) * 1000
            return QueryResponse(
                response=response,
                username=username,
                role=user_role,
                duration_ms=round(duration, 2)
            )

        # Step 2 — Detect sensitive data in original query
        sensitive_data = detect_sensitive_data(request.query)

        # Step 3 — If sensitive data found return 403 immediately with approval ID
        if sensitive_data:
            approval_id = str(uuid.uuid4())
            logger.warning(
                f"Sensitive data detected in query | "
                f"types={list(sensitive_data.keys())} | "
                f"user={username}"
            )

            # Store pending approval immediately
            pending_approvals[approval_id] = {
                "status": "pending",
                "query": request.query[:100],
                "sensitive_data_types": list(sensitive_data.keys()),
                "requested_by": username,
                "requested_at": datetime.now().isoformat(),
                "approved_by": None,
                "approved_at": None,
                "timeout_seconds": 60
            }

            # Log to Power BI metrics
            log_security_event(
                event_type="approval_requested",
                approval_id=approval_id,
                sensitive_data_types=list(sensitive_data.keys()),
                requested_by=username,
                outcome="pending"
            )

            # Return 403 immediately — do not wait 60 seconds
            raise HTTPException(
                status_code=403,
                detail=f"Query contains sensitive data types: "
                       f"{list(sensitive_data.keys())}. "
                       f"Approval ID: {approval_id}"
            )

        # Step 4 — Sanitise query before sending to LLM
        sanitised_query = sanitise_for_llm(
            request.query,
            {"username": username, "role": user_role}
        )

        # Step 5 — Run agent with sanitised query
        logger.info(
            f"Query received | user={username} | "
            f"role={user_role} | query={sanitised_query[:50]}"
        )
        response = await run_agent(
            query=sanitised_query,
            user_role=user_role,
            username=username,
            session_id=username
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
    return {"success": success, "message": f"Next action created successfully for issue {issue_id} — assigned to {assigned_to}, due {due_date}"}


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
    return {"success": success, "message": f"Issue {issue_id} status successfully updated to '{new_status}'"}


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
    """Returns all queries waiting for human approval. Admin only."""
    return {"pending_approvals": get_pending_approvals()}


@router.post("/security/approve/{approval_id}",
    tags=["Security"],
    summary="Approve a pending query — Admin only"
)
async def approve_query(
    approval_id: str,
    user: dict = Depends(require_role("admin"))
):
    """Security officer approves a pending query. Admin only."""
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
    summary="Reject a pending query — Admin only"
)
async def reject_query(
    approval_id: str,
    user: dict = Depends(require_role("admin"))
):
    """Security officer rejects a pending query. Admin only."""
    success = reject_request(approval_id, user["username"])
    if not success:
        raise HTTPException(status_code=404, detail="Approval request not found")
    return {
        "rejected": True,
        "approval_id": approval_id,
        "rejected_by": user["username"]
    }


@router.post("/security/self-approve/{approval_id}",
    tags=["Security"],
    summary="User self-approves their own sensitive query"
)
async def self_approve_query(
    approval_id: str,
    user: dict = Depends(get_current_user)
):
    """
    User approves their own query after seeing the sensitive data warning.
    Logs who approved and when for full audit trail.
    """
    success = approve_request(approval_id, user["username"])
    if not success:
        raise HTTPException(status_code=404, detail="Approval request not found")
    log_security_event(
        event_type="self_approval_granted",
        approval_id=approval_id,
        sensitive_data_types=[],
        requested_by=user["username"],
        outcome="approved",
        approved_by=user["username"]
    )
    logger.info(
        f"SELF APPROVAL | user={user['username']} | approval_id={approval_id}"
    )
    return {
        "approved": True,
        "approval_id": approval_id,
        "approved_by": user["username"]
    }

# ── Skills routes ──────────────────────────────────────────────────
@router.post("/skills/escalation/{customer_name}",
    tags=["Skills"],
    summary="Run Customer Escalation Summary Skill"
)
async def run_escalation(
    customer_name: str,
    user: dict = Depends(get_current_user)
):
    """
    Customer Escalation Summary Skill.
    A structured reusable workflow that analyses customer risk.
    Returns executive summary, risk level, recommended action,
    and missing information identification.
    All authenticated users can invoke this skill.
    """
    from app.skills.escalation_skill import run_escalation_skill
    result = await run_escalation_skill(customer_name)
    return {
        "customer_name": result.customer_name,
        "executive_summary": result.executive_summary,
        "risk_level": result.risk_level,
        "recommended_next_action": result.recommended_next_action,
        "missing_information": result.missing_information,
        "metrics": {
            "total_open_issues": result.total_open_issues,
            "critical_issues": result.critical_issues,
            "high_issues": result.high_issues,
            "duration_ms": result.duration_ms
        }
    }