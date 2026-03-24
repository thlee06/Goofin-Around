from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy.orm import Session
from typing import Optional

from app.database import get_db
from app.services.ics_service import generate_ics_for_event, generate_ics_for_events
from app.services.event_service import get_event_by_id

router = APIRouter(tags=["export"])


@router.get("/events/{event_id}/export.ics")
def export_single_event(event_id: int, db: Session = Depends(get_db)):
    event = get_event_by_id(db, event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    ics_content = generate_ics_for_event(event)
    return Response(
        content=ics_content,
        media_type="text/calendar",
        headers={"Content-Disposition": f'attachment; filename="event-{event_id}.ics"'},
    )


@router.get("/export.ics")
def export_multiple_events(
    db: Session = Depends(get_db),
    ids: Optional[str] = Query(default=None, description="Comma-separated event IDs"),
):
    """
    Export multiple events as a single .ics file.
    Usage: /export.ics?ids=1,2,3,7
    """
    if not ids:
        raise HTTPException(status_code=400, detail="Provide at least one event ID via ?ids=1,2,3")

    try:
        id_list = [int(i.strip()) for i in ids.split(",") if i.strip()]
    except ValueError:
        raise HTTPException(status_code=400, detail="IDs must be integers")

    from app.models.event import Event
    events = db.query(Event).filter(Event.id.in_(id_list), Event.is_active == True).all()

    if not events:
        raise HTTPException(status_code=404, detail="No matching events found")

    ics_content = generate_ics_for_events(events)
    return Response(
        content=ics_content,
        media_type="text/calendar",
        headers={"Content-Disposition": 'attachment; filename="columbia-events.ics"'},
    )
