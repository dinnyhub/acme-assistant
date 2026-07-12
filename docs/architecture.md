# Architecture Diagram

See README.md for the full Mermaid architecture diagram.

## Component Summary

| Component | Technology | Purpose |
|---|---|---|
| Chat UI | HTML/CSS/JS | User interface served by FastAPI |
| API Layer | FastAPI + Python | Authentication, routing, observability |
| Agent | LangGraph | Dynamic tool selection and reasoning |
| LLM | Groq llama-3.3-70b-versatile | Language model for agent reasoning |
| MCP Server | Custom Python | Standardised tool definitions |
| Escalation Skill | Python workflow | Structured customer risk assessment |
| Auth | Keycloak 24 | JWT authentication and RBAC |
| Database | PostgreSQL 15 | Customer and issue data |
| Memory | Redis 7 | Conversation history |
| Observability | FastAPI /metrics | Power BI and Streamlit dashboard |
| Containerisation | Docker Compose | Full stack orchestration |
