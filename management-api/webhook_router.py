from fastapi import APIRouter, Request, HTTPException, status, Depends
import stripe
import os
from sqlalchemy.ext.asyncio import AsyncSession
from database import get_db
import models, schemas
from datetime import datetime
from sqlalchemy.future import select

webhook_router = APIRouter()

stripe.api_key = os.getenv("STRIPE_SECRET_KEY")
WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET") # You'll need to set this environment variable

@webhook_router.post("/stripe")
async def stripe_webhook(request: Request, db: AsyncSession = Depends(get_db)):
    payload = await request.body()
    sig_header = request.headers.get('stripe-signature')

    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, WEBHOOK_SECRET
        )
    except ValueError as e:
        # Invalid payload
        raise HTTPException(status_code=400, detail=f"Invalid payload: {e}")
    except stripe.error.SignatureVerificationError as e:
        # Invalid signature
        raise HTTPException(status_code=400, detail=f"Invalid signature: {e}")

    # Handle the event
    if event['type'] == 'invoice.paid':
        invoice_data = event['data']['object']
        print(f"Invoice paid: {invoice_data['id']}")
        
        # Find or create invoice in our database
        db_invoice = await db.execute(select(models.Invoice).filter_by(stripe_invoice_id=invoice_data['id'])).scalars().first()
        if db_invoice:
            db_invoice.status = "paid"
            db_invoice.amount_cents = invoice_data['amount_due'] # Update amount in case of changes
            await db.commit()
            await db.refresh(db_invoice)
        else:
            # Create invoice if it doesn't exist (e.g., for initial invoices or if our system missed creation)
            # This requires mapping Stripe customer ID to our client_id and api_id
            # For simplicity, we'll assume client_id and api_id can be derived or are known.
            # In a real system, you'd fetch the client and API based on the Stripe customer ID
            # and potentially the subscription item.
            client_id = None # TODO: Derive client_id from invoice_data['customer']
            api_id = None # TODO: Derive api_id from invoice_data['lines'] or subscription

            # Attempt to find client based on Stripe customer ID
            db_user = await db.execute(select(models.User).filter_by(stripe_customer_id=invoice_data['customer'])).scalars().first()
            if db_user and db_user.clients:
                client_id = db_user.clients[0].id # Assuming one client per user
            
            # Attempt to find API ID from subscription if available
            if invoice_data.get('subscription'):
                db_subscription = await db.execute(select(models.Subscription).filter_by(stripe_subscription_id=invoice_data['subscription'])).scalars().first()
                if db_subscription:
                    api_id = db_subscription.plan.api_id

            if client_id is not None and api_id is not None:
                new_invoice = models.Invoice(
                    client_id=client_id,
                    api_id=api_id,
                    period_start=datetime.fromtimestamp(invoice_data['period_start']),
                    period_end=datetime.fromtimestamp(invoice_data['period_end']),
                    amount_cents=invoice_data['amount_due'],
                    status="paid",
                    stripe_invoice_id=invoice_data['id']
                )
                db.add(new_invoice)
                await db.commit()
                await db.refresh(new_invoice)
                db_invoice = new_invoice # Set db_invoice to the newly created one
            else:
                print(f"Could not derive client_id or api_id for invoice {invoice_data['id']}, skipping local invoice creation.")
                db_invoice = None

        # --- Payout Logic (Triggered by invoice.paid) ---
        if db_invoice and db_invoice.status == "paid":
            # Find the publisher (API owner) for this invoice
            db_api = await db.get(models.API, db_invoice.api_id)
            if db_api and db_api.owner and db_api.owner.role == "publisher" and db_api.owner.stripe_account_id:
                publisher_share_cents = int(db_invoice.amount_cents * 0.80) # 80% revenue share
                try:
                    transfer = stripe.Transfer.create(
                        amount=publisher_share_cents,
                        currency="usd",
                        destination=db_api.owner.stripe_account_id,
                        transfer_group=f"invoice_{db_invoice.id}", # Group transfers by invoice
                    )
                    new_payout = models.Payout(
                        publisher_id=db_api.owner.id,
                        invoice_id=db_invoice.id,
                        amount_cents=publisher_share_cents,
                        status="paid", # Assuming immediate payout for simplicity
                        stripe_payout_id=transfer.id
                    )
                    db.add(new_payout)
                    await db.commit()
                    await db.refresh(new_payout)
                    print(f"Payout {transfer.id} created for publisher {db_api.owner.email}")
                except stripe.error.StripeError as e:
                    print(f"Stripe error creating payout for {db_api.owner.email}: {e}")
                except Exception as e:
                    print(f"Unexpected error creating payout for {db_api.owner.email}: {e}")

    elif event['type'] == 'invoice.payment_failed':
        invoice_data = event['data']['object']
        print(f"Invoice payment failed: {invoice_data['id']}")
        # Update our database to mark invoice as failed, notify user
        db_invoice = await db.execute(select(models.Invoice).filter_by(stripe_invoice_id=invoice_data['id'])).scalars().first()
        if db_invoice:
            db_invoice.status = "failed"
            await db.commit()
            await db.refresh(db_invoice)

    elif event['type'] == 'customer.subscription.updated':
        subscription_data = event['data']['object']
        print(f"Subscription updated: {subscription_data['id']}")
        # Update our database to reflect subscription status changes (e.g., canceled, active)
        db_subscription = await db.execute(select(models.Subscription).filter_by(stripe_subscription_id=subscription_data['id'])).scalars().first()
        if db_subscription:
            db_subscription.status = subscription_data['status']
            if subscription_data['status'] == "canceled":
                db_subscription.canceled_at = datetime.now()
            await db.commit()
            await db.refresh(db_subscription)
        else:
            print(f"Subscription {subscription_data['id']} not found in DB, skipping update.")

    return {"status": "success"}
