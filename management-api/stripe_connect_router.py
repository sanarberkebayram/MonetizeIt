from fastapi import APIRouter, Depends, HTTPException, status, Query
from typing import Dict
from sqlalchemy.ext.asyncio import AsyncSession
import stripe
import os

import crud, schemas, models
from database import get_db
from auth import get_current_active_user

stripe_connect_router = APIRouter()

stripe.api_key = os.getenv("STRIPE_SECRET_KEY")
PLATFORM_ACCOUNT_ID = os.getenv("STRIPE_ACCOUNT_ID") # Your platform's Stripe Account ID (if applicable)

@stripe_connect_router.post("/onboard-publisher", response_model=Dict[str, str])
async def onboard_publisher(
    current_user: schemas.UserInDB = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    if current_user.role != "publisher":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only publishers can onboard.")

    if current_user.stripe_account_id:
        # If already has an account, create an account link to update/manage
        account_link = stripe.AccountLink.create(
            account=current_user.stripe_account_id,
            refresh_url="http://localhost:8000/stripe-connect/reauth", # TODO: Replace with actual URL
            return_url="http://localhost:8000/stripe-connect/return", # TODO: Replace with actual URL
            type="account_onboarding",
        )
        return {"url": account_link.url}

    try:
        # Create a Stripe Connect account for the publisher
        account = stripe.Account.create(type="standard") # Or "express" or "custom"
        
        # Save the account ID to the user
        current_user.stripe_account_id = account.id
        db.add(current_user)
        await db.commit()
        await db.refresh(current_user)

        # Create an account link for onboarding
        account_link = stripe.AccountLink.create(
            account=account.id,
            refresh_url="http://localhost:8000/stripe-connect/reauth", # TODO: Replace with actual URL
            return_url="http://localhost:8000/stripe-connect/return", # TODO: Replace with actual URL
            type="account_onboarding",
        )
        return {"url": account_link.url}

    except stripe.error.StripeError as e:
        raise HTTPException(status_code=500, detail=f"Stripe error: {e.user_message}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"An unexpected error occurred: {e}")

@stripe_connect_router.get("/return")
async def stripe_connect_return(account_id: str = Query(...), db: AsyncSession = Depends(get_db)):
    # This endpoint is hit by Stripe after the user completes (or skips) onboarding
    # You should check the account status here to confirm onboarding is complete
    # For simplicity, we'll just return a success message.
    # In a real app, you'd redirect to a dashboard page.
    db_user = await db.execute(select(models.User).filter(models.User.stripe_account_id == account_id)).scalars().first()
    if db_user:
        # Optionally, fetch account details from Stripe to verify capabilities
        # account = stripe.Account.retrieve(account_id)
        # if account.capabilities.transfers.status == 'active':
        #     db_user.role = "publisher" # Or update status
        #     await db.commit()
        print(f"Publisher {db_user.email} successfully onboarded Stripe Connect.")
        return {"message": "Stripe Connect onboarding successful!"}
    raise HTTPException(status_code=404, detail="User not found for this Stripe account.")

@stripe_connect_router.get("/reauth")
async def stripe_connect_reauth():
    # This endpoint is hit by Stripe if the account link expires or is invalid
    # You should redirect the user back to the onboarding flow
    raise HTTPException(status_code=400, detail="Stripe Connect re-authentication required. Please re-initiate onboarding.")
