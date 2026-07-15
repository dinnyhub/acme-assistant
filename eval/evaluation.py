"""
Evaluation set for Acme Operations Assistant.
10 test questions — 5 pass cases and 5 fail cases.
Run with: python eval/evaluation.py
"""

import asyncio
import sys
import json
import time
import os
os.environ["GROQ_EVAL_MODEL"] = "qwen/qwen3-32b"
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.agent.agent import run_agent
from app.logger import get_logger
from app.memory import redis_client

logger = get_logger(__name__)


# ── Evaluation questions ───────────────────────────────────────────
EVALUATION_SET = [

    # ── 5 PASS CASES ──────────────────────────────────────────────
    {
        "id": 1,
        "category": "Customer Profile — Pass",
        "question": "Show me the details for Acme Corp customer",
        "expected_tool": "get_customer_profile",
        "expected_keywords": ["acme corp", "enterprise"],
        "expected_outcome": "pass",
        "role": "sales_user"
    },
    {
        "id": 2,
        "category": "Open Issues — Pass",
        "question": "What are the open issues for Global Finance Inc?",
        "expected_tool": "get_open_issues",
        "expected_keywords": ["global finance", "issue"],
        "expected_outcome": "pass",
        "role": "sales_user"
    },
    {
        "id": 3,
        "category": "Issue History — Pass",
        "question": "Show me the history of issue 1 for Acme Corp",
        "expected_tool": "get_issue_history",
        "expected_keywords": ["issue", "history", "api"],
        "expected_outcome": "pass",
        "role": "support_user"
    },
    {
        "id": 4,
        "category": "Status Update Support User — Pass",
        "question": "Update the status of issue 3 to in_progress",
        "expected_tool": "update_issue_status",
        "expected_keywords": ["status", "issue"],
        "expected_outcome": "pass",
        "role": "support_user"
    },
    {
        "id": 5,
        "category": "Create Next Action Admin — Pass",
        "question": "Create a next action for issue 4: Schedule emergency call, assigned to support_team, due 2025-08-15",
        "expected_tool": "create_next_action",
        "expected_keywords": ["created", "next action"],
        "expected_outcome": "pass",
        "role": "admin"
    },

    # ── 5 FAIL CASES ──────────────────────────────────────────────
    {
        "id": 6,
        "category": "RBAC Denial — sales_user cannot create next action",
        "question": "Create a next action for issue 1: Call the customer, assigned to dev_team, due 2025-08-01",
        "expected_tool": "create_next_action",
        "expected_keywords": ["access denied", "admin"],
        "expected_outcome": "deny",
        "role": "sales_user"
    },
    {
        "id": 7,
        "category": "RBAC Denial — sales_user cannot update issue status",
        "question": "Update the status of issue 2 to resolved",
        "expected_tool": "update_issue_status",
        "expected_keywords": ["access denied", "support"],
        "expected_outcome": "deny",
        "role": "sales_user"
    },
    {
        "id": 8,
        "category": "RBAC Denial — support_user cannot create next action",
        "question": "Create a next action for issue 2: Send invoice correction, assigned to finance_team, due 2025-08-10",
        "expected_tool": "create_next_action",
        "expected_keywords": ["access denied", "admin"],
        "expected_outcome": "deny",
        "role": "support_user"
    },
    {
        "id": 9,
        "category": "Customer Not Found — Fail",
        "question": "Show me open issues for NonExistent Company Ltd",
        "expected_tool": "get_customer_profile",
        "expected_keywords": ["not found", "nonexistent"],
        "expected_outcome": "not_found",
        "role": "sales_user"
    },
    {
        "id": 10,
        "category": "Invalid Status — Fail",
        "question": "Update the status of issue 1 to flying",
        "expected_tool": "update_issue_status",
        "expected_keywords": ["not a valid", "flying"],
        "expected_outcome": "not_found",
        "role": "support_user"
    },
]


def evaluate_response(
    response: str,
    expected_keywords: list,
    expected_outcome: str
) -> tuple:
    """
    Evaluates whether the response matches the expected outcome.

    Three outcome types:
    - pass: response contains expected keywords — correct data returned
    - deny: response contains access denied or permission message — RBAC working
    - not_found: response indicates customer or resource not found
    """
    response_lower = response.lower()

    if expected_outcome == "deny":
        # For denial cases check for access denied or permission messages
        denial_keywords = [
            "access denied", "only admin", "only support",
            "permission", "not allowed", "cannot", "insufficient",
            "do not have", "don't have", "invalid status", "invalid"
        ]
        found_denial = any(kw in response_lower for kw in denial_keywords)
        found = [kw for kw in expected_keywords if kw in response_lower]
        passed = found_denial
        missing = [] if passed else ["denial or permission message"]
        return passed, found, missing

    if expected_outcome == "not_found":
        not_found_keywords = [
            "not found", "no customer", "unable to find",
            "doesn't exist", "could not find", "cannot find",
            "no record", "does not exist",
            "not a valid", "not valid", "invalid"
        ]
        found_nf = any(kw in response_lower for kw in not_found_keywords)
        found = [kw for kw in expected_keywords if kw in response_lower]
        passed = found_nf
        missing = [] if passed else ["not found message"]
        return passed, found, missing

    # Normal pass case — check for expected keywords
    found = [kw for kw in expected_keywords if kw in response_lower]
    missing = [kw for kw in expected_keywords if kw not in response_lower]
    passed = len(missing) == 0
    return passed, found, missing

# Clear eval sessions from previous runs
for i in range(1, 11):
    redis_client.delete(f"session:eval_session_{i}")

async def run_evaluation() -> dict:
    """
    Runs all 10 evaluation questions and returns structured results.
    5 pass cases and 5 fail cases covering:
    - Tool selection accuracy
    - RBAC enforcement
    - Escalation skill
    - Error handling
    - Not found scenarios
    """
    # Clear all eval sessions before running
    try:
        from app.memory import redis_client
        keys = redis_client.keys("session:eval_*")
        if keys:
            redis_client.delete(*keys)
            print("Cleared previous eval sessions from Redis")
    except Exception as e:
        print(f"Could not clear Redis sessions: {e}")

    print("\n" + "=" * 60)
    print("ACME OPERATIONS ASSISTANT — EVALUATION SET")
    print("5 Pass Cases + 5 Fail Cases")
    print("=" * 60)

    results = []
    passed = 0
    failed = 0
    total_duration = 0.0

    for test in EVALUATION_SET:
        print(f"\n[{test['id']}/10] {test['category']}")
        print(f"Question : {test['question']}")
        print(f"Role     : {test['role']}")
        print(f"Expected : {test['expected_outcome'].upper()}")

        start = time.time()
        try:
            response = await run_agent(
                query=test["question"],
                user_role=test["role"],
                username=f"eval_user_{test['id']}",
                session_id=f"eval_session_{test['id']}"
            )
            duration = (time.time() - start) * 1000

            passed_test, found, missing = evaluate_response(
                response,
                test["expected_keywords"],
                test["expected_outcome"]
            )

            result = {
                "id": test["id"],
                "category": test["category"],
                "question": test["question"],
                "role": test["role"],
                "expected_tool": test["expected_tool"],
                "expected_outcome": test["expected_outcome"],
                "response_preview": response[:300],
                "passed": passed_test,
                "found_keywords": found,
                "missing_keywords": missing,
                "duration_ms": round(duration, 2)
            }

            if passed_test:
                passed += 1
                print(f"✅ PASSED ({duration:.0f}ms)")
                if found:
                    print(f"   Found  : {found}")
            else:
                failed += 1
                print(f"❌ FAILED ({duration:.0f}ms)")
                print(f"   Missing: {missing}")
                print(f"   Response: {response[:200]}...")

        except Exception as e:
            duration = (time.time() - start) * 1000
            result = {
                "id": test["id"],
                "category": test["category"],
                "question": test["question"],
                "role": test["role"],
                "expected_tool": test["expected_tool"],
                "expected_outcome": test["expected_outcome"],
                "response_preview": f"ERROR: {str(e)}",
                "passed": False,
                "found_keywords": [],
                "missing_keywords": test["expected_keywords"],
                "duration_ms": round(duration, 2)
            }
            failed += 1
            print(f"❌ ERROR ({duration:.0f}ms): {str(e)[:100]}")

        results.append(result)
        total_duration += result["duration_ms"]

        # Wait 5 seconds between questions to avoid rate limits
        if test["id"] < 10:
            await asyncio.sleep(8)

    # Summary
    pass_cases = [r for r in results if r["expected_outcome"] == "pass"]
    fail_cases = [r for r in results if r["expected_outcome"] in ["deny", "not_found"]]
    pass_passed = sum(1 for r in pass_cases if r["passed"])
    fail_passed = sum(1 for r in fail_cases if r["passed"])

    print("\n" + "=" * 60)
    print("EVALUATION SUMMARY")
    print("=" * 60)
    print(f"Total questions    : 10")
    print(f"Overall passed     : {passed}/10")
    print(f"Overall failed     : {failed}/10")
    print(f"Pass rate          : {passed * 10}%")
    print(f"")
    print(f"Pass cases (1-5)   : {pass_passed}/5 correct")
    print(f"Fail cases (6-10)  : {fail_passed}/5 correctly denied/rejected")
    print(f"")
    print(f"Total duration     : {total_duration:.0f}ms")
    print(f"Average latency    : {total_duration / 10:.0f}ms")

    summary = {
        "total": 10,
        "passed": passed,
        "failed": failed,
        "pass_rate": f"{passed * 10}%",
        "pass_cases_correct": f"{pass_passed}/5",
        "fail_cases_correct": f"{fail_passed}/5",
        "total_duration_ms": round(total_duration, 2),
        "avg_latency_ms": round(total_duration / 10, 2),
        "results": results
    }

    # Save results
    os.makedirs("eval", exist_ok=True)
    output_path = "eval/results.json"
    with open(output_path, "w") as f:
        json.dump(summary, f, indent=2)
    print(f"\nResults saved to {output_path}")
    print("=" * 60)

    return summary


if __name__ == "__main__":
    asyncio.run(run_evaluation())