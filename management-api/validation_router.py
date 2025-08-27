from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
import hashlib

import crud, schemas
from database import get_db

validation_router = APIRouter()

@validation_router.get("/validate-api-key/{api_key_raw}", response_model=schemas.APIKeyInDB)
async def validate_api_key(api_key_raw: str, db: AsyncSession = Depends(get_db)):
    api_key_hash = hashlib.sha256(api_key_raw.encode()).hexdigest()
    db_api_key = await crud.get_api_key_by_hash(db, key_hash=api_key_hash)
    
    if not db_api_key or db_api_key.status != "active":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or inactive API Key")
    
    return db_api_key