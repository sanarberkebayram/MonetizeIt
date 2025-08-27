from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
import stripe
import os

import crud, schemas, models
from database import get_db
from auth import get_current_active_user

subscription_router = APIRouter()

stripe.api_key = os.getenv("STRIPE_SECRET_KEY")

@subscription_router.post("/subscriptions", response_model=schemas.SubscriptionInDB, status_code=status.HTTP_201_CREATED)
async def create_subscription(
    plan_id: int,
    current_user: schemas.UserInDB = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    if not current_user.stripe_customer_id:
        raise HTTPException(status_code=400, detail="Stripe customer not found for this user.")

    db_plan = await db.get(models.Plan, plan_id)
    if not db_plan:
        raise HTTPException(status_code=404, detail="Plan not found.")
    
    if not db_plan.stripe_price_id:
        raise HTTPException(status_code=400, detail="Plan does not have a Stripe Price ID configured.")

    try:
        # Create Stripe Subscription
        stripe_subscription = stripe.Subscription.create(
            customer=current_user.stripe_customer_id,
            items=[{"price": db_plan.stripe_price_id}],
            expand=["latest_invoice.payment_intent"],
        )

        # Store subscription in our database
        new_subscription = models.Subscription(
            user_id=current_user.id,
            plan_id=plan_id,
            stripe_subscription_id=stripe_subscription.id,
            status=stripe_subscription.status,
            started_at=datetime.fromtimestamp(stripe_subscription.current_period_start)
        )
        db.add(new_subscription)
        await db.commit()
        await db.refresh(new_subscription)

        return new_subscription

    except stripe.error.CardError as e:
        raise HTTPException(status_code=400, detail=f"Card error: {e.user_message}")
    except stripe.error.StripeError as e:
        raise HTTPException(status_code=500, detail=f"Stripe error: {e.user_message}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"An unexpected error occurred: {e}")

# TODO: Add endpoints for updating/canceling subscriptions
