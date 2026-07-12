from fastapi import FastAPI, Request, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
import time

from app.logger import get_logger
from app.metrics import log_api_request, get_metrics_summary
from app.auth.auth import get_current_user
from app.database import get_customer_by_name
from app.api.routes import router

import os
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from app.memory import get_redis_health

load_dotenv()
logger = get_logger(__name__)

app = FastAPI(
    title="Acme Operations Assistant",
    description="Agentic AI assistant for customer support and account management",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Middleware to log every request automatically
@app.middleware("http")
async def log_requests(request: Request, call_next):
    start_time = time.time()
    response = await call_next(request)
    duration_ms = (time.time() - start_time) * 1000
    log_api_request(
        endpoint=str(request.url.path),
        method=request.method,
        status_code=response.status_code,
        duration_ms=duration_ms
    )
    return response

# Include API routes
app.include_router(router, prefix="/api")

@app.get("/", tags = ["System"], summary="Root endpoint")
async def root():
    logger.info("Root endpoint called")
    return {
        "message": "Acme Operations Assistant API",
        "version": "1.0.0",
        "status": "running"
    }

@app.get("/health", tags = ["System"], summary="Health check endpoint")
async def health():
    return {"status": "healthy",
            "redis": "connected" if get_redis_health() else "disconnected"
            }

@app.get("/metrics", tags = ["Monitoring"], summary="Get real-time metrics for API requests, LLM calls, tool calls, MCP calls and errors")
async def metrics():
    """
    Power BI connects to this endpoint to get all monitoring data.
    Returns real-time metrics for API requests, LLM calls, 
    tool calls, MCP calls and errors.
    """
    return get_metrics_summary()

@app.get("/me", tags = ["Auth"], summary="Get current user info from Keycloak token")
async def get_me(user: dict = Depends(get_current_user)):
    """
    Returns current user info from their Keycloak token.
    Any authenticated user can call this.
    """
    return {
        "username": user["username"],
        "roles": user["roles"],
        "email": user["email"]
    }

@app.get("/customers/{name}", tags=["Customers"], summary="Get customer by name")
async def get_customer(
    name: str,
    user: dict = Depends(get_current_user)
):
    """
    Get customer by name.
    All authenticated users can access this.
    """
    customer = get_customer_by_name(name)
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    return customer

app.mount("/static", StaticFiles(directory="app/static"), name="static")

@app.get("/ui", tags=["System"])
async def serve_ui():
    return FileResponse("app/static/index.html")

@app.get("/config", tags=["System"])
async def get_config():
    return {
        "client_secret": os.getenv("KEYCLOAK_CLIENT_SECRET", "acme-secret")
    }

@app.post("/login", tags=["Auth"])
async def login(request: Request):
    """
    Proxy login endpoint — browser calls this instead of Keycloak directly.
    Avoids CORS issues with Keycloak.
    """
    import httpx
    body = await request.form()
    username = body.get("username")
    password = body.get("password")
    
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{os.getenv('KEYCLOAK_URL')}/realms/{os.getenv('KEYCLOAK_REALM')}/protocol/openid-connect/token",
            data={
                "grant_type": "password",
                "client_id": os.getenv("KEYCLOAK_CLIENT_ID"),
                "client_secret": os.getenv("KEYCLOAK_CLIENT_SECRET"),
                "username": username,
                "password": password
            }
        )
    
    if resp.status_code == 200:
        return resp.json()
    else:
        from fastapi import HTTPException
        raise HTTPException(status_code=401, detail="Invalid credentials")