from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Boolean, Text, Float
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from database import Base

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    password_hash = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    role = Column(String, default="developer") # e.g., "developer", "admin", "publisher"
    stripe_customer_id = Column(String, unique=True, nullable=True) # Stripe Customer ID
    stripe_account_id = Column(String, unique=True, nullable=True) # Stripe Connect Account ID for publishers

    apis = relationship("API", back_populates="owner")
    clients = relationship("Client", back_populates="user")
    subscriptions = relationship("Subscription", back_populates="user")
    invoices = relationship("Invoice", back_populates="user") # Changed to user for direct linking

class API(Base):
    __tablename__ = "apis"
    id = Column(Integer, primary_key=True, index=True)
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    name = Column(String, index=True, nullable=False)
    description = Column(Text)
    base_url = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    owner = relationship("User", back_populates="apis")
    plans = relationship("Plan", back_populates="api")
    api_keys = relationship("APIKey", back_populates="api")
    invoices = relationship("Invoice", back_populates="api") # New relationship

class Plan(Base):
    __tablename__ = "plans"
    id = Column(Integer, primary_key=True, index=True)
    api_id = Column(Integer, ForeignKey("apis.id"), nullable=False)
    name = Column(String, nullable=False)
    billing_interval = Column(String, default="monthly") # e.g., "monthly", "yearly"
    price_cents = Column(Integer, nullable=False) # Price in cents
    unit_type = Column(String) # e.g., "request", "MB", "subscription"
    unit_price_cents = Column(Integer) # Price per unit in cents, if applicable
    stripe_price_id = Column(String, unique=True, nullable=True) # Stripe Price ID
    quota_limit = Column(Integer, nullable=True) # New field for quota limit

    api = relationship("API", back_populates="plans")
    subscriptions = relationship("Subscription", back_populates="plan")

class Client(Base):
    __tablename__ = "clients"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    name = Column(String, nullable=False)
    description = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User", back_populates="clients")
    api_keys = relationship("APIKey", back_populates="client")

class APIKey(Base):
    __tablename__ = "api_keys"
    id = Column(Integer, primary_key=True, index=True)
    client_id = Column(Integer, ForeignKey("clients.id"), nullable=False)
    api_id = Column(Integer, ForeignKey("apis.id"), nullable=False)
    key_hash = Column(String, unique=True, nullable=False) # Hashed API key
    status = Column(String, default="active") # e.g., "active", "revoked"
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    expires_at = Column(DateTime(timezone=True), nullable=True)

    client = relationship("Client", back_populates="api_keys")
    api = relationship("API", back_populates="api_keys")

class UsageAggregate(Base):
    __tablename__ = "usage_aggregates"
    id = Column(Integer, primary_key=True, index=True)
    api_id = Column(Integer, ForeignKey("apis.id"), nullable=False)
    client_id = Column(Integer, ForeignKey("clients.id"), nullable=False)
    date = Column(DateTime(timezone=True), nullable=False) # Aggregation date (e.g., daily)
    total_requests = Column(Integer, default=0)
    total_bytes = Column(Integer, default=0)
    # Add other metrics as needed (e.g., total_cost_cents)

    api = relationship("API")
    client = relationship("Client")

class Subscription(Base):
    __tablename__ = "subscriptions"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    plan_id = Column(Integer, ForeignKey("plans.id"), nullable=False)
    stripe_subscription_id = Column(String, unique=True, nullable=False) # Stripe Subscription ID
    status = Column(String, default="active") # e.g., "active", "canceled", "past_due"
    started_at = Column(DateTime(timezone=True), server_default=func.now())
    canceled_at = Column(DateTime(timezone=True), nullable=True)

    user = relationship("User", back_populates="subscriptions")
    plan = relationship("Plan", back_populates="subscriptions")

class Invoice(Base):
    __tablename__ = "invoices"
    id = Column(Integer, primary_key=True, index=True)
    client_id = Column(Integer, ForeignKey("clients.id"), nullable=False)
    api_id = Column(Integer, ForeignKey("apis.id"), nullable=False) # New field
    period_start = Column(DateTime(timezone=True), nullable=False)
    period_end = Column(DateTime(timezone=True), nullable=False)
    amount_cents = Column(Integer, nullable=False)
    status = Column(String, default="draft") # e.g., "draft", "open", "paid", "void", "uncollectible"
    stripe_invoice_id = Column(String, unique=True, nullable=True) # Stripe Invoice ID

    client = relationship("Client", back_populates="invoices")
    api = relationship("API", back_populates="invoices") # New relationship

class Payout(Base):
    __tablename__ = "payouts"
    id = Column(Integer, primary_key=True, index=True)
    publisher_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    invoice_id = Column(Integer, ForeignKey("invoices.id"), nullable=False)
    amount_cents = Column(Integer, nullable=False)
    status = Column(String, default="pending") # e.g., "pending", "paid", "failed"
    stripe_payout_id = Column(String, unique=True, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    publisher = relationship("User")
    invoice = relationship("Invoice")