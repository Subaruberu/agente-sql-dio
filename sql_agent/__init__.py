"""Agente de IA que converte perguntas em linguagem natural para SQL (SQLite)."""

from .agent import AgentResponse, SQLAgent, SQLAgentError, extract_sql
from .database import Database, QueryResult, UnsafeQueryError
from .llm import LLMClient, LLMConfigurationError, OpenAICompatibleLLM

__version__ = "1.0.0"

__all__ = [
    "AgentResponse",
    "Database",
    "LLMClient",
    "LLMConfigurationError",
    "OpenAICompatibleLLM",
    "QueryResult",
    "SQLAgent",
    "SQLAgentError",
    "UnsafeQueryError",
    "extract_sql",
]
