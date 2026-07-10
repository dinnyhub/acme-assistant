from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
import time

from app.logger import get_logger
from app.metrics import log_api_request, log_error, get_metrics_summary

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

@app.get("/")
async def root():
    logger.info("Root endpoint called")
    return {
        "message": "Acme Operations Assistant API",
        "version": "1.0.0",
        "status": "running"
    }

@app.get("/health")
async def health():
    return {"status": "healthy"}

@app.get("/metrics")
async def metrics():
    """
    Power BI connects to this endpoint to get all monitoring data.
    Returns real-time metrics for API requests, LLM calls, 
    tool calls, MCP calls and errors.
    """
    return get_metrics_summary()