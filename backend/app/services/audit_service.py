from typing import Any, Optional
from sqlalchemy.orm import Session
from app.models.audit_log import AuditLog


def log_audit(
    db: Session,
    user_id: Optional[str],
    action: str,
    entity: str,
    entity_id: Optional[str] = None,
    meta: Optional[Any] = None,
) -> AuditLog:
    log_entry = AuditLog(
        user_id=user_id,
        action=action,
        entity=entity,
        entity_id=entity_id,
        meta=meta or {},
    )
    db.add(log_entry)
    db.commit()
    db.refresh(log_entry)
    return log_entry
