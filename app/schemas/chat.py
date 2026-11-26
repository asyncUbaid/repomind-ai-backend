from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    conversation_id: int | None = None


class CitationResponse(BaseModel):
    file_path: str
    start_line: int
    end_line: int
    symbol_name: str | None = None


class ChatResponse(BaseModel):
    conversation_id: int
    answer: str
    citations: list[CitationResponse]


class MessageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    role: str
    content: str
    citations: list[CitationResponse]
    created_at: datetime


class ConversationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    created_at: datetime
    messages: list[MessageResponse] = []
