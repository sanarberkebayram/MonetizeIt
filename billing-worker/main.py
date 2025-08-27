import os
import redis.asyncio as redis
import asyncio
import json
from datetime import datetime, date, timedelta
from collections import defaultdict

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import sessionmaker, joinedload
from sqlalchemy import func

from database import Base # Import Base from the copied database.py
from models import UsageAggregate, API, Client, Plan, User, Subscription, Invoice, Payout # Import models from the copied models.py
from redis import exceptions as redis_exceptions
import stripe

from prometheus_client import start_http_server, Counter, Histogram, generate_latest

import logging
import uuid

# Configure JSON logging
class JsonFormatter(logging.Formatter):
    def format(self, record):
        log_record = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "message": record.getMessage(),
            "service": "billing-worker",
            "request_id": getattr(record, 'request_id', None),
            "traceback": self.formatException(record.exc_info) if record.exc_info else None,
        }
        return json.dumps(log_record)

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
handler = logging.StreamHandler()
handler.setFormatter(JsonFormatter())
logger.addHandler(handler)

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+asyncpg://postgres:example@postgres:5432/monetizeit_db")
STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY")

stripe.api_key = STRIPE_SECRET_KEY

USAGE_STREAM_KEY = "usage_events"
CONSUMER_GROUP = "billing_group"
CONSUMER_NAME = os.getenv("HOSTNAME", "billing_consumer_1")

# Prometheus Metrics for Billing Worker
BILLING_PROCESS_COUNT = Counter('billing_process_total', 'Total billing processes run')
BILLING_INVOICE_COUNT = Counter('billing_invoices_created_total', 'Total invoices created', ['status'])
BILLING_PAYOUT_COUNT = Counter('billing_payouts_total', 'Total payouts initiated', ['status'])
BILLING_USAGE_EVENTS_PROCESSED = Counter('billing_usage_events_processed_total', 'Total usage events processed')

# SQLAlchemy setup
engine = create_async_engine(DATABASE_URL, echo=False)
AsyncSessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False
)

async def get_db():
    async with AsyncSessionLocal() as session:
        yield session

async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

async def process_monthly_billing():
    BILLING_PROCESS_COUNT.inc()
    logger.info("Starting monthly billing process...")
    async with AsyncSessionLocal() as db:
        stmt = select(Subscription).options(joinedload(Subscription.user), joinedload(Subscription.plan))
        subscriptions = (await db.execute(stmt)).scalars().all()

        for sub in subscriptions:
            today = datetime.now().date()
            # For simplicity, let's bill for the previous full month
            end_of_last_month = date(today.year, today.month, 1) - timedelta(days=1)
            start_of_last_month = date(end_of_last_month.year, end_of_last_month.month, 1)

            logger.info(f"Processing subscription {sub.id} for user {sub.user.email} for period {start_of_last_month} to {end_of_last_month}")

            # Aggregate usage for the period
            usage_stmt = select(func.sum(UsageAggregate.total_requests), func.sum(UsageAggregate.total_bytes)).filter(
                UsageAggregate.api_id == sub.plan.api_id,
                UsageAggregate.client_id == sub.user.clients[0].id, # Assuming one client per user for simplicity
                UsageAggregate.date >= start_of_last_month,
                UsageAggregate.date <= end_of_last_month
            )
            aggregated_usage = (await db.execute(usage_stmt)).first()
            total_requests = aggregated_usage[0] or 0
            total_bytes = aggregated_usage[1] or 0

            logger.info(f"  Aggregated: {total_requests} requests, {total_bytes} bytes")

            # Calculate amount due based on plan
            amount_due_cents = 0
            if sub.plan.unit_type == "subscription":
                amount_due_cents = sub.plan.price_cents
            elif sub.plan.unit_type == "request":
                amount_due_cents = total_requests * sub.plan.unit_price_cents
            elif sub.plan.unit_type == "MB":
                amount_due_cents = (total_bytes / (1024 * 1024)) * sub.plan.unit_price_cents # Convert bytes to MB
            # Add other pricing models as needed

            if amount_due_cents > 0:
                logger.info(f"  Amount due: {amount_due_cents} cents")
                try:
                    # Create Stripe Invoice Item (for metered billing)
                    if sub.plan.unit_type != "subscription":
                        stripe.InvoiceItem.create(
                            customer=sub.user.stripe_customer_id,
                            price=sub.plan.stripe_price_id, # This should be a metered price
                            quantity=total_requests if sub.plan.unit_type == "request" else (total_bytes / (1024 * 1024)),
                            unit_amount=sub.plan.unit_price_cents,
                            currency="usd", # Assuming USD
                        )

                    # Create Stripe Invoice
                    stripe_invoice = stripe.Invoice.create(
                        customer=sub.user.stripe_customer_id,
                        collection_method='charge_automatically',
                        auto_advance=True, # Auto-finalize and attempt collection
                        description=f"Invoice for {sub.plan.name} ({start_of_last_month} - {end_of_last_month})",
                        # For subscription invoices, Stripe handles this automatically
                        # For one-off invoices, you might need to add invoice items
                    )

                    # Store invoice in our database
                    new_invoice = Invoice(
                        client_id=sub.user.clients[0].id, # Assuming one client per user
                        api_id=sub.plan.api_id, # Populate api_id
                        period_start=start_of_last_month,
                        period_end=end_of_last_month,
                        amount_cents=amount_due_cents,
                        status="draft", # Will be updated by webhook to paid/failed
                        stripe_invoice_id=stripe_invoice.id
                    )
                    db.add(new_invoice)
                    await db.commit()
                    await db.refresh(new_invoice)
                    BILLING_INVOICE_COUNT.labels(status="created").inc()
                    logger.info(f"  Stripe Invoice {stripe_invoice.id} created for {sub.user.email}")

                except stripe.error.StripeError as e:
                    BILLING_INVOICE_COUNT.labels(status="failed").inc()
                    logger.error(f"  Stripe error creating invoice for {sub.user.email}: {e}", exc_info=True)
                except Exception as e:
                    BILLING_INVOICE_COUNT.labels(status="failed").inc()
                    logger.error(f"  Unexpected error creating invoice for {sub.user.email}: {e}", exc_info=True)
            else:
                logger.info(f"  No amount due for {sub.user.email}")

    logger.info("Monthly billing process finished.")

async def consume_usage_events():
    r = redis.from_url(REDIS_URL, decode_responses=True)
    
    # Ensure database tables are created
    await init_db()

    try:
        await r.xgroup_create(USAGE_STREAM_KEY, CONSUMER_GROUP, mkstream=True)
    except redis_exceptions.ResponseError as e:
        if "BUSYGROUP" in str(e):
            logger.info(f"Consumer group {CONSUMER_GROUP} already exists.")
        else:
            logger.error(f"Error creating consumer group: {e}", exc_info=True)
            return
    except Exception as e:
        logger.error(f"Error creating consumer group: {e}", exc_info=True)
        return

    logger.info(f"Billing worker {CONSUMER_NAME} started, consuming from stream {USAGE_STREAM_KEY} in group {CONSUMER_GROUP}")

    # Schedule monthly billing process to run once a day (for testing)
    # In production, this would be a cron job or a more robust scheduler
    asyncio.create_task(run_daily_billing_check())

    while True:
        try:
            messages = await r.xreadgroup(
                CONSUMER_GROUP,
                CONSUMER_NAME,
                {USAGE_STREAM_KEY: '>'},
                count=10, # Read up to 10 messages at once
                block=1000 # Block for 1 second
            )

            if not messages:
                await asyncio.sleep(0.1) # Small sleep to prevent busy-waiting
                continue

            for stream, message_list in messages:
                BILLING_USAGE_EVENTS_PROCESSED.inc()
                async with AsyncSessionLocal() as db:
                    for message_id, message_data in message_list:
                        event = {k.decode('utf-8'): v.decode('utf-8') for k, v in message_data.items()}
                        logger.info(f"Processing message {message_id}: {event}")

                        try:
                            api_id = int(event["api_id"])
                            client_id = int(event["client_id"])
                            units = int(event.get("units", 1))
                            bytes_transferred = int(event.get("bytes", 0))
                            timestamp = datetime.fromtimestamp(float(event["timestamp"]))
                            event_date = timestamp.date() # Aggregate by date

                            # Find or create UsageAggregate record
                            stmt = select(UsageAggregate).filter_by(
                                api_id=api_id,
                                client_id=client_id,
                                date=event_date
                            )
                            result = await db.execute(stmt)
                            usage_aggregate = result.scalars().first()

                            if usage_aggregate:
                                usage_aggregate.total_requests += units
                                usage_aggregate.total_bytes += bytes_transferred
                            else:
                                usage_aggregate = UsageAggregate(
                                    api_id=api_id,
                                    client_id=client_id,
                                    date=event_date,
                                    total_requests=units,
                                    total_bytes=bytes_transferred
                                )
                                db.add(usage_aggregate)
                            
                            await db.commit()
                            await db.refresh(usage_aggregate)
                            logger.info(f"  Aggregated usage for API {api_id}, Client {client_id} on {event_date}")

                            # Acknowledge the message after successful processing and persistence
                            await r.xack(USAGE_STREAM_KEY, CONSUMER_GROUP, message_id)
                            logger.info(f"  Acknowledged message {message_id}")

                        except Exception as e:
                            logger.error(f"Error processing message {message_id}: {e}", exc_info=True)
                            # Depending on error handling strategy, you might not ack here
                            # or move to a Dead Letter Queue

        except asyncio.CancelledError:
            logger.info("Consumer task cancelled.")
            break
        except Exception as e:
            logger.error(f"Error consuming messages: {e}", exc_info=True)
            await asyncio.sleep(1) # Wait before retrying

async def run_daily_billing_check():
    # Start Prometheus HTTP server for metrics
    start_http_server(8002) # Expose metrics on port 8002

    while True:
        now = datetime.now()
        # For testing, run every minute. In production, run once a day at a specific time.
        await process_monthly_billing()
        await asyncio.sleep(60) # Check every minute

if __name__ == "__main__":
    asyncio.run(consume_usage_events())
