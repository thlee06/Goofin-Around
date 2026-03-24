from sqlalchemy import String, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class Category(Base):
    __tablename__ = "categories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    color_hex: Mapped[str] = mapped_column(String(7), default="#6B7280")  # Tailwind gray-500
    icon_name: Mapped[str] = mapped_column(String(100), nullable=True)

    events: Mapped[list["Event"]] = relationship("Event", back_populates="category")  # noqa: F821

    def __repr__(self) -> str:
        return f"<Category {self.slug}>"
