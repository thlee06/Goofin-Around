from fastapi import APIRouter, Request, Depends, Query
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from typing import Optional
from datetime import date

from app.database import get_db
from app.services.event_service import get_events, get_event_by_id
from app.services.search_service import search_events

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.get("/", response_class=HTMLResponse)
async def index(
    request: Request,
    db: Session = Depends(get_db),
    q: Optional[str] = None,
    department: Optional[str] = None,
    category: Optional[str] = None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    is_free: Optional[bool] = None,
    page: int = Query(default=1, ge=1),
):
    events, total = get_events(
        db, q=q, department=department, category=category,
        start_date=start_date, end_date=end_date, is_free=is_free,
        page=page,
    )
    departments = _get_departments(db)
    categories = _get_categories(db)

    # HTMX partial swap: return only the event list fragment
    if request.headers.get("HX-Request"):
        return templates.TemplateResponse(
            "partials/event_list.html",
            {"request": request, "events": events, "total": total, "page": page},
        )

    return templates.TemplateResponse(
        "pages/index.html",
        {
            "request": request,
            "events": events,
            "total": total,
            "page": page,
            "departments": departments,
            "categories": categories,
            "filters": {
                "q": q, "department": department, "category": category,
                "start_date": start_date, "end_date": end_date, "is_free": is_free,
            },
        },
    )


@router.get("/events/{event_id}", response_class=HTMLResponse)
async def event_detail(request: Request, event_id: int, db: Session = Depends(get_db)):
    event = get_event_by_id(db, event_id)
    if not event:
        return templates.TemplateResponse(
            "pages/404.html", {"request": request}, status_code=404
        )
    return templates.TemplateResponse(
        "pages/event_detail.html", {"request": request, "event": event}
    )


@router.get("/calendar", response_class=HTMLResponse)
async def calendar_view(
    request: Request,
    db: Session = Depends(get_db),
    month: Optional[str] = None,  # format: "2026-03"
):
    from app.services.event_service import get_events_for_month
    from datetime import datetime
    import calendar as cal_module

    if month:
        try:
            year, mo = map(int, month.split("-"))
            view_date = date(year, mo, 1)
        except (ValueError, AttributeError):
            view_date = date.today().replace(day=1)
    else:
        view_date = date.today().replace(day=1)

    calendar_data = get_events_for_month(db, view_date.year, view_date.month)

    # Compute prev/next month strings for nav buttons
    first_weekday = cal_module.monthrange(view_date.year, view_date.month)[0]  # 0=Mon
    if view_date.month == 1:
        prev = date(view_date.year - 1, 12, 1)
    else:
        prev = date(view_date.year, view_date.month - 1, 1)
    if view_date.month == 12:
        nxt = date(view_date.year + 1, 1, 1)
    else:
        nxt = date(view_date.year, view_date.month + 1, 1)

    cal_ctx = {
        "request": request,
        "calendar_data": calendar_data,
        "view_date": view_date,
        "today_date": date.today(),
        "first_weekday": first_weekday,
        "prev_month": prev.strftime("%Y-%m"),
        "prev_month_label": prev.strftime("%b %Y"),
        "next_month": nxt.strftime("%Y-%m"),
        "next_month_label": nxt.strftime("%b %Y"),
    }

    if request.headers.get("HX-Request"):
        return templates.TemplateResponse("partials/calendar_grid.html", cal_ctx)

    return templates.TemplateResponse("pages/calendar.html", cal_ctx)


@router.get("/map", response_class=HTMLResponse)
async def map_view(request: Request, db: Session = Depends(get_db)):
    from app.services.event_service import get_mappable_events
    import json

    events = get_mappable_events(db)
    events_json = json.dumps([
        {
            "id": e.id,
            "title": e.title,
            "lat": e.latitude,
            "lon": e.longitude,
            "location": e.location_name,
            "start": e.start_datetime.isoformat() if e.start_datetime else None,
            "department": e.department.name if e.department else "",
            "url": f"/events/{e.id}",
        }
        for e in events
    ])
    return templates.TemplateResponse(
        "pages/map.html", {"request": request, "events_json": events_json}
    )


@router.get("/departments", response_class=HTMLResponse)
async def departments_page(request: Request, db: Session = Depends(get_db)):
    departments = _get_departments(db)
    return templates.TemplateResponse(
        "pages/departments.html", {"request": request, "departments": departments}
    )


@router.get("/admin/scrapes", response_class=HTMLResponse)
async def scrape_status(request: Request, db: Session = Depends(get_db)):
    from app.models import ScrapeRun, Department
    runs = (
        db.query(ScrapeRun)
        .join(Department)
        .order_by(ScrapeRun.started_at.desc())
        .limit(100)
        .all()
    )
    return templates.TemplateResponse(
        "pages/admin_scrapes.html", {"request": request, "runs": runs}
    )


def _get_departments(db: Session):
    from app.models import Department
    return db.query(Department).filter_by(is_enabled=True).order_by(Department.name).all()


def _get_categories(db: Session):
    from app.models import Category
    return db.query(Category).order_by(Category.name).all()
