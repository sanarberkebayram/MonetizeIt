from pydantic import BaseModel, EmailStr
from typing import Optional, List, Dict, Any
from datetime import datetime, date

# User Schemas
class UserBase(BaseModel):
    email: EmailStr

class UserCreate(UserBase):
    password: str

class UserInDB(UserBase):
    id: int
    created_at: datetime
    role: str
    stripe_customer_id: Optional[str] = None
    stripe_account_id: Optional[str] = None # New field

    class Config:
        from_attributes = True

# API Schemas
class APIBase(BaseModel):
    name: str
    description: Optional[str] = None
    base_url: str

class APICreate(APIBase):
    pass

class APIInDB(APIBase):
    id: int
    owner_id: int
    created_at: datetime

    class Config:
        from_attributes = True

# Plan Schemas
class PlanBase(BaseModel):
    name: str
    billing_interval: Optional[str] = "monthly"
    price_cents: int
    unit_type: Optional[str] = None
    unit_price_cents: Optional[int] = None
    stripe_price_id: Optional[str] = None
    quota_limit: Optional[int] = None # New field for quota limit

class PlanCreate(PlanBase):
    api_id: int

class PlanInDB(PlanBase):
    id: int
    api_id: int
    stripe_price_id: Optional[str] = None
    quota_limit: Optional[int] = None

    class Config:
        from_attributes = True

# Client Schemas
class ClientBase(BaseModel):
    name: str
    description: Optional[str] = None

class ClientCreate(ClientBase):
    user_id: int

class ClientInDB(ClientBase):
    id: int
    user_id: int
    created_at: datetime

    class Config:
        from_attributes = True

# APIKey Schemas
class APIKeyInDB(BaseModel):
    id: int
    client_id: int
    api_id: int
    key_hash: str
    status: str
    created_at: datetime
    expires_at: Optional[datetime] = None
    plan: Optional[PlanInDB] = None # Add plan details here

    class Config:
        from_attributes = True

class APIKeyCreate(BaseModel):
    client_id: int
    api_id: int
    status: Optional[str] = "active"
    expires_at: Optional[datetime] = None

# Usage Aggregate Schemas
class UsageAggregateBase(BaseModel):
    api_id: int
    client_id: int
    date: date
    total_requests: int
    total_bytes: int

class UsageAggregateInDB(UsageAggregateBase):
    id: int

    class Config:
        from_attributes = True

# Subscription Schemas
class SubscriptionBase(BaseModel):
    user_id: int
    plan_id: int
    stripe_subscription_id: str
    status: str = "active"
    started_at: datetime
    canceled_at: Optional[datetime] = None

class SubscriptionCreate(BaseModel):
    user_id: int
    plan_id: int
    stripe_subscription_id: str

class SubscriptionInDB(SubscriptionBase):
    id: int

    class Config:
        from_attributes = True

# Invoice Schemas
class InvoiceBase(BaseModel):
    client_id: int
    api_id: int # New field
    period_start: datetime
    period_end: datetime
    amount_cents: int
    status: str = "draft"
    stripe_invoice_id: Optional[str] = None

class InvoiceCreate(BaseModel):
    client_id: int
    api_id: int # New field
    period_start: datetime
    period_end: datetime
    amount_cents: int
    status: str
    stripe_invoice_id: Optional[str] = None

class InvoiceInDB(InvoiceBase):
    id: int

    class Config:
        from_attributes = True

# Payout Schemas
class PayoutBase(BaseModel):
    publisher_id: int
    invoice_id: int
    amount_cents: int
    status: str = "pending"
    stripe_payout_id: Optional[str] = None

class PayoutCreate(BaseModel):
    publisher_id: int
    invoice_id: int
    amount_cents: int

class PayoutInDB(PayoutBase):
    id: int
    created_at: datetime

    class Config:
        from_attributes = True

# Auth Schemas
class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    email: Optional[str] = None
