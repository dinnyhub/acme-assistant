# Acme Operations Assistant

An agentic AI assistant for Acme Operations — built for the EY Applied AI Engineer technical assessment. The system enables internal staff to query customer data, manage support issues, and receive AI-powered escalation summaries through a secure, role-based conversational interface.

---

## Quick Start

```bash
# Clone the repository
git clone https://github.com/dinnyhub/acme-assistant.git
cd acme-assistant

# Copy the example env file and add your API keys
cp .env.example .env
# Edit .env and add:
# - GROQ_API_KEY (get free at console.groq.com)
# - KEYCLOAK_CLIENT_SECRET (generated after first docker compose up)

# Start everything
docker compose up

# Open the UI
open http://localhost:8000/ui

# Open the developer dashboard (separate terminal)
streamlit run app/dashboard.py --server.port 8502
open http://localhost:8502
```

### Environment Variables

| Variable | Description | Example |
|---|---|---|
| `GROQ_API_KEY` | Groq API key — get free at console.groq.com | `gsk_...` |
| `GROQ_MODEL` | LLM model to use | `llama-3.3-70b-versatile` |
| `DATABASE_URL` | PostgreSQL connection string | `postgresql://acme_user:acme_pass@localhost:5432/acme_db` |
| `REDIS_URL` | Redis connection string | `redis://localhost:6379` |
| `KEYCLOAK_URL` | Keycloak URL | `http://localhost:8080` |
| `KEYCLOAK_REALM` | Keycloak realm name | `acme` |
| `KEYCLOAK_CLIENT_ID` | Keycloak client ID | `acme-app` |
| `KEYCLOAK_CLIENT_SECRET` | Keycloak client secret — copy from Keycloak admin after first run | `abc123...` |
| `SECRET_KEY` | App secret key — any random string | `supersecretkey123` |

---

## Architecture Overview

```mermaid
graph TD
    User["👤 User Browser\nHTML Chat UI"]
    Dashboard["📊 Developer Dashboard\nStreamlit :8502"]

    User -->|HTTPS + JWT| FastAPI
    Dashboard -->|GET /metrics| FastAPI

    subgraph FastAPI ["⚡ FastAPI Application :8000"]
        Auth["🔐 Keycloak JWT Auth\nRBAC Enforcement"]
        Security["🛡️ Security Layer\nSensitive Data Detection\nHuman-in-the-Loop"]
        Routes["📡 API Routes\n/api/query\n/api/mcp\n/api/skills"]
        Metrics["📈 Metrics\n/metrics endpoint\nPower BI ready"]
    end

    Auth --> Security
    Security --> Routes
    Routes --> Agent

    subgraph Agent ["🤖 LangGraph Agent"]
        LLM["Groq llama-3.3-70b\nLLM Reasoning"]
        Tools["6 Tools\nget_customer_profile\nget_open_issues\nget_issue_history\ncreate_next_action\nupdate_issue_status\nescalation_summary"]
        MCP["MCP Server\nStandardised\nTool Definitions"]
        Skill["Customer Escalation\nSummary Skill\nRisk Assessment"]
    end

    LLM --> Tools
    Tools --> MCP
    Tools --> Skill

    subgraph Infra ["🐳 Docker Compose Infrastructure"]
        PG["PostgreSQL 15\n5 tables\nSeed data"]
        Redis["Redis 7\nConversation Memory\n1hr TTL"]
        KC["Keycloak 24\n3 Roles\n3 Users\nAuto-import"]
    end

    MCP --> PG
    Agent --> Redis
    FastAPI --> KC
```

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

The MCP server is implemented as a Python class within the application rather than a separate container. This is a deliberate trade-off — in production it would run as a separate containerised service for independent scaling and versioning.

**Why MCP is useful here:** Without MCP, tool definitions are tightly coupled to the agent. With MCP, the same tool definitions can be consumed by any agent or called directly via API — making the system more modular and testable.

### Skills
The Customer Escalation Summary Skill is a structured, repeatable workflow distinct from a one-off prompt call. It:

1. Fetches customer data from PostgreSQL
2. Calculates base risk level **deterministically** from issue priorities — no LLM needed for this step
3. Identifies missing information without LLM involvement
4. Calls the LLM only for the executive summary and recommendation
5. Returns a structured `EscalationSummary` object with four outputs: executive summary, risk level (Low/Medium/High/Critical), recommended next action, and missing information identification

### Authentication — Keycloak
Keycloak is a hard requirement. Every request must present a valid JWT bearer token. Three roles are enforced:

- `sales_user` — read-only access to customer and issue data
- `support_user` — read and update access for issues
- `admin` — full access including creating next actions

The Keycloak realm is exported as `infra/keycloak/acme-realm.json` and auto-imported on `docker compose up` — no manual Keycloak setup is required.

### Security — Human in the Loop
Before any query reaches the LLM, the system scans for sensitive data patterns (email, phone, credit card, bank account, NI number, passport, sort code, IP address).

If detected:
1. The request returns a 403 immediately with an approval ID
2. The user sees a security alert in the UI
3. The user can approve (Continue) or cancel (Edit Query)
4. If approved — the query is logged with who approved it and when
5. The query proceeds with the original data — the user has accepted responsibility
6. All approval events are logged to the audit trail and metrics

This satisfies FCA human oversight requirements and GDPR data minimisation principles.

### Redis Memory
Conversation history is stored in Redis with a 1-hour TTL. The agent receives the last 4 messages as context on each query, enabling follow-up questions without re-fetching data.

**Redis vs PostgreSQL rationale:** Redis stores short-term conversation memory because it is optimised for fast key-value reads with automatic expiry — no cleanup jobs needed. PostgreSQL stores durable structured data (customers, issues, next actions) that must survive restarts and support complex queries. The two stores serve fundamentally different purposes — Redis for ephemeral session state, PostgreSQL for business data.

### Observability
Two-layer observability:

**1. Daily rotating log files** (`logs/acme_YYYY-MM-DD.log`)
- Auto-delete after 7 days
- Every API request, LLM call, tool call, auth event, security event logged with timestamp
- Full audit trail for compliance — approval ID, requester, approver, timestamp

**2. Metrics endpoint** (`GET /metrics`)
- Real-time JSON metrics for all system components
- Power BI connects to this endpoint for production dashboards
- Streamlit developer dashboard (`http://localhost:8502`) consumes the same endpoint for local development
- Tracks: API requests, LLM calls, tool calls, agent events, MCP calls, database queries, auth events, security events

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
| MCP Server | `POST /api/mcp/call` | Call MCP tool directly |
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

**Pass cases:** customer profile retrieval, open issues retrieval, issue history, status update by support_user, next action creation by admin

**Fail cases:** RBAC denial (sales_user create next action), RBAC denial (sales_user update status), RBAC denial (support_user create next action), customer not found, invalid status value

**Result: 10/10 — 100% pass rate**

---

## Trade-offs and Decisions

**LLM: Groq llama-3.3-70b-versatile**
Free tier with 100K daily tokens. In production this would use Azure OpenAI Service (GPT-4o) to keep all data within the Microsoft compliance boundary — satisfying FCA and GDPR requirements. The architecture is identical — only the LLM provider changes.

**MCP server: integrated vs separate container**
The MCP server runs as a Python class within the application rather than a separate container. This simplifies the Docker Compose setup and reduces operational complexity for a prototype. In production it would be a separate containerised service for independent scaling and versioning.

**Keycloak: dev-file mode**
Using `KC_DB: dev-file` for simplicity. The realm is exported as JSON and auto-imported on startup so no manual setup is needed. In production Keycloak would use PostgreSQL as its database for persistence and high availability.

**Redis: in-memory metrics**
Metrics are stored in application memory and reset on restart. In production metrics would be persisted to a time-series database (InfluxDB or Azure Monitor) and the Redis metrics store would be replaced with a proper observability platform.

**Sensitive data: regex-based detection**
Pattern matching covers common UK financial data types (email, phone, credit card, NI number, bank account, sort code, passport, IP address). In production this would use a dedicated PII detection service (Azure AI Content Safety or AWS Comprehend) with ML-based detection for higher accuracy.

---

## AI Usage

AI tools were used during development of this project:

- **GitHub Copilot** — inline code completion and refactoring during development
- **Groq llama-3.3-70b-versatile** — primary production LLM powering the agent reasoning, tool calling, and response generation (100K TPD free tier)
- **Groq qwen/qwen3-32b** — fallback model when daily token limit is reached (500K TPD) — change `GROQ_MODEL` in `.env` to switch
- **Groq llama-3.1-8b-instant** — evaluation runs only, chosen for highest daily token quota (500K TPD)

**What was delegated to AI tools:** Code scaffolding, boilerplate generation, debugging suggestions, and documentation drafting were delegated to AI tools. This freed time for architecture decisions, system integration, and security design.

**How code was reviewed and validated:** Every AI-generated function was read line by line, tested against real data, and validated with pyflakes for unused imports and type errors. Several errors were caught and corrected — including incorrect LangGraph API usage, wrong regex patterns for sensitive data detection, and session contamination bugs in the evaluation framework.

**How errors and hallucinations were identified:** Running the application end-to-end against real data immediately exposed incorrect outputs. Type errors were caught by Pylance. Logic errors (such as the agent entering infinite loops when conversation history was passed incorrectly) were identified through log analysis.

**What I would not trust AI to do without human oversight:** Security-critical decisions (RBAC logic, data sanitisation rules, approval flow design), architecture trade-offs, and anything requiring business context judgment. AI tools are strong at implementation — weak at knowing what to build and why. In a client engagement I would always design the security architecture myself and use AI only for implementation of well-specified components.

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
- `.env.example` — Environment variable template
- `README.md` — This file