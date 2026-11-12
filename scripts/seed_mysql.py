from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sql_agent.config import load_settings  # noqa: E402
from sql_agent.database import quote_identifier  # noqa: E402
from sql_agent.sample_data import MYSQL_SCHEMA_STATEMENTS, build_sample_data  # noqa: E402

TABLES_IN_ORDER = ["clientes", "vendedores", "produtos", "pedidos", "itens_pedido"]
DROP_ORDER = list(reversed(TABLES_IN_ORDER))

INSERT_SQL = {
    "clientes": (
        "INSERT INTO clientes (id, nome, email, cidade, estado, segmento, data_cadastro) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s)"
    ),
    "vendedores": "INSERT INTO vendedores (id, nome, email, regiao) VALUES (%s, %s, %s, %s)",
    "produtos": (
        "INSERT INTO produtos (id, nome, categoria, preco_unitario, estoque) "
        "VALUES (%s, %s, %s, %s, %s)"
    ),
    "pedidos": (
        "INSERT INTO pedidos (id, cliente_id, vendedor_id, data_pedido, status, canal) "
        "VALUES (%s, %s, %s, %s, %s, %s)"
    ),
    "itens_pedido": (
        "INSERT INTO itens_pedido (id, pedido_id, produto_id, quantidade, preco_unitario) "
        "VALUES (%s, %s, %s, %s, %s)"
    ),
}


def _connect(settings, with_database: bool = True):
    import pymysql

    return pymysql.connect(
        host=settings.mysql_host,
        port=settings.mysql_port,
        user=settings.mysql_user,
        password=settings.mysql_password,
        database=settings.mysql_database if with_database else None,
        charset="utf8mb4",
        autocommit=False,
        connect_timeout=10,
        **({"ssl": {"ca": settings.mysql_ssl_ca}} if settings.mysql_ssl_ca else {}),
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Cria a massa de dados do agente no MySQL.")
    parser.add_argument(
        "--force",
        action="store_true",
        help="apaga as tabelas do projeto que já existirem antes de recriar",
    )
    parser.add_argument("--seed", type=int, default=2026, help="semente aleatória (padrão: 2026)")
    args = parser.parse_args()

    try:
        import pymysql
    except ImportError:
        print("erro: instale as dependências com 'pip install -r requirements.txt'.", file=sys.stderr)
        return 1

    settings = load_settings()
    if settings.backend != "mysql":
        print(
            "erro: o backend atual é 'sqlite'. Configure no .env:\n"
            "  SQL_AGENT_BACKEND=mysql\n"
            "  DATABASE_URL=mysql://usuario:senha@host:3306/diobank\n",
            file=sys.stderr,
        )
        return 1

    try:
        connection = _connect(settings)
    except pymysql.err.OperationalError as exc:
        if exc.args and exc.args[0] == 1049:  # Unknown database
            print(f"Banco '{settings.mysql_database}' não existe; criando...")
            server = _connect(settings, with_database=False)
            try:
                with server.cursor() as cursor:
                    cursor.execute(
                        f"CREATE DATABASE IF NOT EXISTS {quote_identifier(settings.mysql_database)} "
                        "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
                    )
                server.commit()
            finally:
                server.close()
            connection = _connect(settings)
        else:
            print(f"erro ao conectar no MySQL: {exc}", file=sys.stderr)
            return 1

    try:
        with connection.cursor() as cursor:
            cursor.execute("SHOW TABLES")
            existing = {str(row[0]) for row in cursor.fetchall()}
            ours = existing & set(TABLES_IN_ORDER)

            if ours and not args.force:
                print(
                    "erro: as tabelas já existem: " + ", ".join(sorted(ours)) + ".\n"
                    "Use --force para apagá-las e recriar (os dados serão perdidos).",
                    file=sys.stderr,
                )
                return 1

            if ours:
                print("Removendo tabelas existentes: " + ", ".join(sorted(ours)))
                cursor.execute("SET FOREIGN_KEY_CHECKS = 0")
                for table in DROP_ORDER:
                    cursor.execute(f"DROP TABLE IF EXISTS {quote_identifier(table)}")
                cursor.execute("SET FOREIGN_KEY_CHECKS = 1")

            for statement in MYSQL_SCHEMA_STATEMENTS:
                cursor.execute(statement)

            data = build_sample_data(args.seed)
            for table in TABLES_IN_ORDER:
                cursor.executemany(INSERT_SQL[table], data[table])
                print(f"  {table:<14} {len(data[table]):>4} registro(s)")

        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()

    print(
        f"\nMassa de dados criada em {settings.mysql_host}:{settings.mysql_port}"
        f"/{settings.mysql_database}."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
