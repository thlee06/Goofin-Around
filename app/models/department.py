from datetime import datetime
from sqlalchemy import String, Boolean, Integer, DateTime
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class Department(Base):
    __tablename__ = "departments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    school: Mapped[str] = mapped_column(String(200), nullable=True)
    website_url: Mapped[str] = mapped_column(String(500), nullable=False)
    scraper_class: Mapped[str] = mapped_column(String(200), nullable=False)
    scrape_interval_hours: Mapped[int] = mapped_column(Integer, default=6)
    last_scraped_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    logo_url: Mapped[str] = mapped_column(String(500), nullable=True)

    events: Mapped[list["Event"]] = relationship("Event", back_populates="department")  # noqa: F821
    scrape_runs: Mapped[list["ScrapeRun"]] = relationship("ScrapeRun", back_populates="department")  # noqa: F821

    def __repr__(self) -> str:
        return f"<Department {self.slug}>"
