from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List

import crud, schemas, models
from database import get_db
from auth import get_current_active_user

api_router = APIRouter()

@api_router.post("/apis", response_model=schemas.APIInDB, status_code=status.HTTP_201_CREATED)
async def create_api(api: schemas.APICreate, current_user: schemas.UserInDB = Depends(get_current_active_user), db: AsyncSession = Depends(get_db)):
    # Only owner can create API, so owner_id is current_user.id
    return await crud.create_api(db=db, api=api, owner_id=current_user.id)

@api_router.get("/apis/{api_id}", response_model=schemas.APIInDB)
async def get_api(api_id: int, db: AsyncSession = Depends(get_db)):
    db_api = await crud.get_api_by_id(db, api_id=api_id)
    if db_api is None:
        raise HTTPException(status_code=404, detail="API not found")
    return db_api

@api_router.post("/apis/{api_id}/plans", response_model=schemas.PlanInDB, status_code=status.HTTP_201_CREATED)
async def create_plan_for_api(api_id: int, plan: schemas.PlanBase, current_user: schemas.UserInDB = Depends(get_current_active_user), db: AsyncSession = Depends(get_db)):
    db_api = await crud.get_api_by_id(db, api_id=api_id)
    if db_api is None or db_api.owner_id != current_user.id:
        raise HTTPException(status_code=404, detail="API not found or you don't have permission to add plans to this API")
    
    plan_create = schemas.PlanCreate(api_id=api_id, **plan.dict())
    return await crud.create_plan(db=db, plan=plan_create)
