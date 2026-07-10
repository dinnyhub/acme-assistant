import time
from app.database import (
    get_customer_by_name,
    get_open_issues,
    get_issue_history,
    get_next_actions,
    create_next_action,
    update_issue_status
)
from app.metrics import log_tool_call
from app.logger import get_logger

logger = get_logger(__name__)


def tool_get_customer_profile(customer_name: str) -> dict:
    """
    Tool 1: Get customer profile by name.
    Available to: all authenticated users.
    """
    start = time.time()
    try:
        customer = get_customer_by_name(customer_name)
        duration = (time.time() - start) * 1000
        if not customer:
            log_tool_call("get_customer_profile", 
                         {"customer_name": customer_name}, 
                         duration, False, "Customer not found")
            return {"error": f"No customer found with name: {customer_name}"}
        log_tool_call("get_customer_profile",
                     {"customer_name": customer_name},
                     duration, True)
        return {"customer": customer}
    except Exception as e:
        duration = (time.time() - start) * 1000
        log_tool_call("get_customer_profile",
                     {"customer_name": customer_name},
                     duration, False, str(e))
        return {"error": str(e)}


def tool_get_open_issues(customer_id: int) -> dict:
    """
    Tool 2: Get all open issues for a customer.
    Available to: all authenticated users.
    """
    start = time.time()
    try:
        issues = get_open_issues(customer_id)
        duration = (time.time() - start) * 1000
        log_tool_call("get_open_issues",
                     {"customer_id": customer_id},
                     duration, True)
        return {
            "issues": issues,
            "total_open": len(issues),
            "critical": sum(1 for i in issues if i["priority"] == "critical"),
            "high": sum(1 for i in issues if i["priority"] == "high")
        }
    except Exception as e:
        duration = (time.time() - start) * 1000
        log_tool_call("get_open_issues",
                     {"customer_id": customer_id},
                     duration, False, str(e))
        return {"error": str(e)}


def tool_get_issue_history(issue_id: int) -> dict:
    """
    Tool 3: Get history and updates for a specific issue.
    Available to: all authenticated users.
    """
    start = time.time()
    try:
        history = get_issue_history(issue_id)
        duration = (time.time() - start) * 1000
        log_tool_call("get_issue_history",
                     {"issue_id": issue_id},
                     duration, True)
        return {
            "issue_id": issue_id,
            "history": history,
            "total_updates": len(history)
        }
    except Exception as e:
        duration = (time.time() - start) * 1000
        log_tool_call("get_issue_history",
                     {"issue_id": issue_id},
                     duration, False, str(e))
        return {"error": str(e)}


def tool_create_next_action(
    issue_id: int,
    action_text: str,
    assigned_to: str,
    due_date: str,
    user_role: str = "unknown"
) -> dict:
    """
    Tool 4: Create a recommended next action for an issue.
    Available to: admin only — RBAC enforced here.
    """
    start = time.time()

    # RBAC check — only admin can create next actions
    if user_role != "admin":
        duration = (time.time() - start) * 1000
        log_tool_call("create_next_action",
                     {"issue_id": issue_id},
                     duration, False, "Insufficient permissions")
        return {
            "error": "Access denied. Only admin users can create next actions."
        }

    try:
        success = create_next_action(
            issue_id, action_text, assigned_to, due_date
        )
        duration = (time.time() - start) * 1000
        log_tool_call("create_next_action",
                     {"issue_id": issue_id, "action": action_text},
                     duration, True)
        return {
            "success": True,
            "message": f"Next action created for issue {issue_id}",
            "action": action_text,
            "assigned_to": assigned_to,
            "due_date": due_date
        }
    except Exception as e:
        duration = (time.time() - start) * 1000
        log_tool_call("create_next_action",
                     {"issue_id": issue_id},
                     duration, False, str(e))
        return {"error": str(e)}


def tool_update_issue_status(
    issue_id: int,
    new_status: str,
    user_role: str = "unknown"
) -> dict:
    """
    Tool 5: Update the status of an issue.
    Available to: support_user and admin only.
    """
    start = time.time()

    # RBAC check
    if user_role not in ["support_user", "admin"]:
        duration = (time.time() - start) * 1000
        log_tool_call("update_issue_status",
                     {"issue_id": issue_id},
                     duration, False, "Insufficient permissions")
        return {
            "error": "Access denied. Only support users and admins can update issues."
        }

    valid_statuses = ["open", "in_progress", "resolved", "closed"]
    if new_status not in valid_statuses:
        return {"error": f"Invalid status. Must be one of: {valid_statuses}"}

    try:
        success = update_issue_status(issue_id, new_status)
        duration = (time.time() - start) * 1000
        log_tool_call("update_issue_status",
                     {"issue_id": issue_id, "status": new_status},
                     duration, True)
        return {
            "success": True,
            "message": f"Issue {issue_id} status updated to {new_status}"
        }
    except Exception as e:
        duration = (time.time() - start) * 1000
        log_tool_call("update_issue_status",
                     {"issue_id": issue_id},
                     duration, False, str(e))
        return {"error": str(e)}