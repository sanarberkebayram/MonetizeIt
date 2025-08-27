from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import func
from datetime import date, datetime
from typing import List, Optional, Dict, Any

import crud, schemas, models
from database import get_db
from auth import get_current_active_user

publisher_analytics_router = APIRouter()

@publisher_analytics_router.get("/publishers/{publisher_id}/revenue", response_model=Dict[str, Any])
async def get_publisher_revenue(
    publisher_id: int,
    start_date: Optional[date] = Query(None, description="Start date for revenue data (YYYY-MM-DD)"),
    end_date: Optional[date] = Query(None, description="End date for revenue data (YYYY-MM-DD)"),
    current_user: schemas.UserInDB = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    # Verify that the current user is the publisher or an admin
    if current_user.id != publisher_id and current_user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to view this publisher's revenue.")

    # Get all APIs owned by this publisher
    api_stmt = select(models.API).filter(models.API.owner_id == publisher_id)
    apis = (await db.execute(api_stmt)).scalars().all()
    api_ids = [api.id for api in apis]

    if not api_ids:
        return {"total_revenue_cents": 0, "revenue_by_api": {}}

    query = select(
        models.Invoice.api_id,
        func.sum(models.Invoice.amount_cents)
    ).filter(
        models.Invoice.api_id.in_(api_ids),
        models.Invoice.status == "paid" # Only count paid invoices
    ).group_by(models.Invoice.api_id)

    if start_date:
        query = query.filter(models.Invoice.period_start >= start_date)
    if end_date:
        query = query.filter(models.Invoice.period_end <= end_date)

    result = await db.execute(query)
    revenue_data = result.all()

    total_revenue_cents = 0
    revenue_by_api = {}
    for api_id, revenue_cents in revenue_data:
        total_revenue_cents += revenue_cents
        api_name = next((api.name for api in apis if api.id == api_id), f"API {api_id}")
        revenue_by_api[api_name] = revenue_cents

    return {
        "total_revenue_cents": total_revenue_cents,
        "revenue_by_api": revenue_by_api
    }
