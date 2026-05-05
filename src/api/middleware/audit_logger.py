"""Audit logging helpers for security-relevant events."""

import json
import re
from datetime import datetime
from typing import Any, Optional

from src.db.database import get_db_session
from src.db.models import AuditLog
from src.utils.logger import get_logger

logger = get_logger(__name__)
_SENSITIVE_KEY_PATTERNS = re.compile(
    r"(api[_\-]?key|api[_\-]?secret|password|passwd|token|secret|credential|private[_\-]?key)",
    re.IGNORECASE,
)


def _scrub_secrets(data: Any, depth: int = 0) -> Any:
    if depth > 10:
        return data
    if isinstance(data, dict):
        return {
            key: "[REDACTED]" if _SENSITIVE_KEY_PATTERNS.search(str(key)) else _scrub_secrets(value, depth + 1)
            for key, value in data.items()
        }
    if isinstance(data, list):
        return [_scrub_secrets(item, depth + 1) for item in data]
    return data


async def audit_log(
    event_type: str,
    entity_id: Optional[str] = None,
    entity_type: Optional[str] = None,
    actor: str = "system",
    details: Optional[dict] = None,
    ip_address: Optional[str] = None,
) -> None:
    try:
        scrubbed = _scrub_secrets(details or {})
        async with get_db_session() as session:
            session.add(
                AuditLog(
                    event_type=event_type,
                    entity_id=entity_id,
                    entity_type=entity_type,
                    actor=actor,
                    details_json=json.dumps(scrubbed),
                    ip_address=ip_address,
                    created_at=datetime.utcnow(),
                )
            )
            await session.commit()
    except Exception as exc:
        logger.warning(f"[AUDIT] Write failed for {event_type}: {exc}")
