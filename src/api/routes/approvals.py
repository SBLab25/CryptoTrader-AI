"""Phase 3 approval routes."""

from __future__ import annotations

import json
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy import select

from src.api.auth import get_current_user
from src.api.middleware.audit_logger import audit_log
from src.api.middleware.rate_limiter import limiter
from src.db.database import get_session
from src.db.models import ApprovalRequestRecord
from src.db.redis_client import broadcast

router = APIRouter(prefix="/api/approvals", tags=["Approvals"])


class ApprovalResponse(BaseModel):
    id: str
    symbol: str
    side: str
    position_usd: float
    confidence: float
    status: str
    created_at: datetime
    expires_at: datetime
    decided_at: datetime | None = None
    decided_by: str | None = None
    trade_payload: dict


def _serialize(record: ApprovalRequestRecord) -> ApprovalResponse:
    return ApprovalResponse(
        id=record.id,
        symbol=record.symbol,
        side=record.side,
        position_usd=float(record.position_usd),
        confidence=float(record.confidence),
        status=record.status,
        created_at=record.created_at,
        expires_at=record.expires_at,
        decided_at=record.decided_at,
        decided_by=record.decided_by,
        trade_payload=json.loads(record.trade_payload_json or "{}"),
    )


@router.get("/pending", response_model=list[ApprovalResponse])
async def list_pending_approvals(session=Depends(get_session), _user: str = Depends(get_current_user)):
    result = await session.execute(
        select(ApprovalRequestRecord)
        .where(ApprovalRequestRecord.status == "PENDING")
        .order_by(ApprovalRequestRecord.created_at.asc())
    )
    now = datetime.utcnow()
    return [_serialize(row) for row in result.scalars().all() if row.expires_at > now]


@router.get("/{approval_id}", response_model=ApprovalResponse)
async def get_approval(approval_id: str, session=Depends(get_session), _user: str = Depends(get_current_user)):
    record = await session.get(ApprovalRequestRecord, approval_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Approval request not found")
    return _serialize(record)


@router.post("/{approval_id}/approve", status_code=status.HTTP_200_OK)
@limiter.limit("30/minute")
async def approve_trade(
    approval_id: str,
    request: Request,
    session=Depends(get_session),
    current_user: str = Depends(get_current_user),
):
    record = await _set_decision(session, approval_id, "APPROVED", current_user)
    if record is None:
        raise HTTPException(status_code=404, detail="Approval not found or already decided")
    await audit_log(
        event_type="APPROVAL_GRANTED",
        entity_id=approval_id,
        entity_type="ApprovalRequest",
        actor=current_user,
        details={"decision": "APPROVED"},
        ip_address=request.client.host if request.client else None,
    )
    try:
        await broadcast({"type": "approval_decided", "id": approval_id, "decision": "APPROVED"})
    except Exception:
        pass
    return {"status": "approved", "id": approval_id}


@router.post("/{approval_id}/deny", status_code=status.HTTP_200_OK)
@limiter.limit("30/minute")
async def deny_trade(
    approval_id: str,
    request: Request,
    session=Depends(get_session),
    current_user: str = Depends(get_current_user),
):
    record = await _set_decision(session, approval_id, "DENIED", current_user)
    if record is None:
        raise HTTPException(status_code=404, detail="Approval not found or already decided")
    await audit_log(
        event_type="APPROVAL_DENIED",
        entity_id=approval_id,
        entity_type="ApprovalRequest",
        actor=current_user,
        details={"decision": "DENIED"},
        ip_address=request.client.host if request.client else None,
    )
    try:
        await broadcast({"type": "approval_decided", "id": approval_id, "decision": "DENIED"})
    except Exception:
        pass
    return {"status": "denied", "id": approval_id}


async def _set_decision(session, approval_id: str, decision: str, actor: str) -> ApprovalRequestRecord | None:
    record = await session.get(ApprovalRequestRecord, approval_id)
    if record is None or record.status != "PENDING" or record.expires_at <= datetime.utcnow():
        return None
    record.status = decision
    record.decided_at = datetime.utcnow()
    record.decided_by = actor
    await session.commit()
    await session.refresh(record)
    return record
