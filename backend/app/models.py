"""
SQLAlchemy models — owned by Member 2.

Column names and attributes here are the contract Member 1's routes and
Member 5's activity feed already code against. Do not rename without a
coordinated PR, because routes.py does:

    db.query(Card).filter(Card.column_id == col.id).order_by(Card.position)
    Activity(action=..., card_title=..., from_column=..., to_column=..., message=...)

Entities
--------
BoardColumn : the three fixed MVP columns (todo / doing / done).
Card        : a task sitting in exactly one column, ordered by `position`.
Activity    : an audit row written for each successful create / move.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship, validates

from .database import Base

# Single source of truth for the column contract. routes.py/schemas.py keep
# their own copy; tests assert the two stay in sync.
COLUMN_IDS: tuple[str, ...] = ("todo", "doing", "done")

# Activity actions the MVP understands.
ACTIVITY_CREATED = "created"
ACTIVITY_MOVED = "moved"


def _uuid4_str() -> str:
    return str(uuid.uuid4())


def _utcnow() -> datetime:
    """Timezone-aware UTC now.

    `datetime.utcnow()` is deprecated in 3.12+ and returns a naive datetime,
    which serializes without an offset and makes activity ordering ambiguous.
    """
    return datetime.now(timezone.utc)


class BoardColumn(Base):
    __tablename__ = "board_columns"

    # Human-readable slug ("todo") used as the primary key so the API and the
    # WebSocket payloads can carry it directly, per the card data shape.
    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    title: Mapped[str] = mapped_column(String(120), nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    cards: Mapped[list["Card"]] = relationship(
        back_populates="column",
        cascade="all, delete-orphan",
        order_by="(Card.position, Card.created_at)",
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<BoardColumn {self.id!r} pos={self.position}>"


class Card(Base):
    __tablename__ = "cards"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid4_str)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")

    # A card cannot exist in a column that does not exist. SQLite enforces this
    # only because database.py turns on PRAGMA foreign_keys.
    column_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("board_columns.id", ondelete="RESTRICT"), nullable=False
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow
    )

    column: Mapped[BoardColumn] = relationship(back_populates="cards")

    __table_args__ = (
        # Mirrors the validation in schemas.CardCreate: a blank title is not a
        # valid card even if someone writes to the DB directly.
        CheckConstraint("length(trim(title)) > 0", name="ck_cards_title_not_blank"),
        CheckConstraint("position >= 0", name="ck_cards_position_non_negative"),
        # Every board read filters by column and sorts by position.
        Index("ix_cards_column_position", "column_id", "position"),
    )

    @validates("title")
    def _strip_title(self, _key: str, value: str) -> str:
        return value.strip() if isinstance(value, str) else value

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<Card {self.id!r} {self.title!r} in={self.column_id} pos={self.position}>"


class Activity(Base):
    """Append-only history shown in the activity panel."""

    __tablename__ = "activities"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid4_str)
    action: Mapped[str] = mapped_column(String(20), nullable=False)  # created | moved

    # Intentionally NOT a ForeignKey: the activity feed is an audit log and
    # should survive even if cards are ever deleted in a later iteration.
    card_id: Mapped[str] = mapped_column(String(36), nullable=False)
    card_title: Mapped[str] = mapped_column(String(200), nullable=False)

    # NULL for "created" (the card had no previous column).
    from_column: Mapped[str | None] = mapped_column(String(32), nullable=True)
    to_column: Mapped[str] = mapped_column(String(32), nullable=False)

    message: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )

    __table_args__ = (
        CheckConstraint(
            "action IN ('created', 'moved')", name="ck_activities_action_valid"
        ),
        # Activity list is always "newest first".
        Index("ix_activities_created_at", "created_at"),
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<Activity {self.action} {self.card_title!r}>"
