"""Cria o banco SQLite de exemplo em data/empresa.db.

Uso:
    python scripts/create_sample_db.py
    python scripts/create_sample_db.py --output data/meu_banco.db
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

# Permite executar o script diretamente (sem instalar o pacote).
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sql_agent.sample_data import create_sample_database  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Cria o banco de exemplo do agente SQL.")
    parser.add_argument(
        "--output",
        default="data/empresa.db",
        help="caminho do arquivo SQLite a ser criado (padrão: data/empresa.db)",
    )
    parser.add_argument("--seed", type=int, default=2026, help="semente aleatória (padrão: 2026)")
    args = parser.parse_args()

    path = create_sample_database(args.output, seed=args.seed)
    print(f"Banco criado em: {path}")

    connection = sqlite3.connect(path)
    try:
        tables = [
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' "
                "AND name NOT LIKE 'sqlite_%' ORDER BY name"
            )
        ]
        for table in tables:
            total = connection.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
            print(f"  {table:<14} {total:>4} registro(s)")
    finally:
        connection.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
