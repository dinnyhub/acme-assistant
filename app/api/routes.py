import time
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from app.auth.auth import get_current_user, require_role, get_user_role
from app.agent.agent import run_agent
from app.metrics import log_api_request, log_error
from app.logger import get_logger

logger = get_logger(__name__)
router = APIRouter()


# ── Request/Response models ───────────────────────────────────────
class QueryRequest(BaseModel):
    query: str


class QueryResponse(BaseModel):
    response: str
    username: str
    role: str
    duration_ms: float


# ── Routes ────────────────────────────────────────────────────────
@router.post("/query", response_model=QueryResponse, tags=["Agent"], summary="Send a query to the AI agent")
async def query_agent(
    request: QueryRequest,
    user: dict = Depends(get_current_user)
):
    """
    Main endpoint — sends a query to the AI agent.
    The agent reasons about which tools to call and returns a response.
    All authenticated users can use this endpoint.
    """
    start = time.time()
    user_role = get_user_role(user)
    username = user["username"]

    try:
        logger.info(
            f"Query received | user={username} | role={user_role} | query={request.query[:50]}"
        )
        response = await run_agent(
            query=request.query,
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
    except Exception as e:
        log_error("api", "QueryError", str(e), user_role)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/customers", tags=["Customers"], summary="List all customers")
async def list_customers(
    user: dict = Depends(get_current_user)
):
    """
    List all customers.
    All authenticated users can access this.
    """
    from app.database import execute_query
    customers = execute_query("SELECT * FROM customers ORDER BY name")
    return {"customers": customers}


@router.get("/customers/{customer_id}/issues", tags=["Customers"], summary="Get open issues for a customer")
async def get_customer_issues(
    customer_id: int,
    user: dict = Depends(get_current_user)
):
    """
    Get open issues for a specific customer.
    All authenticated users can access this.
    """
    from app.database import get_open_issues
    issues = get_open_issues(customer_id)
    return {"issues": issues, "total": len(issues)}


@router.get("/issues/{issue_id}/history", tags=["Issues"], summary="Get history for a specific issue")
async def get_issue_history(
    issue_id: int,
    user: dict = Depends(get_current_user)
):
    """
    Get history for a specific issue.
    All authenticated users can access this.
    """
    from app.database import get_issue_history
    history = get_issue_history(issue_id)
    return {"history": history, "total_updates": len(history)}


@router.post("/issues/{issue_id}/next-action", tags=["Issues"], summary="Create next action — Admin only")
async def create_next_action(
    issue_id: int,
    action_text: str,
    assigned_to: str,
    due_date: str,
    user: dict = Depends(require_role("admin"))
):
    """
    Create a next action for an issue.
    Admin only — enforced by require_role dependency.
    """
    from app.database import create_next_action
    success = create_next_action(issue_id, action_text, assigned_to, due_date)
    return {"success": success, "message": "Next action created"}


@router.put("/issues/{issue_id}/status", tags=["Issues"], summary="Update issue status — Support/Admin only")
async def update_issue_status(
    issue_id: int,
    new_status: str,
    user: dict = Depends(require_role("support_user"))
):
    """
    Update issue status.
    Support user and admin only.
    """
    from app.database import update_issue_status
    success = update_issue_status(issue_id, new_status)
    return {"success": success, "message": f"Status updated to {new_status}"}