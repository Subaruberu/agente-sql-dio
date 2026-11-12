"""Interface de linha de comando do agente SQL."""

from __future__ import annotations

import argparse
import json
import sys
from typing import Sequence

from .agent import AgentResponse, SQLAgent, SQLAgentError
from .config import Settings, load_settings
from .database import Database
from .llm import LLMConfigurationError, OpenAICompatibleLLM

COMMANDS_HELP = """Comandos disponíveis:
  /ajuda    mostra esta ajuda
  /schema   exibe o esquema do banco
  /sair     encerra o programa

Dica: para respostas em JSON, use o modo de uma pergunta só:
  python -m sql_agent -q "sua pergunta" --json
"""


def _stringify(value: object) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, float):
        text = f"{value:.4f}".rstrip("0").rstrip(".")
        return text or "0"
    if isinstance(value, bytes):
        return f"<{len(value)} bytes>"
    return str(value)


def render_table(
    columns: Sequence[str],
    rows: Sequence[Sequence[object]],
    max_width: int = 36,
) -> str:
    """Desenha uma tabela ASCII simples no terminal."""

    if not columns:
        return "(sem colunas)"

    headers = [str(column) for column in columns]
    cells = [[_stringify(value) for value in row] for row in rows]

    widths = []
    for index, header in enumerate(headers):
        longest = max([len(header), *(len(row[index]) for row in cells)])
        widths.append(max(3, min(longest, max_width)))

    def fit(text: str, width: int) -> str:
        if len(text) > width:
            text = text[: max(0, width - 3)] + "..."
        return text.ljust(width)

    border = "+" + "+".join("-" * (width + 2) for width in widths) + "+"
    lines = [border]
    lines.append("| " + " | ".join(fit(header, w) for header, w in zip(headers, widths)) + " |")
    lines.append(border)
    for row in cells:
        lines.append("| " + " | ".join(fit(cell, w) for cell, w in zip(row, widths)) + " |")
    lines.append(border)
    return "\n".join(lines)


def print_response(response: AgentResponse) -> None:
    result = response.result
    print()
    print(f"SQL gerado (tentativa {response.attempts}):")
    for line in response.sql.splitlines() or [""]:
        print(f"  {line}")

    print()
    suffix = " -> resultado truncado" if result.truncated else ""
    print(f"Resultado: {result.row_count} linha(s) em {result.elapsed_ms} ms{suffix}")
    print(render_table(result.columns, result.rows))

    if response.explanation:
        print()
        print(f"Resposta: {response.explanation}")

    for warning in response.warnings:
        print(f"aviso: {warning}", file=sys.stderr)


def _open_database(settings: Settings) -> Database:
    try:
        return Database(settings.db_path, max_rows=settings.max_rows)
    except FileNotFoundError as exc:
        raise SystemExit(
            f"{exc}\n\nCrie o banco de exemplo com:\n"
            "  python scripts/create_sample_db.py"
        ) from exc


def _build_agent(database: Database, settings: Settings) -> SQLAgent:
    try:
        llm = OpenAICompatibleLLM(
            model=settings.model,
            api_key=settings.api_key,
            base_url=settings.base_url,
            temperature=settings.temperature,
        )
    except LLMConfigurationError as exc:
        database.close()
        raise SystemExit(f"{exc}\n\nConsulte o README para configurar o provedor.") from exc

    return SQLAgent(database, llm, max_retries=settings.max_retries)


def _run_question(agent: SQLAgent, question: str, *, explain: bool, as_json: bool) -> int:
    try:
        response = agent.ask(question, explain=explain)
    except SQLAgentError as exc:
        print(f"erro: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:  # noqa: BLE001 - falha de rede/provedor
        print(f"erro inesperado: {exc}", file=sys.stderr)
        return 1

    if as_json:
        print(json.dumps(response.to_dict(), ensure_ascii=False, indent=2, default=str))
    else:
        print_response(response)
    return 0


def _repl(agent: SQLAgent, database: Database, *, explain: bool) -> int:
    print()
    print("Agente SQL - perguntas em linguagem natural viram consultas SQLite")
    print(f"Banco: {database.path}")
    print("Digite /ajuda para ver os comandos ou /sair para encerrar.")
    print()

    while True:
        try:
            question = input("pergunta> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0

        if not question:
            continue
        if question in {"/sair", "/exit", "/quit"}:
            return 0
        if question == "/ajuda":
            print(COMMANDS_HELP)
            continue
        if question == "/schema":
            print()
            print(database.schema())
            print()
            continue

        try:
            response = agent.ask(question, explain=explain)
            print_response(response)
        except SQLAgentError as exc:
            print(f"erro: {exc}", file=sys.stderr)
        except Exception as exc:  # noqa: BLE001 - mantém o REPL vivo
            print(f"erro inesperado: {exc}", file=sys.stderr)
        print()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="sql-agent",
        description="Converte perguntas em linguagem natural para consultas SQL (SQLite).",
    )
    parser.add_argument("--db", help="caminho do arquivo SQLite (padrão: data/empresa.db)")
    parser.add_argument("-q", "--question", help="pergunta única; sem ela, abre o modo interativo")
    parser.add_argument("--json", action="store_true", help="imprime a resposta em JSON")
    parser.add_argument(
        "--no-explain",
        action="store_true",
        help="não pede ao modelo a explicação em linguagem natural",
    )
    parser.add_argument("--max-rows", type=int, help="máximo de linhas retornadas (padrão: 100)")
    parser.add_argument("--max-retries", type=int, help="tentativas extras de correção (padrão: 2)")
    parser.add_argument("--model", help="sobrescreve LLM_MODEL")
    parser.add_argument("--base-url", help="sobrescreve LLM_BASE_URL")
    parser.add_argument("--show-schema", action="store_true", help="imprime o esquema e sai")
    parser.add_argument("--version", action="version", version="%(prog)s 1.0.0")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    settings = load_settings(
        db_path=args.db,
        model=args.model,
        base_url=args.base_url,
        max_rows=args.max_rows,
        max_retries=args.max_retries,
    )
    database = _open_database(settings)

    if args.show_schema:
        try:
            print(database.schema())
        finally:
            database.close()
        return 0

    if args.json and not args.question:
        database.close()
        print("erro: --json exige --question (-q).", file=sys.stderr)
        return 2

    try:
        agent = _build_agent(database, settings)
        if args.question:
            return _run_question(
                agent, args.question, explain=not args.no_explain, as_json=args.json
            )
        return _repl(agent, database, explain=not args.no_explain)
    finally:
        database.close()


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
