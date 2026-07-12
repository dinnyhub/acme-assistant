import time
from dataclasses import dataclass
from langchain_groq import ChatGroq
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.utils.utils import convert_to_secret_str
import os
from dotenv import load_dotenv
from app.logger import get_logger
from app.metrics import log_llm_call
from app.database import (
    get_customer_by_name,
    get_open_issues,
    get_issue_history
)

load_dotenv()
logger = get_logger(__name__)


@dataclass
class EscalationSummary:
    """
    Structured output of the Customer Escalation Summary Skill.
    A reusable, repeatable workflow distinct from a one-off prompt call.
    """
    customer_name: str
    executive_summary: str
    risk_level: str  # Low / Medium / High / Critical
    recommended_next_action: str
    missing_information: list[str]
    total_open_issues: int
    critical_issues: int
    high_issues: int
    duration_ms: float


def _get_llm() -> ChatGroq:
    """Returns the LLM instance for the skill."""
    return ChatGroq(
        model="llama-3.3-70b-versatile",
        api_key=convert_to_secret_str(os.getenv("GROQ_API_KEY", "")),
        temperature=0
    )


def _calculate_base_risk(issues: list) -> str:
    """
    Calculates base risk level from issue priorities.
    This is a deterministic pre-step before the LLM assessment.
    """
    if not issues:
        return "Low"

    priorities = [i.get("priority", "low") for i in issues]

    if "critical" in priorities:
        return "Critical"
    elif priorities.count("high") >= 2:
        return "High"
    elif "high" in priorities:
        return "Medium"
    else:
        return "Low"


def _identify_missing_info(
    customer: dict,
    issues: list,
    histories: dict
) -> list[str]:
    """
    Identifies missing information before calling the LLM.
    Deterministic check — no LLM needed for this step.
    """
    missing = []

    if not customer.get("email"):
        missing.append("Customer email address is missing")

    if not issues:
        missing.append("No open issues found — unable to assess escalation risk")
        return missing

    for issue in issues:
        issue_id = issue.get("id")
        history = histories.get(issue_id, [])
        if not history:
            missing.append(
                f"Issue {issue_id} ('{issue.get('title', 'Unknown')}') "
                f"has no update history"
            )
        if not issue.get("updated_at"):
            missing.append(
                f"Issue {issue_id} has no last-updated timestamp"
            )

    next_actions_missing = [
        i for i in issues
        if not histories.get(i.get("id"))
    ]
    if next_actions_missing:
        missing.append(
            f"{len(next_actions_missing)} issue(s) have no next actions defined"
        )

    return missing


async def run_escalation_skill(customer_name: str) -> EscalationSummary:
    """
    Customer Escalation Summary Skill.

    A structured, repeatable workflow that:
    1. Fetches customer data from database
    2. Calculates base risk deterministically
    3. Identifies missing information
    4. Calls LLM to generate executive summary and recommendations
    5. Returns structured EscalationSummary output

    This is distinct from a one-off prompt — it is a reusable
    workflow with defined inputs, structured outputs, and
    deterministic pre/post processing steps.
    """
    start = time.time()
    logger.info(f"Escalation skill invoked | customer={customer_name}")

    # Step 1 — Fetch customer from database
    customer = get_customer_by_name(customer_name)
    if not customer:
        duration = (time.time() - start) * 1000
        return EscalationSummary(
            customer_name=customer_name,
            executive_summary=f"Customer '{customer_name}' not found in the system.",
            risk_level="Unknown",
            recommended_next_action="Verify customer name and try again.",
            missing_information=["Customer not found in database"],
            total_open_issues=0,
            critical_issues=0,
            high_issues=0,
            duration_ms=round(duration, 2)
        )

    # Step 2 — Fetch open issues
    issues = get_open_issues(customer["id"])

    # Step 3 — Fetch history for each issue
    histories = {}
    for issue in issues:
        issue_id = issue.get("id")
        histories[issue_id] = get_issue_history(issue_id)

    # Step 4 — Deterministic risk calculation
    base_risk = _calculate_base_risk(issues)

    # Step 5 — Identify missing information
    missing_info = _identify_missing_info(customer, issues, histories)

    # Step 6 — Build context for LLM
    issues_context = ""
    for issue in issues:
        issue_id = issue.get("id")
        history = histories.get(issue_id, [])
        history_text = "\n".join([
            f"  - {str(h.get('created_at', ''))[:10]}: {h.get('update_text', '')}"
            for h in history
        ]) or "  No history available"

        issues_context += f"""
Issue ID: {issue_id}
Title: {issue.get('title')}
Priority: {issue.get('priority')}
Status: {issue.get('status')}
History:
{history_text}
"""

    # Step 7 — Call LLM for executive summary and recommendations
    llm = _get_llm()
    llm_start = time.time()

    system_prompt = """You are an expert customer success analyst at Acme Operations.
Your role is to assess customer escalation risk and provide actionable recommendations.
You must be concise, precise, and business-focused.
Always respond in the exact format requested."""

    user_prompt = f"""Analyse this customer situation and provide a structured assessment.

CUSTOMER: {customer.get('name')}
ACCOUNT TYPE: {customer.get('account_type')}
EMAIL: {customer.get('email')}
TOTAL OPEN ISSUES: {len(issues)}
BASE RISK ASSESSMENT: {base_risk}

OPEN ISSUES AND HISTORY:
{issues_context if issues_context else "No open issues found."}

Provide your assessment in this EXACT format:

EXECUTIVE_SUMMARY: [2-3 sentences summarising the customer situation and key concerns]
RISK_LEVEL: [{base_risk}] [Confirm or adjust this risk level with brief justification]
RECOMMENDED_ACTION: [Single most important action to take in the next 24-48 hours]
"""

    try:
        response = llm.invoke([
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt)
        ])

        llm_duration = (time.time() - llm_start) * 1000
        log_llm_call(
            model="llama-3.3-70b-versatile",
            prompt_tokens=0,
            response_tokens=0,
            duration_ms=llm_duration,
            success=True
        )

        # Parse LLM response
        response_text = str(response.content)
        lines = response_text.strip().split('\n')

        executive_summary: str = ""
        risk_level: str = base_risk
        recommended_action: str = ""

        for line in lines:
            if line.startswith("EXECUTIVE_SUMMARY:"):
                executive_summary = line.replace("EXECUTIVE_SUMMARY:", "").strip()
            elif line.startswith("RISK_LEVEL:"):
                risk_text = line.replace("RISK_LEVEL:", "").strip()
                for level in ["Critical", "High", "Medium", "Low"]:
                    if level.lower() in risk_text.lower():
                        risk_level = level
                        break
            elif line.startswith("RECOMMENDED_ACTION:"):
                recommended_action = line.replace("RECOMMENDED_ACTION:", "").strip()

        # Fallback if parsing fails
        if not executive_summary:
            executive_summary = response_text[:300]
        if not recommended_action:
            recommended_action = "Review all open issues and contact customer within 24 hours."

    except Exception as e:
        llm_duration = (time.time() - llm_start) * 1000
        log_llm_call(
            model="llama-3.3-70b-versatile",
            prompt_tokens=0,
            response_tokens=0,
            duration_ms=llm_duration,
            success=False,
            error=str(e)
        )
        logger.error(f"Escalation skill LLM error: {e}")
        executive_summary = f"Unable to generate AI summary. Base risk: {base_risk}."
        risk_level = base_risk
        recommended_action = "Review open issues manually and contact customer."

    duration = (time.time() - start) * 1000
    logger.info(
        f"Escalation skill completed | customer={customer_name} | "
        f"risk={risk_level} | issues={len(issues)} | duration={duration:.2f}ms"
    )

    return EscalationSummary(
        customer_name=customer.get("name", customer_name),
        executive_summary=executive_summary,
        risk_level=risk_level,
        recommended_next_action=recommended_action,
        missing_information=missing_info,
        total_open_issues=len(issues),
        critical_issues=sum(1 for i in issues if i.get("priority") == "critical"),
        high_issues=sum(1 for i in issues if i.get("priority") == "high"),
        duration_ms=round(duration, 2)
    )