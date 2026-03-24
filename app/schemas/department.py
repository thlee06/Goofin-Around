from datetime import datetime
from typing import Optional
from pydantic import BaseModel


class DepartmentOut(BaseModel):
    id: int
    name: str
    slug: str
    school: Optional[str]
    website_url: str
    last_scraped_at: Optional[datetime]
    is_enabled: bool
    logo_url: Optional[str]

    model_config = {"from_attributes": True}
