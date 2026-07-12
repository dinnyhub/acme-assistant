# Acme Operations Assistant

An agentic AI assistant for Acme Operations — built for the EY Future Development Engineer case study. The system enables internal staff to query customer data, manage support issues, and receive AI-powered escalation summaries through a secure, role-based conversational interface.

---

## Quick Start

```bash
# Clone the repository
git clone https://github.com/dinnyhub/acme-assistant.git
cd acme-assistant

# Add your API key to .env
cp .env.example .env
# Edit .env and add your GROQ_API_KEY

# Start everything
docker compose up

# Open the UI
open http://localhost:8000/ui

# Open the developer dashboard (separate terminal)
streamlit run app/dashboard.py --server.port 8502
open http://localhost:8502
```

---

## Architecture Overview

The system is composed of four layers:

**1. User Interface**
HTML/CSS/JS chat UI served by FastAPI at `/ui`. ChatGPT-style interface with fixed header, scrollable chat, and fixed input. Security alerts appear inline when sensitive data is detected.

**2. API Layer — FastAPI**
Handles authentication (Keycloak JWT), RBAC enforcement, sensitive data detection, human-in-the-loop approval, data sanitisation, and observability. All requests are logged and tracked.

**3. Agent Layer — LangGraph**
The LangGraph agent dynamically selects from 6 tools based on the user query. The MCP server exposes the same tools in a standardised format. The Escalation Skill provides a structured multi-step workflow for customer risk assessment.

**4. Infrastructure — Docker Compose**
PostgreSQL 15 (data), Redis 7 (conversation memory), Keycloak 24 (authentication). All services start with `docker compose up`. Keycloak realm auto-imports from `infra/keycloak/acme-realm.json`.

---

## Components

### Agent and Tools
The LangGraph agent dynamically selects tools based on user queries. It does not hard-code answers — it reasons about which tools to invoke and chains them as needed.

**6 tools:**
- `get_customer_profile` — retrieves customer by name
- `get_open_issues` — retrieves open issues ordered by priority
- `get_issue_history` — retrieves issue update history
- `create_next_action` — creates next action (admin only)
- `update_issue_status` — updates issue status (support/admin only)
- `escalation_summary` — invokes the Customer Escalation Summary Skill

### MCP Server
A custom Python MCP (Model Context Protocol) server exposes the same tools in a standardised, reusable format. This separates tool definitions from agent logic — tools can be reused across different agents or called directly via the `/api/mcp/call` endpoint.

### Skills
The Customer Escalation Summary Skill is a structured, repeatable workflow distinct from a one-off prompt call. It:
1. Fetches customer data from PostgreSQL
2. Calculates base risk level deterministically from issue priorities
3. Identifies missing information without LLM involvement
4. Calls the LLM only for the executive summary and recommendation
5. Returns a structured `EscalationSummary` object with four outputs: executive summary, risk level (Low/Medium/High/Critical), recommended next action, and missing information

### Authentication — Keycloak
Keycloak is a hard requirement. Every request must present a valid JWT bearer token. Three roles are enforced:
- `sales_user` — read-only access to customer and issue data
- `support_user` — read and update access for issues
- `admin` — full access including creating next actions

The Keycloak realm is exported as `infra/keycloak/acme-realm.json` and auto-imported on `docker compose up` — no manual Keycloak setup is required.

### Security — Human in the Loop
Before any query reaches the LLM, the system scans for sensitive data patterns (email, phone, credit card, bank account, NI number, passport, sort code, IP address).

If detected:
1. The request is held immediately and an approval ID is returned
2. The user sees a security alert in the UI
3. The user can approve (Continue) or cancel (Edit Query)
4. If approved — the query is logged with who approved it and when
5. The query is sanitised (sensitive data redacted) before reaching the LLM

This satisfies FCA human oversight requirements and GDPR data minimisation principles.

### Redis Memory
Conversation history is stored in Redis with a 1-hour TTL. The agent receives the last 2 exchanges as context on each query, enabling follow-up questions without re-fetching data.

### Observability
Two-layer observability:

**1. Daily rotating log files** (`logs/acme_YYYY-MM-DD.log`)
- Auto-delete after 7 days
- Every API request, LLM call, tool call, auth event, security event logged

**2. Metrics endpoint** (`GET /metrics`)
- Real-time JSON metrics for all system components
- Power BI connects to this endpoint for production dashboards
- Streamlit developer dashboard (`http://localhost:8502`) consumes the same endpoint for local development

---

## API Endpoints

| Tag | Endpoint | Description |
|---|---|---|
| System | `GET /` | Root |
| System | `GET /health` | Health check with Redis status |
| System | `GET /ui` | Chat UI |
| Auth | `POST /login` | Keycloak proxy login |
| Auth | `GET /me` | Current user info |
| Monitoring | `GET /metrics` | Power BI metrics |
| Agent | `POST /api/query` | Main agent endpoint |
| Customers | `GET /api/customers` | List all customers |
| Customers | `GET /api/customers/{id}/issues` | Get customer issues |
| Issues | `GET /api/issues/{id}/history` | Issue history |
| Issues | `POST /api/issues/{id}/next-action` | Create next action (admin) |
| Issues | `PUT /api/issues/{id}/status` | Update status (support/admin) |
| MCP Server | `GET /api/mcp/tools` | List MCP tools |
| MCP Server | `POST /api/mcp/call` | Call MCP tool |
| Skills | `POST /api/skills/escalation/{name}` | Run escalation skill |
| Security | `GET /api/security/pending-approvals` | Pending approvals (admin) |
| Security | `POST /api/security/approve/{id}` | Approve query (admin) |
| Security | `POST /api/security/self-approve/{id}` | User self-approve |
| Security | `POST /api/security/reject/{id}` | Reject query (admin) |

Full interactive documentation: `http://localhost:8000/docs`

---

## Test Users

| Username | Password | Role | Access |
|---|---|---|---|
| alice | alice123 | sales_user | Read only |
| bob | bob123 | support_user | Read and update |
| carol | carol123 | admin | Full access |

---

## Evaluation

10 test questions — 5 pass cases and 5 fail cases:

```bash
python eval/evaluation.py
```

Results saved to `eval/results.json`.

**Pass cases:** customer profile, open issues, issue history, status update, next action creation

**Fail cases:** RBAC denial (sales_user create), RBAC denial (sales_user update), RBAC denial (support_user create), customer not found, invalid status value

**Result: 10/10 — 100% pass rate**

---

## Trade-offs and Decisions

**LLM: Groq llama-3.3-70b-versatile**
Free tier with 100K daily tokens. In production this would use Azure OpenAI Service (GPT-4o) to keep all data within the Microsoft compliance boundary — satisfying FCA and GDPR requirements. The architecture is identical — only the LLM provider changes.

**Keycloak: dev-file mode**
Using `KC_DB: dev-file` for simplicity. In production Keycloak would use PostgreSQL as its database for persistence and high availability.

**Redis: in-memory metrics**
Metrics are stored in application memory and reset on restart. In production metrics would be persisted to a time-series database (InfluxDB or Azure Monitor).

**MCP server: custom Python class**
Implemented as a Python class rather than a separate MCP process. In production the MCP server would run as a separate containerised service, enabling independent scaling and versioning.

**Sensitive data: regex-based detection**
Pattern matching covers common UK financial data types. In production this would use a dedicated PII detection service (Azure AI Content Safety or AWS Comprehend) with ML-based detection.

---

## AI Usage

AI tools were used during development of this project:

- **GitHub Copilot** — inline code completion and refactoring during development
- **Groq llama-3.3-70b-versatile** — production LLM powering the agent reasoning, tool calling, and response generation
- **Groq llama-3.1-8b-instant** — evaluation runs, chosen for higher daily token quota (500K vs 100K TPD)

All code was reviewed, tested, and understood before inclusion. Architecture decisions, system design, and trade-off analysis are my own.

---

## Project Structure

**app/** — Application code
- `main.py` — FastAPI entry point, middleware, routes
- `logger.py` — Daily rotating log files with 7-day auto-delete
- `metrics.py` — Real-time metrics tracking for all system events
- `memory.py` — Redis conversation memory with 1-hour TTL
- `database.py` — PostgreSQL connection and all query functions
- `dashboard.py` — Streamlit developer monitoring dashboard

**app/agent/** — LangGraph agent
- `agent.py` — LangGraph agent with tool calling and Redis memory
- `tools.py` — 6 agent tools with RBAC enforcement

**app/api/** — API routes
- `routes.py` — All FastAPI routes with Swagger tags

**app/auth/** — Authentication
- `auth.py` — Keycloak JWT validation and RBAC dependencies

**app/mcp_server/** — MCP Server
- `server.py` — Custom MCP server exposing 5 tools with standardised schemas

**app/skills/** — Reusable skills
- `escalation_skill.py` — Customer Escalation Summary Skill

**app/security/** — Security layer
- `data_sanitiser.py` — Sensitive data detection and human-in-the-loop approval

**app/static/** — Frontend
- `index.html` — ChatGPT-style chat UI

**infra/** — Infrastructure configuration
- `postgres/init.sql` — Database schema and seed data
- `keycloak/acme-realm.json` — Keycloak realm export (auto-imported on startup)

**eval/** — Evaluation
- `evaluation.py` — 10 test questions (5 pass, 5 fail)
- `results.json` — Latest evaluation results

**Root files**
- `docker-compose.yml` — Full stack orchestration
- `Dockerfile` — Application container
- `requirements.txt` — Python dependencies
- `README.md` — This file