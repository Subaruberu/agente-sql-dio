"""Interface web (Streamlit) do agente SQL.

Execute com:
    streamlit run app.py

A conexão com o banco é aberta por execução do script e fechada no fim, em vez
de ser compartilhada entre threads: o Streamlit pode executar o script em
threads diferentes, e conexões SQLite/MySQL não são thread-safe.
"""

from __future__ import annotations

import os
from decimal import Decimal
from typing import Any

import streamlit as st

from sql_agent.agent import SQLAgent, SQLAgentError
from sql_agent.config import Settings, load_settings
from sql_agent.database import (
    Database,
    DatabaseConfigurationError,
    DatabaseConnectionError,
    create_database,
)
from sql_agent.llm import LLMConfigurationError, OpenAICompatibleLLM

EXEMPLOS = [
    "Quais foram os 5 clientes que mais gastaram em 2026?",
    "Qual o faturamento por categoria, sem contar pedidos cancelados?",
    "Quais clientes nunca fizeram pedidos?",
    "Qual vendedor teve o maior número de pedidos entregues?",
    "Qual o ticket médio dos pedidos feitos pelo site?",
    "Quais produtos estão com estoque abaixo de 20 unidades?",
    "Qual a evolução mensal do faturamento em 2026?",
    "Qual cidade concentra mais clientes do segmento Tecnologia?",
]

DATABASE_ERRORS = (DatabaseConnectionError, DatabaseConfigurationError, FileNotFoundError)


def _load_streamlit_secrets() -> None:
    """Copia segredos do Streamlit Cloud para o ambiente, sem sobrescrever o .env."""

    try:
        for key, value in st.secrets.items():
            if key not in os.environ and isinstance(value, (str, int, float)):
                os.environ[key] = str(value)
    except Exception:  # noqa: BLE001 - não existe secrets.toml no uso local
        pass


def _open_database(settings: Settings) -> Database:
    return create_database(settings)


def _display_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Converte Decimal para float para a tabela ficar legível na interface."""

    return [
        {
            key: float(value) if isinstance(value, Decimal) else value
            for key, value in row.items()
        }
        for row in rows
    ]


def _render_payload(payload: dict[str, Any]) -> None:
    st.code(payload["sql"], language="sql")

    rows = payload.get("linhas", [])
    if rows:
        st.dataframe(_display_rows(rows), width="stretch", hide_index=True)
    else:
        st.info("A consulta não retornou registros.")

    details = (
        f"{payload['total_linhas']} linha(s) · {payload['tempo_ms']} ms · "
        f"tentativa(s): {payload['tentativas']}"
    )
    if payload.get("truncado"):
        details += " · resultado truncado"
    st.caption(details)

    if payload.get("explicacao"):
        st.markdown(payload["explicacao"])

    for warning in payload.get("avisos", []):
        st.warning(warning)


def _render_history() -> None:
    for item in st.session_state.history:
        if item["role"] == "user":
            st.chat_message("user").markdown(item["content"])
            continue

        with st.chat_message("assistant"):
            if item.get("error"):
                st.error(item["error"])
            else:
                _render_payload(item["payload"])


def _sidebar(
    settings: Settings, database_label: str, database_schema: str, explain: bool
) -> bool:
    with st.sidebar:
        st.header("Configuração")
        st.markdown(f"**Banco:** {database_label}")
        st.markdown(f"**Modelo:** `{settings.model}`")
        st.caption(
            f"Máximo de {settings.max_rows} linhas por consulta · "
            f"{settings.max_retries} tentativa(s) de correção"
        )

        explain = st.toggle("Gerar explicação em linguagem natural", value=explain)

        if st.button("Limpar conversa", width="stretch"):
            st.session_state.history = []
            st.rerun()

        with st.expander("Ver esquema do banco"):
            st.code(database_schema, language="sql")

        st.divider()
        st.subheader("Perguntas de exemplo")
        exemplo = st.selectbox(
            "Escolha uma pergunta", EXEMPLOS, index=None, placeholder="Selecione..."
        )
        if st.button("Perguntar exemplo", disabled=exemplo is None, width="stretch"):
            st.session_state.pending_question = exemplo
            st.rerun()

        st.divider()
        st.caption(
            "Projeto do desafio DIO. As consultas são executadas em uma conexão "
            "somente leitura; ainda assim, use um usuário de banco com permissão de SELECT."
        )

    return bool(explain)


def main() -> None:
    st.set_page_config(
        page_title="Agente SQL — DioBank",
        page_icon="🤖",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    _load_streamlit_secrets()

    st.title("🤖 Agente SQL — DioBank")
    st.caption(
        "Faça uma pergunta em português: o agente gera o SQL, valida, consulta o banco "
        "e explica o resultado."
    )

    try:
        settings = load_settings()
    except ValueError as exc:
        st.error(f"Configuração inválida: {exc}")
        st.stop()

    # Abre e fecha apenas para ler o rótulo e o esquema do banco.
    try:
        with _open_database(settings) as database:
            database_label = database.label
            database_schema = database.schema()
    except FileNotFoundError:
        st.error(
            "Banco SQLite não encontrado. Rode `python scripts/create_sample_db.py` "
            "ou configure o MySQL no `.env`."
        )
        st.stop()
    except DATABASE_ERRORS as exc:
        st.error(str(exc))
        st.info("Confira as variáveis de conexão no `.env` (veja o README).")
        st.stop()

    if "history" not in st.session_state:
        st.session_state.history = []
    if "explain" not in st.session_state:
        st.session_state.explain = True

    st.session_state.explain = _sidebar(
        settings, database_label, database_schema, st.session_state.explain
    )

    try:
        llm = OpenAICompatibleLLM(
            model=settings.model,
            api_key=settings.api_key,
            base_url=settings.base_url,
            temperature=settings.temperature,
        )
    except LLMConfigurationError as exc:
        st.error(str(exc))
        st.code(
            "LLM_MODEL=gpt-4o-mini\n"
            "LLM_API_KEY=sua-chave\n"
            "# LLM_BASE_URL=https://api.groq.com/openai/v1",
            language="bash",
        )
        st.stop()

    _render_history()

    pending = st.session_state.pop("pending_question", None)
    question = st.chat_input("Pergunte algo sobre os dados...") or pending
    if not question:
        return

    st.session_state.history.append({"role": "user", "content": question})
    st.chat_message("user").markdown(question)

    with st.chat_message("assistant"):
        with st.spinner("Gerando SQL, validando e consultando o banco..."):
            try:
                with _open_database(settings) as database:
                    agent = SQLAgent(database, llm, max_retries=settings.max_retries)
                    response = agent.ask(question, explain=st.session_state.explain)
            except DATABASE_ERRORS as exc:
                message = f"Não foi possível conectar ao banco: {exc}"
                st.error(message)
                st.session_state.history.append({"role": "assistant", "error": message})
            except SQLAgentError as exc:
                st.error(str(exc))
                st.session_state.history.append({"role": "assistant", "error": str(exc)})
            except Exception as exc:  # noqa: BLE001 - erro de rede/provedor
                message = f"Erro inesperado: {exc}"
                st.error(message)
                st.session_state.history.append({"role": "assistant", "error": message})
            else:
                payload = response.to_dict()
                _render_payload(payload)
                st.session_state.history.append(
                    {"role": "assistant", "payload": payload}
                )


if __name__ == "__main__":
    main()
