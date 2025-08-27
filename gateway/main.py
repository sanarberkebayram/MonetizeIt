from fastapi import FastAPI, Request, Response, HTTPException, status
from httpx import AsyncClient
import os
import redis.asyncio as redis
import hashlib
import json
import time
from datetime import datetime, date

from prometheus_client import generate_latest, Counter, Histogram
from starlette.responses import PlainTextResponse

import logging
import uuid

# Configure JSON logging
class JsonFormatter(logging.Formatter):
    def format(self, record):
        log_record = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "message": record.getMessage(),
            "service": "gateway",
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

MANAGEMENT_API_URL = os.getenv("MANAGEMENT_API_URL")
REDIS_URL = os.getenv("REDIS_URL")

redis_client: redis.Redis = None
http_client: AsyncClient = None

API_KEY_CACHE_PREFIX = "api_key:"
API_KEY_CACHE_EXPIRATION = 300 # seconds

USAGE_STREAM_KEY = "usage_events"

# Rate Limiting Configuration (per API key, per minute)
RATE_LIMIT_WINDOW_SECONDS = 60
DEFAULT_RATE_LIMIT_REQUESTS = 100 # Default if no specific limit is found

# Prometheus Metrics for Gateway
REQUEST_COUNT = Counter('gateway_http_requests_total', 'Total Gateway HTTP Requests', ['method', 'endpoint', 'status_code'])
REQUEST_LATENCY = Histogram('gateway_http_request_duration_seconds', 'Gateway HTTP Request Latency', ['method', 'endpoint'])

@app.on_event("startup")
async def startup_event():
    global redis_client, http_client
    redis_client = redis.from_url(REDIS_URL, decode_responses=True)
    http_client = AsyncClient(base_url=MANAGEMENT_API_URL)

@app.on_event("shutdown")
async def shutdown_event():
    await redis_client.close()
    await http_client.aclose()

@app.middleware("http")
async def add_prometheus_metrics_and_logging(request: Request, call_next):
    request_id = str(uuid.uuid4())
    request.state.request_id = request_id # Store request_id in request state

    method = request.method
    endpoint = request.url.path
    
    extra_log_data = {
        "request_id": request_id,
        "method": method,
        "endpoint": endpoint,
        "service": "gateway"
    }

    logger.info(f"Incoming request: {method} {endpoint}", extra=extra_log_data)

    with REQUEST_LATENCY.labels(method=method, endpoint=endpoint).time():
        response = await call_next(request)
    
    REQUEST_COUNT.labels(method=method, endpoint=endpoint, status_code=response.status_code).inc()
    extra_log_data["status_code"] = response.status_code
    logger.info(f"Outgoing response: {method} {endpoint} {response.status_code}", extra=extra_log_data)

    return response

async def validate_api_key(api_key_raw: str):
    api_key_hash = hashlib.sha256(api_key_raw.encode()).hexdigest()
    cached_key = await redis_client.get(f"{API_KEY_CACHE_PREFIX}{api_key_hash}")

    if cached_key:
        key_data = json.loads(cached_key)
        if key_data.get("status") == "active":
            return key_data

    # If not in cache or not active, validate with management API
    try:
        response = await http_client.get(f"/validate/validate-api-key/{api_key_raw}")
        response.raise_for_status() # Raise an exception for bad status codes
        key_data = response.json()
        
        if key_data.get("status") == "active":
            await redis_client.setex(f"{API_KEY_CACHE_PREFIX}{api_key_hash}", API_KEY_CACHE_EXPIRATION, json.dumps(key_data))
            return key_data
        else:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or inactive API Key")
    except Exception as e:
        logger.error(f"API Key validation failed: {e}", exc_info=True, extra={"request_id": getattr(app.state, 'request_id', None)})
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=f"API Key validation failed: {e}")

async def apply_rate_limit(api_key_hash: str, limit: int):
    current_time = int(time.time())
    key = f"rate_limit:{api_key_hash}"
    
    await redis_client.zremrangebyscore(key, 0, current_time - RATE_LIMIT_WINDOW_SECONDS)
    await redis_client.zadd(key, {current_time: current_time})
    request_count = await redis_client.zcard(key)
    await redis_client.expire(key, RATE_LIMIT_WINDOW_SECONDS + 5) # A bit longer than the window

    if request_count > limit:
        logger.warning(f"Rate limit exceeded for {api_key_hash}", extra={"request_id": getattr(app.state, 'request_id', None), "api_key_hash": api_key_hash, "limit": limit, "current_count": request_count})
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Rate limit exceeded")
    
    return limit - request_count

@app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS", "HEAD"])
async def proxy(request: Request, path: str):
    api_key_raw = request.headers.get("X-API-Key")
    if not api_key_raw:
        logger.warning("X-API-Key header missing", extra={"request_id": getattr(request.state, 'request_id', None)})
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="X-API-Key header missing")

    validated_key = await validate_api_key(api_key_raw)
    api_key_hash = hashlib.sha256(api_key_raw.encode()).hexdigest()

    # Determine rate limit from plan, or use default
    rate_limit = DEFAULT_RATE_LIMIT_REQUESTS
    if validated_key.get("plan") and validated_key["plan"].get("unit_type") == "request" and validated_key["plan"].get("unit_price_cents") is not None:
        rate_limit = 1000 # Example: higher limit for metered plans
    elif validated_key.get("plan") and validated_key["plan"].get("name") == "Free Tier": # Example for a free tier
        rate_limit = 10 # Example: lower limit for free tier
    
    # Apply rate limiting
    remaining_requests = await apply_rate_limit(api_key_hash, rate_limit)

    # Quota Enforcement
    quota_limit = validated_key.get("plan", {}).get("quota_limit")
    current_quota_usage = 0

    if quota_limit is not None:
        # Fetch current usage from management-api
        today = date.today()
        start_of_month = date(today.year, today.month, 1)
        
        try:
            analytics_response = await http_client.get(
                f"/apis/{validated_key.get('api_id')}/usage",
                params={
                    "start_date": start_of_month.isoformat(),
                    "end_date": today.isoformat(),
                    "client_id": validated_key.get("client_id") # Now filtering by client_id
                }
            )
            analytics_response.raise_for_status()
            usage_data = analytics_response.json()
            
            # Sum up total_requests for the current client
            current_quota_usage = sum(entry.get("total_requests", 0) for entry in usage_data)

            if current_quota_usage >= quota_limit:
                logger.warning(f"Quota limit exceeded for {api_key_raw[:5]}...", extra={"request_id": getattr(request.state, 'request_id', None), "api_key_hash": api_key_hash, "quota_limit": quota_limit, "current_usage": current_quota_usage})
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Quota limit exceeded")

        except Exception as e:
            logger.error(f"Error fetching usage for quota enforcement: {e}", exc_info=True, extra={"request_id": getattr(request.state, 'request_id', None)})

    usage_event = {
        "api_id": validated_key.get("api_id"),
        "client_id": validated_key.get("client_id"),
        "endpoint": f"/{path}",
        "units": 1, # For now, 1 unit per request
        "bytes": len(await request.body()), # Approximate bytes transferred
        "timestamp": time.time() # Unix timestamp
    }
    await redis_client.xadd(USAGE_STREAM_KEY, usage_event)

    response = Response(content=json.dumps({"message": f"Request proxied for path: /{path}", "api_key_used": api_key_raw, "validated_key_info": validated_key}), media_type="application/json")
    response.headers["X-RateLimit-Limit"] = str(rate_limit)
    response.headers["X-RateLimit-Remaining"] = str(remaining_requests)
    response.headers["X-RateLimit-Reset"] = str(RATE_LIMIT_WINDOW_SECONDS) # Time until reset
    if quota_limit is not None:
        response.headers["X-Quota-Limit"] = str(quota_limit)
        response.headers["X-Quota-Used"] = str(current_quota_usage + 1) # +1 for the current request

    return response

@app.get("/metrics", response_class=PlainTextResponse)
async def metrics():
    return PlainTextResponse(generate_latest())
