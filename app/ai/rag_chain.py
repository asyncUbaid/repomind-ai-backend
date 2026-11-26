from langchain_core.output_parsers import StrOutputParser
from langchain_ollama import ChatOllama

from app.ai.prompts import RAG_PROMPT
from app.core.config import get_settings


class RAGChain:
    def __init__(self) -> None:
        settings = get_settings()
        self.chat = ChatOllama(
            model=settings.ollama_chat_model,
            base_url=settings.ollama_base_url,
            temperature=0.1,
            num_ctx=settings.ollama_chat_context_length,
            num_predict=settings.ollama_chat_max_tokens,
            timeout=settings.ollama_request_timeout_seconds,
        )
        self.chain = RAG_PROMPT | self.chat | StrOutputParser()

    def answer(self, question: str, context: str) -> str:
        return self.chain.invoke({"question": question, "context": context})
