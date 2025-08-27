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

    apis = relationship("API", back_populates="owner")
    clients = relationship("Client", back_populates="user")

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

class Plan(Base):
    __tablename__ = "plans"
    id = Column(Integer, primary_key=True, index=True)
    api_id = Column(Integer, ForeignKey("apis.id"), nullable=False)
    name = Column(String, nullable=False)
    billing_interval = Column(String, default="monthly") # e.g., "monthly", "yearly"
    price_cents = Column(Integer, nullable=False) # Price in cents
    unit_type = Column(String) # e.g., "request", "MB", "subscription"
    unit_price_cents = Column(Integer) # Price per unit in cents, if applicable

    api = relationship("API", back_populates="plans")

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