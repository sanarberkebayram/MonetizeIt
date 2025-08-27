from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import func
from datetime import date, datetime
from typing import List, Optional

import crud, schemas, models
from database import get_db
from auth import get_current_active_user

analytics_router = APIRouter()

@analytics_router.get("/apis/{api_id}/usage", response_model=List[schemas.UsageAggregateInDB])
async def get_api_usage(
    api_id: int,
    start_date: Optional[date] = Query(None, description="Start date for usage data (YYYY-MM-DD)"),
    end_date: Optional[date] = Query(None, description="End date for usage data (YYYY-MM-DD)"),
    client_id: Optional[int] = Query(None, description="Filter by client ID"), # New parameter
    current_user: schemas.UserInDB = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    # Verify that the current user owns the API or is an admin
    db_api = await crud.get_api_by_id(db, api_id)
    if not db_api or (db_api.owner_id != current_user.id and current_user.role != "admin"):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="API not found or unauthorized")

    query = select(models.UsageAggregate).filter(models.UsageAggregate.api_id == api_id)

    if start_date:
        query = query.filter(models.UsageAggregate.date >= start_date)
    if end_date:
        query = query.filter(models.UsageAggregate.date <= end_date)
    if client_id:
        query = query.filter(models.UsageAggregate.client_id == client_id) # Apply client_id filter

    result = await db.execute(query.order_by(models.UsageAggregate.date))
    usage_data = result.scalars().all()

    return usage_data