"""Agente de IA que converte perguntas em linguagem natural para SQL."""

from .agent import AgentResponse, SQLAgent, SQLAgentError, extract_sql
from .config import Settings, load_settings
from .database import (
    Database,
    DatabaseConfigurationError,
    DatabaseConnectionError,
    MySQLDatabase,
    QueryExecutionError,
    QueryResult,
    SQLiteDatabase,
    UnsafeQueryError,
    create_database,
    validate_sql,
)
from .llm import LLMClient, LLMConfigurationError, OpenAICompatibleLLM

__version__ = "1.1.0"

__all__ = [
    "AgentResponse",
    "Database",
    "DatabaseConfigurationError",
    "DatabaseConnectionError",
    "LLMClient",
    "LLMConfigurationError",
    "MySQLDatabase",
    "OpenAICompatibleLLM",
    "QueryExecutionError",
    "QueryResult",
    "SQLAgent",
    "SQLAgentError",
    "SQLiteDatabase",
    "Settings",
    "UnsafeQueryError",
    "create_database",
    "extract_sql",
    "load_settings",
    "validate_sql",
]
