from fastapi import FastAPI, Depends, HTTPException, status, Request
from sqlalchemy.ext.asyncio import AsyncSession
from database import init_db, get_db
import models, schemas
from auth_router import auth_router
from api_router import api_router
from client_router import client_router
from validation_router import validation_router
from analytics_router import analytics_router
from subscription_router import subscription_router
from webhook_router import webhook_router
from publisher_analytics_router import publisher_analytics_router
from stripe_connect_router import stripe_connect_router

from prometheus_client import generate_latest, Counter, Histogram
from starlette.responses import PlainTextResponse

import logging
import json
import uuid

# Configure JSON logging
class JsonFormatter(logging.Formatter):
    def format(self, record):
        log_record = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "message": record.getMessage(),
            "service": "management-api",
            "request_id": getattr(record, 'request_id', None),
            "endpoint": getattr(record, 'endpoint', None),
            "method": getattr(record, 'method', None),
            "status_code": getattr(record, 'status_code', None),
            "traceback": self.formatException(record.exc_info) if record.exc_info else None,
        }
        return json.dumps(log_record)

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
handler = logging.StreamHandler()
handler.setFormatter(JsonFormatter())
logger.addHandler(handler)

app = FastAPI()

# Prometheus Metrics
REQUEST_COUNT = Counter('http_requests_total', 'Total HTTP Requests', ['method', 'endpoint', 'status_code'])
REQUEST_LATENCY = Histogram('http_request_duration_seconds', 'HTTP Request Latency', ['method', 'endpoint'])

@app.on_event("startup")
async def on_startup():
    await init_db()

app.include_router(auth_router, prefix="/auth", tags=["auth"])
app.include_router(api_router, tags=["apis"])
app.include_router(client_router, tags=["clients"])
app.include_router(validation_router, prefix="/validate", tags=["validation"])
app.include_router(analytics_router, tags=["analytics"])
app.include_router(subscription_router, tags=["subscriptions"])
app.include_router(webhook_router, prefix="/webhooks", tags=["webhooks"])
app.include_router(publisher_analytics_router, tags=["publisher-analytics"])
app.include_router(stripe_connect_router, prefix="/stripe-connect", tags=["stripe-connect"])

@app.middleware("http")
async def add_prometheus_metrics_and_logging(request: Request, call_next):
    request_id = str(uuid.uuid4())
    request.state.request_id = request_id # Store request_id in request state

    method = request.method
    endpoint = request.url.path
    
    extra_log_data = {
        "request_id": request_id,
        "method": method,
        "endpoint": endpoint
    }

    logger.info(f"Incoming request: {method} {endpoint}", extra=extra_log_data)

    with REQUEST_LATENCY.labels(method=method, endpoint=endpoint).time():
        response = await call_next(request)
    
    REQUEST_COUNT.labels(method=method, endpoint=endpoint, status_code=response.status_code).inc()
    extra_log_data["status_code"] = response.status_code
    logger.info(f"Outgoing response: {method} {endpoint} {response.status_code}", extra=extra_log_data)

    return response

@app.get("/")
async def root():
    logger.info("Root endpoint accessed.", extra={"request_id": getattr(app.state, 'request_id', None)})
    return {"message": "Management API is running!"}

@app.get("/test-db")
async def test_db_connection(db: AsyncSession = Depends(get_db)):
    try:
        await db.execute(models.User.__table__.select().limit(1))
        logger.info("Database connection successful.", extra={"request_id": getattr(app.state, 'request_id', None)})
        return {"message": "Database connection successful!"}
    except Exception as e:
        logger.error(f"Database connection failed: {e}", exc_info=True, extra={"request_id": getattr(app.state, 'request_id', None)})
        raise HTTPException(status_code=500, detail=f"Database connection failed: {e}")

@app.get("/metrics", response_class=PlainTextResponse)
async def metrics():
    return PlainTextResponse(generate_latest())
