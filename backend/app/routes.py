"""
Member 1 — API and validation
Owns: backend/app/routes.py
Implements:
  GET /health
  GET /api/boards/demo
  POST /api/boards/demo/cards  -> 201 + broadcast card.created
  PATCH /api/cards/{card_id}/move -> broadcast card.moved
  DELETE /api/cards/{card_id} -> audit, delete, and broadcast card.deleted
  GET /api/boards/demo/activity

Validation & errors delegate to schemas + explicit HTTPExceptions
so UI receives {"detail":"..."} as per guide.

Persistence is via Member 2's models (backend/app/models.py & database.py)
Live updates are via Member 4's manager.broadcast(event)
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import asc
import uuid
from typing import List

from .database import get_db
from .models import BoardColumn, Card, Activity
from .schemas import (
    CardCreate, CardMove, CardResponse,
    BoardResponse, ColumnResponse, ActivityResponse,
    VALID_COLUMNS
)
from .realtime import manager

router = APIRouter()

# ---- Helpers ----

def _card_to_dict(card: Card) -> dict:
    return {
        "id": card.id,
        "title": card.title,
        "description": card.description or "",
        "column_id": card.column_id,
        "position": card.position,
    }

def _reorder_column(db: Session, column_id: str):
    """Re-normalize positions to 0..n-1 ordered by current position."""
    cards = db.query(Card).filter(Card.column_id == column_id).order_by(asc(Card.position), asc(Card.created_at)).all()
    for idx, c in enumerate(cards):
        c.position = idx
    db.commit()

def _next_position_in_column(db: Session, column_id: str) -> int:
    max_pos = db.query(Card).filter(Card.column_id == column_id).count()
    return max_pos

# ---- Routes ----

@router.get("/health")
def health():
    return {"status": "ok"}

@router.get("/api/boards/demo", response_model=BoardResponse)
def get_board(db: Session = Depends(get_db)):
    """
    Board with columns and each column's cards (ordered by position)
    """
    columns = db.query(BoardColumn).order_by(asc(BoardColumn.position)).all()
    if not columns:
        # Seed fallback if init_db not called (e.g., test DB)
        for cfg in [
            {"id": "todo", "title": "To Do", "position": 0},
            {"id": "doing", "title": "In Progress", "position": 1},
            {"id": "done", "title": "Done", "position": 2},
        ]:
            db.add(BoardColumn(**cfg))
        db.commit()
        columns = db.query(BoardColumn).order_by(asc(BoardColumn.position)).all()

    # Build response
    column_payloads = []
    for col in columns:
        cards = (
            db.query(Card)
            .filter(Card.column_id == col.id)
            .order_by(asc(Card.position), asc(Card.created_at))
            .all()
        )
        card_responses = [
            CardResponse(
                id=c.id, title=c.title, description=c.description or "",
                column_id=c.column_id, position=c.position
            ) for c in cards
        ]
        column_payloads.append(ColumnResponse(id=col.id, title=col.title, cards=card_responses))

    return BoardResponse(id="demo", title="Demo Board", columns=column_payloads)


@router.post("/api/boards/demo/cards", response_model=CardResponse, status_code=status.HTTP_201_CREATED)
async def create_card(payload: CardCreate, db: Session = Depends(get_db)):
    """
    Create a card in demo board.
    - validates via CardCreate (422 if blank title / bad column)
    - appends to end of target column
    - logs activity
    - broadcasts card.created after commit
    """
    # Double-check column exists in DB (not just enum)
    col = db.query(BoardColumn).filter(BoardColumn.id == payload.column_id).first()
    if not col:
        raise HTTPException(status_code=422, detail=f"Invalid column_id. Must be one of: todo, doing, done")

    position = _next_position_in_column(db, payload.column_id)

    new_card = Card(
        id=str(uuid.uuid4()),
        title=payload.title,
        description=payload.description or "",
        column_id=payload.column_id,
        position=position,
    )
    db.add(new_card)

    # Activity log
    activity = Activity(
        id=str(uuid.uuid4()),
        action="created",
        card_id=new_card.id,
        card_title=new_card.title,
        from_column=None,
        to_column=new_card.column_id,
        message=f"Created '{new_card.title}' in {VALID_COLUMNS.get(new_card.column_id, new_card.column_id)}"
    )
    db.add(activity)

    db.commit()
    db.refresh(new_card)

    # Broadcast after successful commit (Member 4 contract)
    card_dict = _card_to_dict(new_card)
    try:
        await manager.broadcast({"type": "card.created", "card": card_dict})
    except Exception:
        # broadcast failure must not fail the request
        pass

    return CardResponse(**card_dict)


@router.patch("/api/cards/{card_id}/move", response_model=CardResponse)
async def move_card(card_id: str, payload: CardMove, db: Session = Depends(get_db)):
    """
    Move a card to another column/position.
    - 404 if card not found
    - 422 if column invalid
    - updates column_id + position
    - reorders affected columns
    - logs activity + broadcasts card.moved
    """
    card: Card | None = db.query(Card).filter(Card.id == card_id).first()
    if not card:
        raise HTTPException(status_code=404, detail="Card not found")

    # Validate target column exists
    target_col = db.query(BoardColumn).filter(BoardColumn.id == payload.column_id).first()
    if not target_col:
        raise HTTPException(status_code=422, detail=f"Invalid column_id. Must be one of: todo, doing, done")

    from_column = card.column_id
    to_column = payload.column_id
    target_position = payload.position

    # Clamp position to valid range in target column
    # If moving within same column, count excludes itself for clamping
    existing_in_target = db.query(Card).filter(Card.column_id == to_column, Card.id != card.id).all()
    max_allowed = len(existing_in_target)
    if target_position > max_allowed:
        target_position = max_allowed

    # Capture old ordering needs:
    source_column_id = card.column_id

    # Perform move: shift cards in target column to make room
    # Increment positions >= target_position for other cards in target
    if from_column != to_column:
        # Make room in target column
        for c in existing_in_target:
            if c.position >= target_position:
                c.position += 1
        card.column_id = to_column
        card.position = target_position
    else:
        # Same-column reorder
        old_pos = card.position
        if target_position == old_pos:
            pass  # no-op
        elif target_position < old_pos:
            # moving up: shift cards between target and old-1 down
            for c in existing_in_target:
                if target_position <= c.position < old_pos:
                    c.position += 1
            card.position = target_position
        else:  # target > old
            for c in existing_in_target:
                if old_pos < c.position <= target_position:
                    c.position -= 1
            card.position = target_position

    # Persist move
    db.commit()
    db.refresh(card)

    # Re-normalize both columns to ensure 0..n-1 continuity
    # (reorder helper commits again)
    _reorder_column(db, to_column)
    if from_column != to_column:
        _reorder_column(db, source_column_id)
        db.refresh(card)

    # Activity log for move
    activity = Activity(
        id=str(uuid.uuid4()),
        action="moved",
        card_id=card.id,
        card_title=card.title,
        from_column=from_column,
        to_column=to_column,
        message=f"Moved '{card.title}' from {VALID_COLUMNS.get(from_column, from_column)} to {VALID_COLUMNS.get(to_column, to_column)}"
    )
    db.add(activity)
    db.commit()

    card_dict = _card_to_dict(card)
    try:
        await manager.broadcast({"type": "card.moved", "card": card_dict})
    except Exception:
        pass

    return CardResponse(**card_dict)


@router.delete("/api/cards/{card_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_card(card_id: str, db: Session = Depends(get_db)):
    """Delete a card, append a durable activity record, and notify clients."""
    card = db.query(Card).filter(Card.id == card_id).first()
    if not card:
        raise HTTPException(status_code=404, detail="Card not found")

    deleted_card = _card_to_dict(card)
    column_id = card.column_id
    column_title = VALID_COLUMNS.get(column_id, column_id)
    activity = Activity(
        id=str(uuid.uuid4()),
        action="deleted",
        card_id=card.id,
        card_title=card.title,
        from_column=column_id,
        # For a deletion, to_column records the last column occupied. This keeps
        # the existing ActivityResponse contract non-nullable.
        to_column=column_id,
        message=f"Deleted '{card.title}' from {column_title}",
    )
    db.add(activity)
    db.delete(card)
    db.flush()  # apply the delete inside this transaction before querying remaining cards

    # Compact positions in the source column before the same commit so delete,
    # activity, and reorder are persisted atomically.
    remaining = (
        db.query(Card)
        .filter(Card.column_id == column_id)
        .order_by(asc(Card.position), asc(Card.created_at))
        .all()
    )
    for position, remaining_card in enumerate(remaining):
        remaining_card.position = position
    db.commit()

    try:
        await manager.broadcast({"type": "card.deleted", "card": deleted_card})
    except Exception:
        # A disconnected subscriber must not turn a successful delete into an API error.
        pass

    return None


@router.get("/api/boards/demo/activity", response_model=List[ActivityResponse])
def get_activity(db: Session = Depends(get_db)):
    """
    Newest activity records first (limit 50 for MVP)
    """
    activities = (
        db.query(Activity)
        .order_by(Activity.created_at.desc())
        .limit(50)
        .all()
    )
    return [
        ActivityResponse(
            id=a.id,
            action=a.action,
            card_id=a.card_id,
            card_title=a.card_title,
            from_column=a.from_column,
            to_column=a.to_column,
            message=a.message,
            created_at=a.created_at,
        )
        for a in activities
    ]
