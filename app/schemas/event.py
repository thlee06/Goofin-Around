from datetime import datetime
from typing import Optional
from pydantic import BaseModel


class CategoryOut(BaseModel):
    id: int
    name: str
    slug: str
    color_hex: str

    model_config = {"from_attributes": True}


class DepartmentBrief(BaseModel):
    id: int
    name: str
    slug: str
    logo_url: Optional[str]

    model_config = {"from_attributes": True}


class EventOut(BaseModel):
    id: int
    title: str
    short_description: Optional[str]
    start_datetime: Optional[datetime]
    end_datetime: Optional[datetime]
    all_day: bool
    location_name: Optional[str]
    latitude: Optional[float]
    longitude: Optional[float]
    source_url: str
    image_url: Optional[str]
    registration_url: Optional[str]
    is_free: Optional[bool]
    tags: list[str]
    department: DepartmentBrief
    category: Optional[CategoryOut]
    is_active: bool

    model_config = {"from_attributes": True}


class EventDetail(EventOut):
    description: Optional[str]
    location_address: Optional[str]
    created_at: datetime
    updated_at: datetime
