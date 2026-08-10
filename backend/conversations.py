"""Thread CRUD — the sidebar's backend.

Every route depends on `current_user`, and every query filters on that user's
id, so there is no request shape that reaches another account's threads.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from backend.auth import current_user
from backend.db import get_db, utcnow
from backend.models import Conversation, User
from backend.schemas import ConversationDetail, ConversationOut, RenameRequest
from backend.store import (
    count_messages,
    detail,
    list_summaries,
    owned_conversation,
    summarise,
)

router = APIRouter(prefix="/api/conversations", tags=["conversations"])


@router.get("", response_model=list[ConversationOut])
def index(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return list_summaries(db, user)


@router.post("", response_model=ConversationOut, status_code=status.HTTP_201_CREATED)
def create(user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Start an empty thread up front.

    Usually unnecessary — sending a message with no `conversationId` creates one
    — but handy for a "new thread" button that wants a URL immediately.
    """
    conversation = Conversation(user_id=user.id, title="New thread")
    db.add(conversation)
    db.commit()
    return summarise(conversation, 0)


@router.get("/{conversation_id}", response_model=ConversationDetail)
def show(
    conversation_id: str,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    """Full thread with its messages — this is what "memory" looks like to the
    UI when a returning user reopens a conversation."""
    return detail(db, owned_conversation(db, user, conversation_id))


@router.patch("/{conversation_id}", response_model=ConversationOut)
def rename(
    conversation_id: str,
    payload: RenameRequest,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    conversation = owned_conversation(db, user, conversation_id)
    conversation.title = payload.title.strip()
    conversation.updated_at = utcnow()
    db.commit()
    return summarise(conversation, count_messages(db, conversation.id))


@router.delete("/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
def destroy(
    conversation_id: str,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    # Messages go with it — the relationship cascades.
    db.delete(owned_conversation(db, user, conversation_id))
    db.commit()
