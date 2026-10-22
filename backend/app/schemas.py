"""
Member 1 — API and validation
Owns: backend/app/schemas.py
Build: Pydantic schemas + validation for board/card/activity flows.
"""
from pydantic import BaseModel, field_validator, Field
from typing import Optional, List
from datetime import datetime

# MVP column contract — must match Team Build Guide
VALID_COLUMNS = {
    "todo": "To Do",
    "doing": "In Progress",
    "done": "Done"
}
VALID_COLUMN_IDS = list(VALID_COLUMNS.keys())

# ---------- Card I/O ----------

class CardCreate(BaseModel):
    title: str = Field(..., description="Card title, required and non-empty")
    description: Optional[str] = Field(default="", description="Optional notes")
    column_id: str = Field(default="todo", description="Target column: todo | doing | done")

    @field_validator("title")
    @classmethod
    def title_must_not_be_blank(cls, v: str):
        if v is None or not v.strip():
            raise ValueError("Card title is required")
        # normalize: trim but preserve inner spaces
        return v.strip()

    @field_validator("column_id")
    @classmethod
    def column_must_be_valid(cls, v: str):
        if v not in VALID_COLUMN_IDS:
            raise ValueError(f"Invalid column_id. Must be one of: {', '.join(VALID_COLUMN_IDS)}")
        return v

    @field_validator("description")
    @classmethod
    def normalize_description(cls, v: Optional[str]):
        if v is None:
            return ""
        return v


class CardMove(BaseModel):
    column_id: str = Field(..., description="Destination column")
    position: int = Field(..., ge=0, description="Zero-based position in destination column")

    @field_validator("column_id")
    @classmethod
    def column_must_be_valid(cls, v: str):
        if v not in VALID_COLUMN_IDS:
            raise ValueError(f"Invalid column_id. Must be one of: {', '.join(VALID_COLUMN_IDS)}")
        return v


class CardResponse(BaseModel):
    id: str
    title: str
    description: str
    column_id: str
    position: int

    class Config:
        from_attributes = True


# ---------- Board ----------

class ColumnResponse(BaseModel):
    id: str
    title: str
    cards: List[CardResponse]

    class Config:
        from_attributes = True


class BoardResponse(BaseModel):
    id: str
    title: str
    columns: List[ColumnResponse]


# ---------- Activity ----------

class ActivityResponse(BaseModel):
    id: str
    action: str
    card_id: str
    card_title: str
    from_column: Optional[str] = None
    to_column: str
    message: str
    created_at: datetime

    class Config:
        from_attributes = True
