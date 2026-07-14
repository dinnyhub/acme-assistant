import streamlit as st
import requests
import pandas as pd
import time
from datetime import datetime

API = "http://localhost:8000"

st.set_page_config(
    page_title="Acme Assistant — Developer Dashboard",
    page_icon="📊",
    layout="wide"
)

st.markdown("""
    <style>
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}
    [data-testid="stMetricValue"] {
        font-size: 1.8rem !important;
        font-weight: 700 !important;
    }
    [data-testid="stMetricLabel"] {
        font-size: 0.85rem !important;
    }
    </style>
""", unsafe_allow_html=True)


def fetch_metrics() -> dict:
    try:
        resp = requests.get(f"{API}/metrics", timeout=5)
        if resp.status_code == 200:
            return resp.json()
        return {}
    except Exception:
        return {}


# ── Header ─────────────────────────────────────────────────────────
h1, h2 = st.columns([5, 1])
with h1:
    st.title("Acme Assistant — Developer Dashboard")
    st.caption(f"Last updated: {datetime.now().strftime('%H:%M:%S')} — Auto refreshes every 30s")
with h2:
    st.write("")
    if st.button("🔄 Refresh"):
        st.rerun()

data = fetch_metrics()

if not data:
    st.error("Cannot connect to API at http://localhost:8000 — make sure the server is running")
    st.stop()

s = data.get("summary", {})
raw = data.get("raw", {})

total_api = s.get("total_api_requests", 0)
avg_api_lat = s.get("avg_api_latency_ms", 0)
success_api = s.get("successful_api_requests", 0)
failed_api = s.get("failed_api_requests", 0)
total_llm = s.get("total_llm_calls", 0)
avg_llm_lat = s.get("avg_llm_latency_ms", 0)
total_tools = s.get("total_tool_calls", 0)
success_tools = s.get("successful_tool_calls", 0)
total_errors = s.get("total_errors", 0)
total_agent = data.get("total_agent_calls", 0)
success_agent = data.get("successful_agent_calls", 0)
total_security = data.get("total_auth_events", 0)
pending_approvals = s.get("pending_approvals", 0)
total_db = data.get("total_database_events", 0)
total_mcp = s.get("total_mcp_calls", 0)
tool_success_rate = round(success_tools * 100 / total_tools) if total_tools > 0 else 0
api_success_rate = round(success_api * 100 / total_api) if total_api > 0 else 0

# ── KPI Row 1 ──────────────────────────────────────────────────────
st.subheader("System Overview")
r1c1, r1c2, r1c3, r1c4 = st.columns(4)

with r1c1:
    st.metric("API Requests", total_api, f"Avg {avg_api_lat}ms · {api_success_rate}% success")
with r1c2:
    st.metric("LLM Calls", total_llm, f"Avg {avg_llm_lat}ms")
with r1c3:
    st.metric("Tool Calls", total_tools, f"{tool_success_rate}% success")
with r1c4:
    st.metric("Agent Calls", total_agent, f"{success_agent} successful")

# ── KPI Row 2 ──────────────────────────────────────────────────────
r2c1, r2c2, r2c3, r2c4 = st.columns(4)

with r2c1:
    st.metric("MCP Calls", total_mcp)
with r2c2:
    st.metric("DB Queries", total_db)
with r2c3:
    st.metric("Errors", total_errors, delta_color="inverse")
with r2c4:
    st.metric(
        "Security Events", total_security,
        f"{pending_approvals} pending",
        delta_color="inverse" if pending_approvals > 0 else "normal"
    )

st.divider()

# ── Horizontal Bar Charts ──────────────────────────────────────────
col_left, col_right = st.columns(2)

with col_left:
    st.subheader("Tool Call Breakdown")
    tool_breakdown = data.get("tool_call_breakdown", {})
    if tool_breakdown:
        df_tools = pd.DataFrame(
            list(tool_breakdown.items()),
            columns=["Tool", "Calls"]
        ).sort_values("Calls", ascending=True)
        st.bar_chart(df_tools.set_index("Tool"), horizontal=True, height=280)
    else:
        st.info("No tool calls recorded yet")

with col_right:
    st.subheader("API Endpoint Breakdown")
    endpoint_breakdown = data.get("api_endpoint_breakdown", {})
    if endpoint_breakdown:
        df_endpoints = pd.DataFrame(
            list(endpoint_breakdown.items()),
            columns=["Endpoint", "Requests"]
        ).sort_values("Requests", ascending=True)
        st.bar_chart(df_endpoints.set_index("Endpoint"), horizontal=True, height=280)
    else:
        st.info("No API requests recorded yet")

st.divider()

# ── Success Rate Progress Bars ─────────────────────────────────────
st.subheader("Success Rates")
p1, p2, p3 = st.columns(3)

with p1:
    st.markdown("**API Requests**")
    st.progress(api_success_rate / 100, text=f"{api_success_rate}% successful ({success_api}/{total_api})")

with p2:
    st.markdown("**Tool Calls**")
    st.progress(tool_success_rate / 100, text=f"{tool_success_rate}% successful ({success_tools}/{total_tools})")

with p3:
    agent_rate = round(success_agent * 100 / total_agent) if total_agent > 0 else 0
    st.markdown("**Agent Calls**")
    st.progress(agent_rate / 100, text=f"{agent_rate}% successful ({success_agent}/{total_agent})")

st.divider()

# ── LLM Calls Table ────────────────────────────────────────────────
st.subheader("LLM Call Performance")
llm_calls = raw.get("llm_calls", [])
if llm_calls:
    df_llm = pd.DataFrame(llm_calls[-15:][::-1])
    df_llm["time"] = pd.to_datetime(df_llm["timestamp"]).dt.strftime("%H:%M:%S")
    df_llm["status"] = df_llm["success"].map({True: "✅", False: "❌"})
    df_llm["latency"] = df_llm["duration_ms"].apply(lambda x: f"{x:.0f}ms")
    avg_lat = df_llm["duration_ms"].mean()
    max_lat = df_llm["duration_ms"].max()
    min_lat = df_llm["duration_ms"].min()
    m1, m2, m3 = st.columns(3)
    with m1:
        st.metric("Avg Latency", f"{avg_lat:.0f}ms")
    with m2:
        st.metric("Max Latency", f"{max_lat:.0f}ms")
    with m3:
        st.metric("Min Latency", f"{min_lat:.0f}ms")
    st.dataframe(
        df_llm[["time", "model", "latency", "status"]],
        hide_index=True,
        
    )
else:
    st.info("No LLM calls recorded yet")

st.divider()

# ── API + Tool Calls ───────────────────────────────────────────────
col_a, col_b = st.columns(2)

with col_a:
    st.subheader("Recent API Requests")
    api_requests = raw.get("api_requests", [])
    if api_requests:
        df_api = pd.DataFrame(api_requests[-10:][::-1])
        df_api["time"] = pd.to_datetime(df_api["timestamp"]).dt.strftime("%H:%M:%S")
        df_api["status"] = df_api["success"].map({True: "✅", False: "❌"})
        st.dataframe(
            df_api[["time", "method", "endpoint", "status_code", "duration_ms", "status"]],
            hide_index=True,
            
        )
    else:
        st.info("No API requests yet")

with col_b:
    st.subheader("Recent Tool Calls")
    tool_calls = raw.get("tool_calls", [])
    if tool_calls:
        df_tc = pd.DataFrame(tool_calls[-10:][::-1])
        df_tc["time"] = pd.to_datetime(df_tc["timestamp"]).dt.strftime("%H:%M:%S")
        df_tc["status"] = df_tc["success"].map({True: "✅", False: "❌"})
        st.dataframe(
            df_tc[["time", "tool_name", "duration_ms", "status"]],
            hide_index=True,
            
        )
    else:
        st.info("No tool calls yet")

st.divider()

# ── Security + Database ────────────────────────────────────────────
col_sec, col_db = st.columns(2)

with col_sec:
    st.subheader("Security Events")
    security_events = raw.get("security_events", [])
    if security_events:
        df_sec = pd.DataFrame(security_events[-10:][::-1])
        df_sec["time"] = pd.to_datetime(df_sec["timestamp"]).dt.strftime("%H:%M:%S")
        available_cols = ["time", "event_type"]
        for col in ["requested_by", "username", "outcome"]:
            if col in df_sec.columns:
                available_cols.append(col)
        st.dataframe(
            df_sec[available_cols],
            hide_index=True,
        )
    else:
        st.success("No security events — all queries are clean")

with col_db:
    st.subheader("Recent Database Queries")
    db_events = raw.get("database_events", [])
    if db_events:
        df_db = pd.DataFrame(db_events[-10:][::-1])
        df_db["time"] = pd.to_datetime(df_db["timestamp"]).dt.strftime("%H:%M:%S")
        df_db["status"] = df_db["success"].map({True: "✅", False: "❌"})
        st.dataframe(
            df_db[["time", "operation", "table", "rows_returned", "duration_ms", "status"]],
            hide_index=True,
            
        )
    else:
        st.info("No database queries yet")

st.divider()

# ── Agent + MCP ────────────────────────────────────────────────────
col_agent, col_mcp = st.columns(2)

with col_agent:
    st.subheader("Agent Events")
    agent_calls = raw.get("agent_calls", [])
    if agent_calls:
        df_agent = pd.DataFrame(agent_calls[-10:][::-1])
        df_agent["time"] = pd.to_datetime(df_agent["timestamp"]).dt.strftime("%H:%M:%S")
        df_agent["status"] = df_agent["success"].map({True: "✅", False: "❌"})
        df_agent["tools"] = df_agent["tools_called"].apply(
            lambda x: ", ".join(x) if isinstance(x, list) else str(x)
        )
        st.dataframe(
            df_agent[["time", "username", "user_role", "duration_ms", "tools", "status"]],
            hide_index=True,
            
        )
    else:
        st.info("No agent events yet")

with col_mcp:
    st.subheader("MCP Server Calls")
    mcp_calls = raw.get("mcp_calls", [])
    if mcp_calls:
        df_mcp = pd.DataFrame(mcp_calls[-10:][::-1])
        df_mcp["time"] = pd.to_datetime(df_mcp["timestamp"]).dt.strftime("%H:%M:%S")
        df_mcp["status"] = df_mcp["success"].map({True: "✅", False: "❌"})
        st.dataframe(
            df_mcp[["time", "server", "tool", "duration_ms", "status"]],
            hide_index=True,
            
        )
    else:
        st.info("No MCP calls recorded yet")

st.divider()
st.caption("Auto-refreshes every 30 seconds. Click 🔄 Refresh to update manually.")

# Auto refresh
if "last_refresh" not in st.session_state:
    st.session_state.last_refresh = time.time()
if time.time() - st.session_state.last_refresh > 30:
    st.session_state.last_refresh = time.time()
    st.rerun()