from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.notification import Notification
from app.models.user import User
from app.schemas.notifications import NotificationMarkReadRequest, NotificationResponse

router = APIRouter(prefix="/api/notifications", tags=["notifications"])


def _serialize(model: Notification) -> NotificationResponse:
    return NotificationResponse(
        id=model.id,
        user_id=model.user_id,
        kind=model.kind,
        title=model.title,
        body=model.body,
        payload=model.payload_json,
        read_at=model.read_at,
        created_at=model.created_at,
    )


@router.get("", response_model=list[NotificationResponse])
def list_notifications(
    current_user: Annotated[User, Depends(get_current_user)],
    unread_only: bool = False,
    limit: int = 50,
    db: Session = Depends(get_db),
):
    limit = max(1, min(int(limit), 200))
    query = db.query(Notification).filter(Notification.user_id == current_user.user_id)
    if unread_only:
        query = query.filter(Notification.read_at.is_(None))

    rows = (
        query.order_by(Notification.created_at.desc(), Notification.id.desc())
        .limit(limit)
        .all()
    )
    return [_serialize(item) for item in rows]


@router.patch("/{notification_id}", response_model=NotificationResponse)
def mark_notification_read(
    notification_id: int,
    body: NotificationMarkReadRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Session = Depends(get_db),
):
    item = (
        db.query(Notification)
        .filter(
            Notification.id == notification_id,
            Notification.user_id == current_user.user_id,
        )
        .first()
    )
    if not item:
        raise HTTPException(status_code=404, detail="Notification not found")

    if body.read:
        item.read_at = datetime.now(timezone.utc)
    else:
        item.read_at = None

    db.commit()
    db.refresh(item)
    return _serialize(item)
