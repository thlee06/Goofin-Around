from datetime import date
from typing import Optional
from pydantic import BaseModel


class FilterParams(BaseModel):
    q: Optional[str] = None
    department: Optional[str] = None      # department slug
    category: Optional[str] = None        # category slug
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    is_free: Optional[bool] = None
    page: int = 1
    per_page: int = 20
