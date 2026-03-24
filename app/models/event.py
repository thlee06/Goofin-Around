from datetime import datetime
from sqlalchemy import (
    String, Boolean, Integer, Float, DateTime, ForeignKey, Text, JSON
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class Event(Base):
    __tablename__ = "events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # Hash of (source_url + title) — used to prevent duplicate inserts
    external_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)

    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=True)
    short_description: Mapped[str] = mapped_column(String(300), nullable=True)

    start_datetime: Mapped[datetime] = mapped_column(DateTime, nullable=True, index=True)
    end_datetime: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    all_day: Mapped[bool] = mapped_column(Boolean, default=False)
    timezone_flag: Mapped[str] = mapped_column(String(50), nullable=True)  # set if non-ET detected

    location_name: Mapped[str] = mapped_column(String(300), nullable=True)
    location_address: Mapped[str] = mapped_column(String(500), nullable=True)
    latitude: Mapped[float] = mapped_column(Float, nullable=True)
    longitude: Mapped[float] = mapped_column(Float, nullable=True)

    source_url: Mapped[str] = mapped_column(String(1000), nullable=False)
    image_url: Mapped[str] = mapped_column(String(1000), nullable=True)
    registration_url: Mapped[str] = mapped_column(String(1000), nullable=True)
    is_free: Mapped[bool] = mapped_column(Boolean, nullable=True)
    tags: Mapped[list] = mapped_column(JSON, default=list)

    department_id: Mapped[int] = mapped_column(Integer, ForeignKey("departments.id"), nullable=False)
    category_id: Mapped[int] = mapped_column(Integer, ForeignKey("categories.id"), nullable=True)
    scrape_run_id: Mapped[int] = mapped_column(Integer, ForeignKey("scrape_runs.id"), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)

    department: Mapped["Department"] = relationship("Department", back_populates="events")  # noqa: F821
    category: Mapped["Category"] = relationship("Category", back_populates="events")  # noqa: F821
    scrape_run: Mapped["ScrapeRun"] = relationship("ScrapeRun", back_populates="events")  # noqa: F821

    def __repr__(self) -> str:
        return f"<Event id={self.id} title={self.title!r}>"
