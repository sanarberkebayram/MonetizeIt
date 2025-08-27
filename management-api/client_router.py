from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List
import secrets
import hashlib

import crud, schemas, models
from database import get_db
from auth import get_current_active_user

client_router = APIRouter()

@client_router.post("/clients", response_model=schemas.ClientInDB, status_code=status.HTTP_201_CREATED)
async def create_client(client: schemas.ClientBase, current_user: schemas.UserInDB = Depends(get_current_active_user), db: AsyncSession = Depends(get_db)):
    client_create = schemas.ClientCreate(user_id=current_user.id, **client.dict())
    return await crud.create_client(db=db, client=client_create)

@client_router.post("/clients/{client_id}/keys", response_model=schemas.APIKeyInDB, status_code=status.HTTP_201_CREATED)
async def create_api_key_for_client(client_id: int, api_id: int, current_user: schemas.UserInDB = Depends(get_current_active_user), db: AsyncSession = Depends(get_db)):
    db_client = await crud.get_client_by_id(db, client_id=client_id)
    if db_client is None or db_client.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Client not found or you don't have permission to create keys for this client")
    
    db_api = await crud.get_api_by_id(db, api_id=api_id)
    if db_api is None:
        raise HTTPException(status_code=404, detail="API not found")

    # Generate a random API key
    api_key_raw = secrets.token_urlsafe(32)
    api_key_hash = hashlib.sha256(api_key_raw.encode()).hexdigest()

    api_key_create = schemas.APIKeyCreate(client_id=client_id, api_id=api_id)
    db_api_key = await crud.create_api_key(db=db, api_key=api_key_create, key_hash=api_key_hash)
    
    # Return the raw key to the user only once
    db_api_key.key_hash = api_key_raw # Temporarily set to raw key for response
    return db_api_key

@client_router.delete("/clients/{client_id}/keys/{key_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_api_key(client_id: int, key_id: int, current_user: schemas.UserInDB = Depends(get_current_active_user), db: AsyncSession = Depends(get_db)):
    db_api_key = await crud.revoke_api_key(db, api_key_id=key_id)
    if db_api_key is None or db_api_key.client.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="API Key not found or you don't have permission to revoke this key")
    return
