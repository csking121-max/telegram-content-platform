"""Admin CRUD for tokens."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from backend.dependencies import get_db
from backend.schemas.token import TokenCreate, TokenRead
from backend.models.token import Token
from backend.engines.token_service import TokenService

router = APIRouter()


@router.get("", response_model=list[TokenRead])
async def list_tokens(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Token).order_by(Token.created_at.desc()).offset(skip).limit(limit)
    )
    return result.scalars().all()


@router.get("/{token_string}", response_model=TokenRead)
async def get_token(token_string: str, db: AsyncSession = Depends(get_db)):
    svc = TokenService(db)
    token = await svc.get(token_string)
    if not token:
        raise HTTPException(404, "Token not found")
    return token


@router.post("", response_model=TokenRead, status_code=201)
async def create_token(body: TokenCreate, db: AsyncSession = Depends(get_db)):
    svc = TokenService(db)
    token = await svc.create(
        pack_id=body.pack_id,
        single_use=body.single_use,
        bound_user_id=body.bound_user_id,
    )
    return token


@router.delete("/{token_string}")
async def revoke_token(token_string: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Token).where(Token.token == token_string))
    token = result.scalar_one_or_none()
    if not token:
        raise HTTPException(404, "Token not found")
    await db.delete(token)
    await db.commit()
    return {"detail": "Token revoked"}