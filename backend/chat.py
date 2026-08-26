"""One assistant turn, run against memory the server owns.

The important change from a stateless chat endpoint: the client posts a single
message, not a transcript. History is read back from the caller's own rows, so
what the model sees cannot be rewritten by editing a request in devtools, and
it survives a refresh, a new tab, or a different machine.
"""

from __future__ import annotations

import json
from typing import Iterator

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.auth import current_user
from backend.config import MAX_COMPLETION_TOKENS
from backend.credits import authorise_turn, charge_usage, finalise_usage
from backend.db import SessionLocal, get_db, utcnow
from backend.models import Conversation, Message, User
from backend.pricing import ModelPolicy, policy_for
from backend.providers import (
    ChatMessage,
    ModelInfo,
    Provider,
    Usage,
    get_provider,
    list_providers,
)
from backend.schemas import ChatReply, ChatTurnRequest, MessageOut
from backend.store import memory, owned_conversation, title_from

router = APIRouter(tags=["chat"])


# --- helpers ---------------------------------------------------------------


def _resolve(payload: ChatTurnRequest, user: User) -> tuple[Provider, ModelInfo, ModelPolicy]:
    """Everything that can refuse a turn, before anything is written.

    Order matters for what the user is told: a provider that is down is a 503
    whoever asks, but "locked" and "out of credits" are about *this* account,
    so they come last and only once the model is known to exist.
    """
    provider = get_provider(payload.provider)
    if provider is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Unknown provider '{payload.provider}'")

    availability = provider.status()
    if not availability.available:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            availability.detail or f"{provider.label} is not available",
        )

    model_id = payload.model.strip()
    if not model_id:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "A model id is required")

    model = provider.find_model(model_id)
    if model is None:
        # Only catalogued models are priced, so only catalogued models run.
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, f"{provider.label} has no model '{model_id}'"
        )

    policy = policy_for(provider.id, model)
    authorise_turn(user, model, policy)
    return provider, model, policy


def _settle(
    *,
    user_id: str,
    conversation_id: str | None,
    saved: dict | None,
    provider: Provider,
    model_id: str,
    policy: ModelPolicy,
    turns: list[ChatMessage],
    text: str,
    usage: Usage | None,
) -> dict | None:
    """Bill a finished turn — including one the user stopped or that died
    halfway, since the vendor metered those too. A turn that produced nothing
    at all (the request itself was rejected) costs nothing."""
    if not text and usage is None:
        return None
    message_id = int(saved["id"]) if saved and saved.get("id") else None
    return charge_usage(
        user_id=user_id,
        conversation_id=conversation_id,
        message_id=message_id,
        provider_id=provider.id,
        model_id=model_id,
        usage=finalise_usage(turns, text, usage),
        policy=policy,
    )


def _rewind_to(db: Session, conversation: Conversation, message_id: str) -> None:
    """Delete an assistant turn and everything after it.

    Message ids are a monotonic sequence, so "after" is simply a larger id —
    which is why retrying a reply from the middle of a thread leaves a coherent
    history rather than orphaned turns hanging off the end.
    """
    try:
        cutoff = int(message_id)
    except ValueError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such message")

    target = db.get(Message, cutoff)
    if target is None or target.conversation_id != conversation.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such message")

    rows = (
        db.execute(
            select(Message).where(
                Message.conversation_id == conversation.id, Message.id >= cutoff
            )
        )
        .scalars()
        .all()
    )
    for row in rows:
        db.delete(row)


def _open_turn(
    db: Session, user: User, payload: ChatTurnRequest
) -> tuple[Conversation, list[ChatMessage], Message | None, bool]:
    """Commit the user's half of the turn and return what to send upstream."""
    is_new = payload.conversation_id is None
    if is_new:
        conversation = Conversation(user_id=user.id)
        db.add(conversation)
    else:
        conversation = owned_conversation(db, user, payload.conversation_id)

    if payload.system is not None:
        conversation.system_prompt = payload.system.strip()

    user_message: Message | None = None
    if payload.regenerate_from:
        _rewind_to(db, conversation, payload.regenerate_from)
    else:
        user_message = Message(
            conversation=conversation, role="user", content=payload.content.strip()
        )
        db.add(user_message)
        if not conversation.title:
            conversation.title = title_from(payload.content)

    conversation.provider = payload.provider
    conversation.model = payload.model
    conversation.updated_at = utcnow()
    db.commit()

    return conversation, memory(db, conversation), user_message, is_new


def _record_reply(
    conversation_id: str,
    text: str,
    error: str | None,
    provider_id: str,
    model: str,
) -> dict | None:
    """Persist the assistant's half of the turn on its own session.

    A streaming response body outlives the request scope, so the session from
    `Depends(get_db)` is already closed by the time this runs.
    """
    if not text and not error:
        return None

    content = f"{text}\n\n{error}" if text and error else (text or error or "")

    with SessionLocal() as db:
        message = Message(
            conversation_id=conversation_id,
            role="assistant",
            content=content,
            provider=provider_id,
            model=model,
            # A turn that errored still shows in the thread but is left out of
            # memory: half an answer with a stack trace glued to it is worse
            # context than no answer at all.
            failed=bool(error),
        )
        db.add(message)

        conversation = db.get(Conversation, conversation_id)
        if conversation is not None:
            conversation.updated_at = utcnow()
        db.commit()

        return MessageOut.model_validate(message).model_dump(mode="json", by_alias=True)


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


def _dump(message: Message | None) -> dict | None:
    if message is None:
        return None
    return MessageOut.model_validate(message).model_dump(mode="json", by_alias=True)


# --- routes ----------------------------------------------------------------


@router.post("/api/chat/stream")
def chat_stream(
    payload: ChatTurnRequest,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    """Stream one turn as Server-Sent Events.

        meta   once, up front — the thread id (new threads are created here)
        token  many — a chunk of the answer
        error  at most once — the provider failed
        done   once — the stored assistant message, plus what the turn cost

    `meta` arriving first is what lets the browser swap its URL to /chat/<id>
    before a single token has been painted.
    """
    provider, model, policy = _resolve(payload, user)
    conversation, turns, user_message, is_new = _open_turn(db, user, payload)

    # Snapshot everything the generator needs: it runs after the request scope
    # (and this session) has gone away.
    user_id = user.id
    conversation_id = conversation.id
    meta = {
        "conversationId": conversation_id,
        "title": conversation.title or "New thread",
        "isNew": is_new,
        "userMessage": _dump(user_message),
    }

    def events() -> Iterator[str]:
        yield _sse("meta", meta)

        text = ""
        usage: Usage | None = None
        error: str | None = None
        saved: dict | None = None
        bill: dict | None = None
        try:
            try:
                for item in provider.stream(
                    model.id, turns, max_output_tokens=MAX_COMPLETION_TOKENS
                ):
                    if isinstance(item, Usage):
                        usage = item
                        continue
                    text += item
                    yield _sse("token", {"text": item})
            except Exception as exc:  # noqa: BLE001 - reported to the client as-is
                error = f"{provider.label} request failed: {exc}"
        finally:
            # Runs on the happy path *and* when the browser hangs up mid-stream,
            # so a stopped answer keeps whatever had already arrived — and is
            # paid for, because the vendor metered it either way.
            saved = _record_reply(conversation_id, text, error, provider.id, model.id)
            bill = _settle(
                user_id=user_id,
                conversation_id=conversation_id,
                saved=saved,
                provider=provider,
                model_id=model.id,
                policy=policy,
                turns=turns,
                text=text,
                usage=usage,
            )

        if error:
            yield _sse("error", {"message": error})
        yield _sse("done", {"conversationId": conversation_id, "message": saved, "usage": bill})

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/api/chat", response_model=ChatReply)
def chat(
    payload: ChatTurnRequest,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    """Non-streaming twin of the above, for scripts and integration tests."""
    provider, model, policy = _resolve(payload, user)
    conversation, turns, _user_message, _is_new = _open_turn(db, user, payload)

    text, usage, error = "", None, None
    try:
        text, usage = provider.complete(model.id, turns, max_output_tokens=MAX_COMPLETION_TOKENS)
    except Exception as exc:  # noqa: BLE001
        error = f"{provider.label} request failed: {exc}"

    saved = _record_reply(conversation.id, text, error, provider.id, model.id)
    bill = _settle(
        user_id=user.id,
        conversation_id=conversation.id,
        saved=saved,
        provider=provider,
        model_id=model.id,
        policy=policy,
        turns=turns,
        text=text,
        usage=usage,
    )
    if error:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, error)
    if saved is None:
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY, f"{provider.label} returned an empty response"
        )

    return ChatReply(
        conversation_id=conversation.id,
        title=conversation.title or "New thread",
        message=MessageOut.model_validate(saved),
        usage=bill,
    )


@router.post("/response")
def legacy_response(payload: dict, user: User = Depends(current_user)):
    """Legacy single-shot endpoint — first available free model, no memory.

    Metered like everything else: a route that talks to a vendor and does not
    touch the balance would be a free way around the paywall.
    """
    query = str(payload.get("query", "")).strip()
    if not query:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "A query is required")

    choice: tuple[Provider, ModelInfo, ModelPolicy] | None = None
    for candidate in list_providers():
        if not candidate.status().available:
            continue
        for info in candidate.models():
            policy = policy_for(candidate.id, info)
            if not policy.premium:
                choice = (candidate, info, policy)
                break
        if choice:
            break
    if choice is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "No free model is available")

    provider, model, policy = choice
    authorise_turn(user, model, policy)

    turns = [ChatMessage(role="user", content=query)]
    try:
        answer, usage = provider.complete(model.id, turns, max_output_tokens=MAX_COMPLETION_TOKENS)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"LLM request failed: {exc}")

    bill = _settle(
        user_id=user.id,
        conversation_id=None,
        saved=None,
        provider=provider,
        model_id=model.id,
        policy=policy,
        turns=turns,
        text=answer,
        usage=usage,
    )
    return {"response": answer, "usage": bill}
