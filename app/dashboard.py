import streamlit as st
import requests
import time

API = "http://localhost:8000"

st.set_page_config(
    page_title="Acme - Developer Dashboard",
    page_icon="📊",
    layout="wide"
)

st.markdown("""
    <style>
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}
    </style>
""", unsafe_allow_html=True)

st.title("Acme Assistant — Developer Dashboard")
st.caption("Real-time monitoring of all system components")

if st.button("Refresh"):
    st.rerun()

try:
    resp = requests.get(f"{API}/metrics")
    data = resp.json()
    s = data["summary"]

    # ── Summary metrics ───────────────────────────────────────────
    st.subheader("System Overview")
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric(
            "API Requests",
            s["total_api_requests"],
            f"Avg {s['avg_api_latency_ms']}ms"
        )
    with col2:
        st.metric(
            "LLM Calls",
            s["total_llm_calls"],
            f"Avg {s['avg_llm_latency_ms']}ms"
        )
    with col3:
        st.metric(
            "Tool Calls",
            s["total_tool_calls"],
            f"{s['successful_tool_calls']} successful"
        )
    with col4:
        st.metric(
            "Errors",
            s["total_errors"],
            delta_color="inverse"
        )

    col5, col6, col7, col8 = st.columns(4)
    with col5:
        st.metric("Agent Calls", s.get("total_agent_calls", 0))
    with col6:
        st.metric("DB Queries", s.get("total_database_events", 0))
    with col7:
        st.metric("Auth Events", s.get("total_auth_events", 0))
    with col8:
        st.metric(
            "Security Events",
            s.get("total_security_events", 0),
            f"{s.get('pending_approvals', 0)} pending"
        )

    st.divider()

    # ── Breakdowns ────────────────────────────────────────────────
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("Tool Call Breakdown")
        breakdown = data.get("tool_call_breakdown", {})
        if breakdown:
            for tool, count in sorted(
                breakdown.items(), key=lambda x: x[1], reverse=True
            ):
                st.progress(
                    count / max(breakdown.values()),
                    text=f"`{tool}` — {count} calls"
                )
        else:
            st.write("No tool calls yet")

    with col2:
        st.subheader("API Endpoint Breakdown")
        endpoints = data.get("api_endpoint_breakdown", {})
        if endpoints:
            for endpoint, count in sorted(
                endpoints.items(), key=lambda x: x[1], reverse=True
            ):
                st.progress(
                    count / max(endpoints.values()),
                    text=f"`{endpoint}` — {count} requests"
                )
        else:
            st.write("No API calls yet")

    st.divider()

    raw = data.get("raw", {})

    # ── Recent API requests ───────────────────────────────────────
    st.subheader("Recent API Requests")
    api_requests = raw.get("api_requests", [])
    if api_requests:
        for req in reversed(api_requests[-10:]):
            status_icon = "✅" if req["success"] else "❌"
            st.write(
                f"{status_icon} `{req['method']} {req['endpoint']}` | "
                f"Status: {req['status_code']} | "
                f"Duration: {req['duration_ms']}ms | "
                f"{req['timestamp'][:19]}"
            )
    else:
        st.write("No API requests yet")

    st.divider()

    # ── Recent LLM calls ──────────────────────────────────────────
    st.subheader("Recent LLM Calls")
    llm_calls = raw.get("llm_calls", [])
    if llm_calls:
        for call in reversed(llm_calls[-10:]):
            status_icon = "✅" if call["success"] else "❌"
            st.write(
                f"{status_icon} Model: `{call['model']}` | "
                f"Duration: {call['duration_ms']}ms | "
                f"Tokens: {call['total_tokens']} | "
                f"{call['timestamp'][:19]}"
            )
    else:
        st.write("No LLM calls yet")

    st.divider()

    # ── Recent tool calls ─────────────────────────────────────────
    st.subheader("Recent Tool Calls")
    tool_calls = raw.get("tool_calls", [])
    if tool_calls:
        for call in reversed(tool_calls[-10:]):
            status_icon = "✅" if call["success"] else "❌"
            st.write(
                f"{status_icon} Tool: `{call['tool_name']}` | "
                f"Duration: {call['duration_ms']}ms | "
                f"{call['timestamp'][:19]}"
            )
    else:
        st.write("No tool calls yet")

    st.divider()

    # ── Security events ───────────────────────────────────────────
    st.subheader("Security Events")
    security_events = raw.get("security_events", [])
    if security_events:
        for event in reversed(security_events[-10:]):
            event_type = event.get("event_type", "unknown")
            icon = (
                "🔴" if "timeout" in event_type or "rejected" in event_type
                else "🟡" if "requested" in event_type or "pending" in event_type
                else "🟢"
            )
            st.write(
                f"{icon} `{event_type}` | "
                f"User: {event.get('requested_by', event.get('username', 'unknown'))} | "
                f"Types: {event.get('sensitive_data_types', [])} | "
                f"{event['timestamp'][:19]}"
            )
    else:
        st.write("No security events yet")

    st.divider()

    # ── Database events ───────────────────────────────────────────
    st.subheader("Database Events")
    db_events = raw.get("database_events", [])
    if db_events:
        for event in reversed(db_events[-10:]):
            status_icon = "✅" if event["success"] else "❌"
            st.write(
                f"{status_icon} `{event['operation']}` on `{event['table']}` | "
                f"Rows: {event['rows_returned']} | "
                f"Duration: {event['duration_ms']}ms | "
                f"{event['timestamp'][:19]}"
            )
    else:
        st.write("No database events yet")

    # Auto refresh every 30 seconds
    time.sleep(0.1)

except Exception as e:
    st.error(f"Cannot connect to API: {e}")
    st.info("Make sure the FastAPI server is running on http://localhost:8000")