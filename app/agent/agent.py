import os
import time
from dotenv import load_dotenv
from langchain_groq import ChatGroq
from langchain_core.utils.utils import convert_to_secret_str
from langchain_core.tools import StructuredTool
from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode
from typing import TypedDict, Annotated, Any
import operator

from app.agent.tools import (
    tool_get_customer_profile,
    tool_get_open_issues,
    tool_get_issue_history,
    tool_create_next_action,
    tool_update_issue_status
)
from app.metrics import log_llm_call, log_agent_event
from app.logger import get_logger

load_dotenv()
logger = get_logger(__name__)


# ── State definition ──────────────────────────────────────────────
class AgentState(TypedDict):
    messages: Annotated[list[Any], operator.add]
    user_role: str
    username: str


# ── LLM setup ─────────────────────────────────────────────────────
def get_llm() -> ChatGroq:
    return ChatGroq(
        model="llama-3.3-70b-versatile",
        api_key=convert_to_secret_str(os.getenv("GROQ_API_KEY", "")),
        temperature=0
    )


# ── Tool definitions ───────────────────────────────────────────────
def make_tools(user_role: str) -> list:
    return [
        StructuredTool.from_function(
            func=tool_get_customer_profile,
            name="get_customer_profile",
            description="Get customer profile by name. Use when user asks about a specific customer."
        ),
        StructuredTool.from_function(
            func=tool_get_open_issues,
            name="get_open_issues",
            description="Get all open issues for a customer. Requires customer_id from get_customer_profile."
        ),
        StructuredTool.from_function(
            func=tool_get_issue_history,
            name="get_issue_history",
            description="Get history and updates for a specific issue. Requires issue_id."
        ),
        StructuredTool.from_function(
            func=lambda issue_id, action_text, assigned_to, due_date: tool_create_next_action(
                issue_id, action_text, assigned_to, due_date, user_role
            ),
            name="create_next_action",
            description="Create a recommended next action for an issue. Admin only."
        ),
        StructuredTool.from_function(
            func=lambda issue_id, new_status: tool_update_issue_status(
                issue_id, new_status, user_role
            ),
            name="update_issue_status",
            description="Update the status of an issue. Support user and admin only."
        ),
    ]


# ── Agent node ────────────────────────────────────────────────────
def agent_node(state: dict, llm_with_tools: Any) -> dict:  # type: ignore
    start = time.time()
    system_message = SystemMessage(content=f"""
You are an AI assistant for Acme Operations, helping internal staff
manage customer accounts and support issues.

Current user role: {state['user_role']}
Current user: {state['username']}

You have access to these tools:
- get_customer_profile: Look up a customer by name
- get_open_issues: Get open issues for a customer
- get_issue_history: Get history for a specific issue
- create_next_action: Create next action (admin only)
- update_issue_status: Update issue status (support_user/admin only)

Always:
1. First get the customer profile to get the customer_id
2. Then get their open issues using the customer_id
3. Provide clear structured responses
4. Respect role-based access - inform user if they lack permission

Important: You are handling sensitive business data.
Do not expose internal system details in your responses.
""")

    messages = [system_message] + state["messages"]

    try:
        response = llm_with_tools.invoke(messages)
        duration = (time.time() - start) * 1000
        log_llm_call(
            model="llama-3.3-70b-versatile",
            prompt_tokens=0,
            response_tokens=0,
            duration_ms=duration,
            success=True
        )
        logger.info(f"Agent LLM call successful | duration={duration:.2f}ms")
        return {"messages": [response]}
    except Exception as e:
        duration = (time.time() - start) * 1000
        log_llm_call(
            model="llama-3.3-70b-versatile",
            prompt_tokens=0,
            response_tokens=0,
            duration_ms=duration,
            success=False,
            error=str(e)
        )
        logger.error(f"Agent LLM call failed: {e}")
        raise


# ── Router ────────────────────────────────────────────────────────
def should_continue(state: dict) -> str:  # type: ignore
    last_message = state["messages"][-1]
    if hasattr(last_message, "tool_calls") and last_message.tool_calls:
        return "tools"
    return END


# ── Build the graph ───────────────────────────────────────────────
def build_agent(user_role: str = "sales_user", username: str = "unknown") -> Any:
    tools = make_tools(user_role)
    llm = get_llm()
    llm_with_tools = llm.bind_tools(tools)

    graph: StateGraph = StateGraph(AgentState)

    graph.add_node(
        "agent",
        lambda state: agent_node(state, llm_with_tools)  # type: ignore
    )
    graph.add_node("tools", ToolNode(tools))

    graph.set_entry_point("agent")

    graph.add_conditional_edges(
        "agent",
        should_continue,
        {"tools": "tools", END: END}
    )
    graph.add_edge("tools", "agent")

    return graph.compile()


async def run_agent(
    query: str,
    user_role: str = "sales_user",
    username: str = "unknown"
) -> str:
    start = time.time()
    logger.info(
        f"Agent query | user={username} | role={user_role} | query={query[:50]}"
    )

    try:
        agent = build_agent(user_role, username)
        initial_state: AgentState = {
            "messages": [HumanMessage(content=query)],
            "user_role": user_role,
            "username": username
        }
        result = await agent.ainvoke(initial_state)  # type: ignore
        final_message = result["messages"][-1]

        # Count how many tool calls were made
        tools_called = [
            m.name for m in result["messages"]
            if hasattr(m, "name") and m.name is not None
        ]

        duration = (time.time() - start) * 1000
        log_agent_event(
            event_type="agent_completed",
            username=username,
            user_role=user_role,
            query_preview=query,
            duration_ms=duration,
            success=True,
            tools_called=tools_called
        )

        if hasattr(final_message, "content"):
            return final_message.content
        return str(final_message)

    except Exception as e:
        duration = (time.time() - start) * 1000
        log_agent_event(
            event_type="agent_failed",
            username=username,
            user_role=user_role,
            query_preview=query,
            duration_ms=duration,
            success=False,
            error=str(e)
        )
        raise