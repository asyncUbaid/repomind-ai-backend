from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.rag_chain import RAGChain
from app.api.routes.auth import get_current_user
from app.api.routes.repositories import owner_repository
from app.ai.models import create_embeddings
from app.db.database import get_db
from app.db.models import Conversation, Message, Repository, User
from app.schemas.chat import ChatRequest, ChatResponse, CitationResponse, ConversationResponse
from app.services.retrieval_service import RetrievalService

router = APIRouter(tags=["chat"])


def format_context(results: list[dict]) -> str:
    parts = []
    for result in results:
        payload = result["payload"]
        parts.append(
            f"File: {payload.get('file_path')}\n"
            f"Lines: {payload.get('start_line')}-{payload.get('end_line')}\n"
            f"Symbol: {payload.get('symbol_name') or 'none'}\n"
            f"Content:\n{payload.get('content', '')}"
        )
    return "\n\n".join(parts)


def generated_citations(results: list[dict]) -> list[CitationResponse]:
    citations: list[CitationResponse] = []
    seen: set[tuple[str, int, int, str | None]] = set()
    for result in results:
        payload = result["payload"]
        key = (
            str(payload["file_path"]),
            int(payload["start_line"]),
            int(payload["end_line"]),
            payload.get("symbol_name"),
        )
        if key in seen:
            continue
        seen.add(key)
        citations.append(
            CitationResponse(
                file_path=key[0],
                start_line=key[1],
                end_line=key[2],
                symbol_name=key[3],
            )
        )
    return citations


@router.post("/api/repositories/{repository_id}/chat", response_model=ChatResponse)
def chat(
    repository_id: int,
    payload: ChatRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ChatResponse:
    repository = owner_repository(repository_id, current_user, db)
    if not repository.latest_commit_sha:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Repository has not been indexed for a commit",
        )

    conversation: Conversation | None = None
    if payload.conversation_id is not None:
        conversation = db.scalar(
            select(Conversation).where(
                Conversation.id == payload.conversation_id,
                Conversation.user_id == current_user.id,
                Conversation.repository_id == repository.id,
            )
        )
        if conversation is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")
    if conversation is None:
        title = payload.message.strip().splitlines()[0][:80]
        conversation = Conversation(
            user_id=current_user.id,
            repository_id=repository.id,
            title=title,
        )
        db.add(conversation)
        db.flush()

    db.add(
        Message(
            conversation_id=conversation.id,
            role="user",
            content=payload.message,
            citations=[],
        )
    )

    retrieval = RetrievalService(create_embeddings())
    results = retrieval.retrieve(
        payload.message,
        repository_id=repository.id,
        commit_sha=repository.latest_commit_sha,
        limit=4,
    )
    citations = generated_citations(results)

    if not results:
        answer = (
            "I could not find sufficient indexed repository context to answer this question. "
            "Index the repository and verify that relevant source files are included."
        )
    else:
        try:
            answer = RAGChain().answer(payload.message, format_context(results))
        except Exception:
            answer = (
                "The local AI model is currently unavailable or could not complete the request. "
                "No repository answer was inferred beyond the retrieved source context."
            )

    db.add(
        Message(
            conversation_id=conversation.id,
            role="assistant",
            content=answer,
            citations=[citation.model_dump() for citation in citations],
        )
    )
    db.commit()
    db.refresh(conversation)
    return ChatResponse(
        conversation_id=conversation.id,
        answer=answer,
        citations=citations,
    )


@router.get("/api/conversations", response_model=list[ConversationResponse])
def list_conversations(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[Conversation]:
    return list(
        db.scalars(
            select(Conversation)
            .where(Conversation.user_id == current_user.id)
            .order_by(Conversation.created_at.desc())
        )
    )


@router.get("/api/conversations/{conversation_id}", response_model=ConversationResponse)
def get_conversation(
    conversation_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Conversation:
    conversation = db.scalar(
        select(Conversation).where(
            Conversation.id == conversation_id,
            Conversation.user_id == current_user.id,
        )
    )
    if conversation is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")
    return conversation
