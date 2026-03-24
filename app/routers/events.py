from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import Optional
from datetime import date

from app.database import get_db
from app.schemas.event import EventOut, EventDetail
from app.services.event_service import get_events, get_event_by_id

router = APIRouter(tags=["events"])


@router.get("/", response_model=dict)
def list_events(
    db: Session = Depends(get_db),
    q: Optional[str] = None,
    department: Optional[str] = None,
    category: Optional[str] = None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    is_free: Optional[bool] = None,
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, ge=1, le=100),
):
    events, total = get_events(
        db, q=q, department=department, category=category,
        start_date=start_date, end_date=end_date, is_free=is_free,
        page=page, per_page=per_page,
    )
    return {
        "total": total,
        "page": page,
        "per_page": per_page,
        "results": [EventOut.model_validate(e) for e in events],
    }


@router.get("/{event_id}", response_model=EventDetail)
def get_event(event_id: int, db: Session = Depends(get_db)):
    event = get_event_by_id(db, event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    return EventDetail.model_validate(event)
