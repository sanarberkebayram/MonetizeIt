from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import joinedload
import models, schemas
from passlib.context import CryptContext
import stripe
import os

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

stripe.api_key = os.getenv("STRIPE_SECRET_KEY")

def get_password_hash(password):
    return pwd_context.hash(password)

def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

async def get_user_by_email(db: AsyncSession, email: str):
    result = await db.execute(select(models.User).filter(models.User.email == email))
    return result.scalars().first()

async def create_user(db: AsyncSession, user: schemas.UserCreate):
    hashed_password = get_password_hash(user.password)
    db_user = models.User(email=user.email, password_hash=hashed_password)
    db.add(db_user)
    await db.commit()
    await db.refresh(db_user)

    # Create Stripe Customer
    try:
        customer = stripe.Customer.create(
            email=db_user.email,
            metadata={'user_id': db_user.id}
        )
        db_user.stripe_customer_id = customer.id
        await db.commit()
        await db.refresh(db_user)
    except stripe.error.StripeError as e:
        print(f"Error creating Stripe customer for user {db_user.email}: {e}")
        # Handle error: potentially delete user or mark as incomplete
        # For now, we'll just log and proceed without stripe_customer_id

    return db_user

async def get_api_by_id(db: AsyncSession, api_id: int):
    result = await db.execute(select(models.API).filter(models.API.id == api_id))
    return result.scalars().first()

async def create_api(db: AsyncSession, api: schemas.APICreate, owner_id: int):
    db_api = models.API(**api.dict(), owner_id=owner_id)
    db.add(db_api)
    await db.commit()
    await db.refresh(db_api)
    return db_api

async def create_plan(db: AsyncSession, plan: schemas.PlanCreate):
    db_plan = models.Plan(**plan.dict())
    db.add(db_plan)
    await db.commit()
    await db.refresh(db_plan)
    return db_plan

async def create_client(db: AsyncSession, client: schemas.ClientCreate):
    db_client = models.Client(**client.dict())
    db.add(db_client)
    await db.commit()
    await db.refresh(db_client)
    return db_client

async def get_client_by_id(db: AsyncSession, client_id: int):
    result = await db.execute(select(models.Client).filter(models.Client.id == client_id))
    return result.scalars().first()

async def create_api_key(db: AsyncSession, api_key: schemas.APIKeyCreate, key_hash: str):
    db_api_key = models.APIKey(**api_key.dict(), key_hash=key_hash)
    db.add(db_api_key)
    await db.commit()
    await db.refresh(db_api_key)
    return db_api_key

async def get_api_key_by_hash(db: AsyncSession, key_hash: str):
    result = await db.execute(
        select(models.APIKey).options(joinedload(models.APIKey.api).joinedload(models.API.plans)).filter(models.APIKey.key_hash == key_hash)
    )
    api_key = result.scalars().first()
    if api_key and api_key.api and api_key.api.plans:
        # Assuming an API key is tied to one active plan for rate limiting purposes
        # This logic might need refinement based on how plans are assigned to API keys
        api_key.plan = api_key.api.plans[0] if api_key.api.plans else None
    return api_key

async def revoke_api_key(db: AsyncSession, api_key_id: int):
    db_api_key = await db.get(models.APIKey, api_key_id)
    if db_api_key:
        db_api_key.status = "revoked"
        await db.commit()
        await db.refresh(db_api_key)
    return db_api_key