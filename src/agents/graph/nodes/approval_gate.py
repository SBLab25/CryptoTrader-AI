"""Phase 3 approval gate node."""

from __future__ import annotations

import json
import asyncio
import time
from datetime import datetime, timedelta

from sqlalchemy import select

from src.core.config import settings
from src.db.database import get_db_session
from src.db.models import ApprovalRequestRecord

PENDING = "PENDING"
APPROVED = "APPROVED"
DENIED = "DENIED"
EXPIRED = "EXPIRED"


async def _get_existing_pending(symbol: str, cycle_id: str) -> ApprovalRequestRecord | None:
    async with get_db_session() as session:
        result = await session.execute(
            select(ApprovalRequestRecord)
            .where(ApprovalRequestRecord.symbol == symbol)
            .where(ApprovalRequestRecord.status == PENDING)
            .order_by(ApprovalRequestRecord.created_at.desc())
        )
        for record in result.scalars().all():
            payload = json.loads(record.trade_payload_json or "{}")
            if payload.get("cycle_id") == cycle_id:
                return record
    return None


async def _create_approval_request(state: dict) -> ApprovalRequestRecord:
    signal = state["signal"]
    risk_result = state["risk_result"]
    expires_at = datetime.utcnow() + timedelta(seconds=settings.approval_timeout_seconds)
    payload = {
        "cycle_id": state.get("cycle_id"),
        "signal": signal,
        "risk_result": risk_result,
    }
    async with get_db_session() as session:
        record = ApprovalRequestRecord(
            symbol=state["symbol"],
            side=str(signal.get("action", "")).lower(),
            position_usd=float(risk_result.get("approved_position_usd", 0.0)),
            confidence=float(signal.get("confidence", 0.0)),
            status=PENDING,
            trade_payload_json=json.dumps(payload, default=str),
            created_at=datetime.utcnow(),
            expires_at=expires_at,
        )
        session.add(record)
        await session.commit()
        return record


async def _reload(approval_id: str) -> ApprovalRequestRecord | None:
    async with get_db_session() as session:
        return await session.get(ApprovalRequestRecord, approval_id)


async def approval_gate_node(state: dict) -> dict:
    started = time.monotonic()
    try:
        mode = str(state.get("mode") or settings.trading_mode).lower()
        position_usd = float((state.get("risk_result") or {}).get("approved_position_usd", 0.0))
        if mode in {"paper", "demo"} or position_usd <= settings.approval_threshold_usd:
            return {
                "approval_granted": True,
                "approval_status": APPROVED,
                "errors": [],
                "node_timings": {"approval_gate": round((time.monotonic() - started) * 1000, 2)},
            }

        record = await _get_existing_pending(state["symbol"], state.get("cycle_id"))
        if record is None:
            record = await _create_approval_request(state)

        deadline = time.monotonic() + settings.approval_timeout_seconds
        current = record
        while time.monotonic() < deadline:
            if current.status == APPROVED:
                return {
                    "approval_granted": True,
                    "approval_status": APPROVED,
                    "approval_request_id": current.id,
                    "errors": [],
                    "node_timings": {"approval_gate": round((time.monotonic() - started) * 1000, 2)},
                }
            if current.status == DENIED:
                return {
                    "approval_granted": False,
                    "approval_status": DENIED,
                    "approval_request_id": current.id,
                    "errors": [],
                    "node_timings": {"approval_gate": round((time.monotonic() - started) * 1000, 2)},
                }
            if current.expires_at <= datetime.utcnow():
                async with get_db_session() as session:
                    persisted = await session.get(ApprovalRequestRecord, current.id)
                    if persisted and persisted.status == PENDING:
                        persisted.status = EXPIRED
                        persisted.decided_at = datetime.utcnow()
                        persisted.decided_by = "system"
                        await session.commit()
                return {
                    "approval_granted": False,
                    "approval_status": EXPIRED,
                    "approval_request_id": current.id,
                    "errors": [],
                    "node_timings": {"approval_gate": round((time.monotonic() - started) * 1000, 2)},
                }
            await asyncio.sleep(0.05)
            current = await _reload(record.id) or current

        return {
            "approval_granted": False,
            "approval_status": EXPIRED,
            "approval_request_id": record.id,
            "errors": [],
            "node_timings": {"approval_gate": round((time.monotonic() - started) * 1000, 2)},
        }
    except Exception as exc:
        return {
            "approval_granted": False,
            "approval_status": "ERROR",
            "errors": [f"approval_gate_node failed: {exc}"],
            "node_timings": {"approval_gate": round((time.monotonic() - started) * 1000, 2)},
        }
