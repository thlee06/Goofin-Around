from datetime import datetime
from sqlalchemy import String, Integer, Float, DateTime, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class ScrapeRun(Base):
    __tablename__ = "scrape_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    department_id: Mapped[int] = mapped_column(Integer, ForeignKey("departments.id"), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    completed_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    # status: "running" | "success" | "partial" | "failed"
    status: Mapped[str] = mapped_column(String(20), default="running")
    events_found: Mapped[int] = mapped_column(Integer, default=0)
    events_new: Mapped[int] = mapped_column(Integer, default=0)
    events_updated: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[str] = mapped_column(Text, nullable=True)
    duration_seconds: Mapped[float] = mapped_column(Float, nullable=True)

    department: Mapped["Department"] = relationship("Department", back_populates="scrape_runs")  # noqa: F821
    events: Mapped[list["Event"]] = relationship("Event", back_populates="scrape_run")  # noqa: F821

    def __repr__(self) -> str:
        return f"<ScrapeRun dept={self.department_id} status={self.status}>"
