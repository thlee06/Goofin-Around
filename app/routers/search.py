from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.database import get_db
from app.services.search_service import search_events

router = APIRouter(tags=["search"])
templates = Jinja2Templates(directory="app/templates")


@router.get("/search", response_class=HTMLResponse)
async def search(
    request: Request,
    db: Session = Depends(get_db),
    q: str = Query(default=""),
):
    results = search_events(db, q) if q.strip() else []

    # HTMX partial for live search bar
    if request.headers.get("HX-Request"):
        return templates.TemplateResponse(
            "partials/event_list.html",
            {"request": request, "events": results, "total": len(results), "page": 1},
        )

    return templates.TemplateResponse(
        "pages/index.html",
        {
            "request": request,
            "events": results,
            "total": len(results),
            "page": 1,
            "filters": {"q": q},
            "departments": [],
            "categories": [],
        },
    )
