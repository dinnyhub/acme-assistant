import re
import asyncio
import time
from datetime import datetime
from app.logger import get_logger
from app.metrics import log_security_event

logger = get_logger(__name__)

# ── Sensitive data patterns ────────────────────────────────────────
SENSITIVE_PATTERNS = {
    "email": r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b',
    "phone": r'\b(\+44|0044|0)[0-9\s\-]{9,13}\b',
    "credit_card": r'\b(?:\d{4}[\s\-]?){3}\d{4}\b',
    "national_insurance": r'\b[A-Z]{2}[0-9]{6}[A-Z]\b',
    "sort_code": r'\b\d{2}-\d{2}-\d{2}\b(?!\d)',
    "bank_account": r'\b\d{8}\b',
    "passport": r'\b[A-Z]{2}[0-9]{7}\b',
    "ip_address": r'\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b',
}

BLOCKED_FIELDS = [
    "password", "secret", "token", "api_key",
    "card_number", "cvv", "pin", "ssn",
    "national_insurance", "passport_number"
]

pending_approvals: dict = {}


class SensitiveDataDetected(Exception):
    """Raised when sensitive data is found in query."""
    pass


class HumanApprovalTimeout(Exception):
    """Raised when human does not approve within timeout."""
    pass


def detect_sensitive_data(text: str) -> dict:
    """
    Scans text for sensitive data patterns.
    Returns a dict of detected patterns and their matches.
    """
    detected = {}
    for pattern_name, pattern in SENSITIVE_PATTERNS.items():
        matches = re.findall(pattern, text, re.IGNORECASE)
        if matches:
            detected[pattern_name] = len(matches)
    return detected


def sanitise_for_llm(data: str, user: dict) -> str:
    """
    Sanitises data before sending to LLM.
    Redacts sensitive patterns automatically.
    Logs what was redacted and who triggered it.
    """
    original = data
    sanitised = data

    for pattern_name, pattern in SENSITIVE_PATTERNS.items():
        matches = re.findall(pattern, sanitised, re.IGNORECASE)
        if matches:
            sanitised = re.sub(
                pattern,
                f"[REDACTED-{pattern_name.upper()}]",
                sanitised,
                flags=re.IGNORECASE
            )
            logger.warning(
                f"SENSITIVE DATA REDACTED | "
                f"type={pattern_name} | "
                f"count={len(matches)} | "
                f"user={user.get('username', 'unknown')} | "
                f"role={user.get('role', 'unknown')}"
            )
            # Log redaction to Power BI metrics
            log_security_event(
                event_type="data_redacted",
                approval_id="auto-redact",
                sensitive_data_types=[pattern_name],
                requested_by=user.get("username", "unknown"),
                outcome="redacted"
            )

    if sanitised != original:
        logger.info(
            f"DATA SANITISED BEFORE LLM | "
            f"user={user.get('username', 'unknown')} | "
            f"original_length={len(original)} | "
            f"sanitised_length={len(sanitised)}"
        )

    return sanitised


def check_blocked_fields(data: dict) -> list:
    """
    Checks if any blocked fields exist in the data dict.
    Returns list of blocked field names found.
    """
    found = []
    for key in data.keys():
        if key.lower() in BLOCKED_FIELDS:
            found.append(key)
    return found


async def request_human_approval(
    approval_id: str,
    query: str,
    sensitive_data: dict,
    username: str,
    timeout_seconds: int = 60
) -> bool:
    """
    Requests human approval before sending sensitive data to LLM.
    - Logs the approval request with timestamp and who requested it
    - Waits up to timeout_seconds for approval
    - If no approval received raises HumanApprovalTimeout
    - Logs the outcome with approver details to logs and Power BI
    """
    pending_approvals[approval_id] = {
        "status": "pending",
        "query": query[:100],
        "sensitive_data_types": list(sensitive_data.keys()),
        "requested_by": username,
        "requested_at": datetime.now().isoformat(),
        "approved_by": None,
        "approved_at": None,
        "timeout_seconds": timeout_seconds
    }

    logger.warning(
        f"HUMAN APPROVAL REQUIRED | "
        f"approval_id={approval_id} | "
        f"sensitive_types={list(sensitive_data.keys())} | "
        f"requested_by={username} | "
        f"timeout={timeout_seconds}s"
    )

    # Log approval request to Power BI metrics
    log_security_event(
        event_type="approval_requested",
        approval_id=approval_id,
        sensitive_data_types=list(sensitive_data.keys()),
        requested_by=username,
        outcome="pending"
    )

    # Wait for approval with timeout
    start_time = time.time()
    while time.time() - start_time < timeout_seconds:
        approval = pending_approvals.get(approval_id, {})

        if approval.get("status") == "approved":
            logger.info(
                f"HUMAN APPROVAL GRANTED | "
                f"approval_id={approval_id} | "
                f"approved_by={approval.get('approved_by')} | "
                f"approved_at={approval.get('approved_at')}"
            )
            # Log approval to Power BI metrics
            log_security_event(
                event_type="approval_granted",
                approval_id=approval_id,
                sensitive_data_types=list(sensitive_data.keys()),
                requested_by=username,
                outcome="approved",
                approved_by=approval.get("approved_by")
            )
            return True

        if approval.get("status") == "rejected":
            logger.warning(
                f"HUMAN APPROVAL REJECTED | "
                f"approval_id={approval_id} | "
                f"rejected_by={approval.get('approved_by')}"
            )
            # Log rejection to Power BI metrics
            log_security_event(
                event_type="approval_rejected",
                approval_id=approval_id,
                sensitive_data_types=list(sensitive_data.keys()),
                requested_by=username,
                outcome="rejected",
                approved_by=approval.get("approved_by")
            )
            return False

        await asyncio.sleep(2)

    # Timeout reached
    pending_approvals[approval_id]["status"] = "timeout"
    logger.error(
        f"HUMAN APPROVAL TIMEOUT | "
        f"approval_id={approval_id} | "
        f"timeout={timeout_seconds}s | "
        f"requested_by={username} | "
        f"PROCESS STOPPED"
    )
    # Log timeout to Power BI metrics
    log_security_event(
        event_type="approval_timeout",
        approval_id=approval_id,
        sensitive_data_types=list(sensitive_data.keys()),
        requested_by=username,
        outcome="timeout"
    )
    raise HumanApprovalTimeout(
        f"Human approval timeout after {timeout_seconds} seconds. "
        f"Query contains sensitive data types: {list(sensitive_data.keys())}. "
        f"Process stopped for security compliance. "
        f"Approval ID: {approval_id} — contact your security officer."
    )


def get_pending_approvals() -> dict:
    """Returns all pending approvals for the monitoring dashboard."""
    return {
        k: v for k, v in pending_approvals.items()
        if v["status"] == "pending"
    }


def approve_request(
    approval_id: str,
    approver_username: str
) -> bool:
    """
    Security officer approves a pending request.
    Logs who approved and when.
    """
    if approval_id not in pending_approvals:
        return False

    pending_approvals[approval_id]["status"] = "approved"
    pending_approvals[approval_id]["approved_by"] = approver_username
    pending_approvals[approval_id]["approved_at"] = datetime.now().isoformat()

    logger.info(
        f"APPROVAL GRANTED | "
        f"approval_id={approval_id} | "
        f"approved_by={approver_username} | "
        f"approved_at={datetime.now().isoformat()}"
    )
    return True


def reject_request(
    approval_id: str,
    approver_username: str
) -> bool:
    """
    Security officer rejects a pending request.
    Logs who rejected and when.
    """
    if approval_id not in pending_approvals:
        return False

    pending_approvals[approval_id]["status"] = "rejected"
    pending_approvals[approval_id]["approved_by"] = approver_username
    pending_approvals[approval_id]["approved_at"] = datetime.now().isoformat()

    logger.warning(
        f"APPROVAL REJECTED | "
        f"approval_id={approval_id} | "
        f"rejected_by={approver_username}"
    )
    return True