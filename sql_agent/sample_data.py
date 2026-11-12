"""Geração do banco de exemplo usado nas demonstrações e nos testes.

Os mesmos dados podem ser gravados em SQLite (para o projeto rodar sem
servidor) ou em MySQL (para o banco remoto do desafio).
"""

from __future__ import annotations

import random
import re
import sqlite3
import unicodedata
from datetime import date, timedelta
from pathlib import Path
from typing import Any

SQLITE_SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE clientes (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    nome          TEXT NOT NULL,
    email         TEXT NOT NULL UNIQUE,
    cidade        TEXT NOT NULL,
    estado        TEXT NOT NULL,
    segmento      TEXT NOT NULL,
    data_cadastro TEXT NOT NULL
);

CREATE TABLE vendedores (
    id     INTEGER PRIMARY KEY AUTOINCREMENT,
    nome   TEXT NOT NULL,
    email  TEXT NOT NULL UNIQUE,
    regiao TEXT NOT NULL
);

CREATE TABLE produtos (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    nome           TEXT NOT NULL,
    categoria      TEXT NOT NULL,
    preco_unitario REAL NOT NULL CHECK (preco_unitario >= 0),
    estoque        INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE pedidos (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    cliente_id  INTEGER NOT NULL REFERENCES clientes(id),
    vendedor_id INTEGER NOT NULL REFERENCES vendedores(id),
    data_pedido TEXT NOT NULL,
    status      TEXT NOT NULL CHECK (status IN ('pago', 'enviado', 'entregue', 'cancelado')),
    canal       TEXT NOT NULL CHECK (canal IN ('site', 'loja', 'telefone'))
);

CREATE TABLE itens_pedido (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    pedido_id      INTEGER NOT NULL REFERENCES pedidos(id),
    produto_id     INTEGER NOT NULL REFERENCES produtos(id),
    quantidade     INTEGER NOT NULL CHECK (quantidade > 0),
    preco_unitario REAL NOT NULL CHECK (preco_unitario >= 0)
);

CREATE INDEX idx_pedidos_cliente ON pedidos(cliente_id);
CREATE INDEX idx_pedidos_vendedor ON pedidos(vendedor_id);
CREATE INDEX idx_pedidos_data ON pedidos(data_pedido);
CREATE INDEX idx_itens_pedido ON itens_pedido(pedido_id);
CREATE INDEX idx_itens_produto ON itens_pedido(produto_id);
"""

MYSQL_SCHEMA_STATEMENTS = [
    """
    CREATE TABLE clientes (
        id            INT AUTO_INCREMENT PRIMARY KEY,
        nome          VARCHAR(120) NOT NULL,
        email         VARCHAR(160) NOT NULL UNIQUE,
        cidade        VARCHAR(80) NOT NULL,
        estado        CHAR(2) NOT NULL,
        segmento      VARCHAR(40) NOT NULL,
        data_cadastro DATE NOT NULL,
        KEY idx_clientes_cidade (cidade),
        KEY idx_clientes_segmento (segmento)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    """
    CREATE TABLE vendedores (
        id     INT AUTO_INCREMENT PRIMARY KEY,
        nome   VARCHAR(120) NOT NULL,
        email  VARCHAR(160) NOT NULL UNIQUE,
        regiao VARCHAR(40) NOT NULL
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    """
    CREATE TABLE produtos (
        id             INT AUTO_INCREMENT PRIMARY KEY,
        nome           VARCHAR(160) NOT NULL,
        categoria      VARCHAR(40) NOT NULL,
        preco_unitario DECIMAL(10, 2) NOT NULL,
        estoque        INT NOT NULL DEFAULT 0,
        KEY idx_produtos_categoria (categoria)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    """
    CREATE TABLE pedidos (
        id          INT AUTO_INCREMENT PRIMARY KEY,
        cliente_id  INT NOT NULL,
        vendedor_id INT NOT NULL,
        data_pedido DATE NOT NULL,
        status      ENUM('pago', 'enviado', 'entregue', 'cancelado') NOT NULL,
        canal       ENUM('site', 'loja', 'telefone') NOT NULL,
        KEY idx_pedidos_cliente (cliente_id),
        KEY idx_pedidos_vendedor (vendedor_id),
        KEY idx_pedidos_data (data_pedido),
        CONSTRAINT fk_pedidos_cliente FOREIGN KEY (cliente_id) REFERENCES clientes (id),
        CONSTRAINT fk_pedidos_vendedor FOREIGN KEY (vendedor_id) REFERENCES vendedores (id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    """
    CREATE TABLE itens_pedido (
        id             INT AUTO_INCREMENT PRIMARY KEY,
        pedido_id      INT NOT NULL,
        produto_id     INT NOT NULL,
        quantidade     INT NOT NULL,
        preco_unitario DECIMAL(10, 2) NOT NULL,
        KEY idx_itens_pedido (pedido_id),
        KEY idx_itens_produto (produto_id),
        CONSTRAINT fk_itens_pedido FOREIGN KEY (pedido_id) REFERENCES pedidos (id),
        CONSTRAINT fk_itens_produto FOREIGN KEY (produto_id) REFERENCES produtos (id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
]

CIDADES = [
    ("São Paulo", "SP"),
    ("Rio de Janeiro", "RJ"),
    ("Belo Horizonte", "MG"),
    ("Curitiba", "PR"),
    ("Porto Alegre", "RS"),
    ("Salvador", "BA"),
    ("Recife", "PE"),
    ("Fortaleza", "CE"),
    ("Brasília", "DF"),
    ("Florianópolis", "SC"),
    ("Goiânia", "GO"),
    ("Campinas", "SP"),
]

NOMES = [
    "Ana", "Bruno", "Carla", "Diego", "Elisa", "Felipe", "Gabriela", "Henrique",
    "Isabela", "João", "Karina", "Lucas", "Mariana", "Nicolas", "Olívia", "Paulo",
    "Queila", "Rafael", "Sofia", "Thiago",
]

SOBRENOMES = [
    "Almeida", "Barbosa", "Cardoso", "Dias", "Esteves", "Ferreira", "Gomes", "Honda",
    "Ibrahim", "Jesus", "Klein", "Lopes", "Moraes", "Nogueira", "Oliveira", "Pereira",
    "Queiroz", "Ribeiro", "Santos", "Teixeira",
]

SEGMENTOS = ["Varejo", "Indústria", "Serviços", "Tecnologia", "Saúde", "Educação"]

VENDEDORES = [
    ("Ana Souza", "Sudeste"),
    ("Bruno Lima", "Sul"),
    ("Carla Mendes", "Nordeste"),
    ("Diego Rocha", "Centro-Oeste"),
    ("Elisa Prado", "Norte"),
    ("Felipe Nunes", "Sudeste"),
]

PRODUTOS = [
    ("Notebook Pro 15", "Eletrônicos", 4599.00, 18),
    ("Smartphone X", "Eletrônicos", 2799.00, 35),
    ("Fone Bluetooth", "Eletrônicos", 349.90, 120),
    ("Monitor 27 polegadas", "Eletrônicos", 1899.00, 22),
    ("Teclado Mecânico", "Eletrônicos", 429.00, 64),
    ("Cadeira de Escritório", "Móveis", 899.00, 40),
    ("Mesa de Escritório", "Móveis", 1290.00, 15),
    ("Estante 5 Prateleiras", "Móveis", 649.00, 27),
    ("Sofá 3 Lugares", "Móveis", 2499.00, 9),
    ("Luminária de Mesa", "Móveis", 129.90, 88),
    ("Python para Análise de Dados", "Livros", 129.90, 150),
    ("SQL Prático", "Livros", 89.90, 210),
    ("Banco de Dados Moderno", "Livros", 149.90, 95),
    ("Estatística Aplicada", "Livros", 119.90, 130),
    ("Arquitetura de Software", "Livros", 159.90, 76),
    ("Bicicleta Urbana", "Esportes", 1899.00, 12),
    ("Tênis de Corrida", "Esportes", 499.90, 58),
    ("Halteres 10 kg", "Esportes", 159.90, 45),
    ("Tapete de Yoga", "Esportes", 99.90, 110),
    ("Mochila Esportiva", "Esportes", 219.90, 70),
    ("Cafeteira Elétrica", "Casa", 299.90, 52),
    ("Jogo de Panelas", "Casa", 449.90, 31),
    ("Aspirador Vertical", "Casa", 799.00, 19),
    ("Air Fryer 5L", "Casa", 499.00, 44),
    ("Kit de Toalhas", "Casa", 149.90, 100),
]

STATUS = ["entregue", "pago", "enviado", "cancelado"]
STATUS_PESOS = [45, 20, 15, 20]
CANAIS = ["site", "loja", "telefone"]
CANAIS_PESOS = [55, 30, 15]


def _slug(text: str) -> str:
    without_accents = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", ".", without_accents.lower()).strip(".")


def _iso(day: date) -> str:
    return day.isoformat()


def build_sample_data(seed: int = 2026) -> dict[str, list[tuple[Any, ...]]]:
    """Gera os dados de demonstração de forma determinística."""

    rng = random.Random(seed)

    # Clientes ------------------------------------------------------------
    combos = [(nome, sobrenome) for nome in NOMES for sobrenome in SOBRENOMES]
    clientes = []
    for index, (nome, sobrenome) in enumerate(rng.sample(combos, 40), start=1):
        cidade, estado = rng.choice(CIDADES)
        inicio = date(2023, 1, 1)
        fim = date(2026, 10, 31)
        cadastro = inicio + timedelta(days=rng.randint(0, (fim - inicio).days))
        email = f"{_slug(nome)}.{_slug(sobrenome)}{index}@exemplo.com.br"
        clientes.append(
            (index, f"{nome} {sobrenome}", email, cidade, estado, rng.choice(SEGMENTOS), _iso(cadastro))
        )

    # Vendedores ----------------------------------------------------------
    vendedores = [
        (index, nome, f"{_slug(nome)}@empresa.com.br", regiao)
        for index, (nome, regiao) in enumerate(VENDEDORES, start=1)
    ]

    # Produtos ------------------------------------------------------------
    produtos = [
        (index, nome, categoria, preco, estoque)
        for index, (nome, categoria, preco, estoque) in enumerate(PRODUTOS, start=1)
    ]

    # Pedidos e itens -----------------------------------------------------
    # Cinco clientes ficam sem pedidos de propósito, para exercitar LEFT JOIN.
    clientes_com_pedido = [cliente[0] for cliente in clientes[:-5]]
    inicio_pedidos = date(2025, 1, 5)
    fim_pedidos = date(2026, 11, 10)
    total_dias = (fim_pedidos - inicio_pedidos).days

    pedidos = []
    itens = []
    item_id = 1
    for pedido_id in range(1, 121):
        cliente_id = rng.choice(clientes_com_pedido)
        vendedor_id = rng.randint(1, len(vendedores))
        data_pedido = inicio_pedidos + timedelta(days=rng.randint(0, total_dias))
        status = rng.choices(STATUS, weights=STATUS_PESOS, k=1)[0]
        canal = rng.choices(CANAIS, weights=CANAIS_PESOS, k=1)[0]
        pedidos.append((pedido_id, cliente_id, vendedor_id, _iso(data_pedido), status, canal))

        for produto in rng.sample(produtos, k=rng.randint(1, 4)):
            produto_id, _, _, preco, _ = produto
            desconto = rng.choice([1.0, 1.0, 1.0, 0.95, 0.9])
            itens.append(
                (
                    item_id,
                    pedido_id,
                    produto_id,
                    rng.randint(1, 5),
                    round(preco * desconto, 2),
                )
            )
            item_id += 1

    return {
        "clientes": clientes,
        "vendedores": vendedores,
        "produtos": produtos,
        "pedidos": pedidos,
        "itens_pedido": itens,
    }


def create_sample_database(
    path: str | Path,
    *,
    seed: int = 2026,
    overwrite: bool = True,
) -> Path:
    """Cria (ou recria) um banco SQLite de demonstração e devolve o caminho."""

    db_path = Path(path).expanduser().resolve()
    db_path.parent.mkdir(parents=True, exist_ok=True)

    if db_path.exists():
        if not overwrite:
            raise FileExistsError(f"O arquivo já existe: {db_path}")
        db_path.unlink()

    data = build_sample_data(seed)

    connection = sqlite3.connect(db_path)
    try:
        connection.executescript(SQLITE_SCHEMA)
        connection.executemany(
            "INSERT INTO clientes (id, nome, email, cidade, estado, segmento, data_cadastro) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            data["clientes"],
        )
        connection.executemany(
            "INSERT INTO vendedores (id, nome, email, regiao) VALUES (?, ?, ?, ?)",
            data["vendedores"],
        )
        connection.executemany(
            "INSERT INTO produtos (id, nome, categoria, preco_unitario, estoque) "
            "VALUES (?, ?, ?, ?, ?)",
            data["produtos"],
        )
        connection.executemany(
            "INSERT INTO pedidos (id, cliente_id, vendedor_id, data_pedido, status, canal) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            data["pedidos"],
        )
        connection.executemany(
            "INSERT INTO itens_pedido (id, pedido_id, produto_id, quantidade, preco_unitario) "
            "VALUES (?, ?, ?, ?, ?)",
            data["itens_pedido"],
        )
        connection.commit()
    finally:
        connection.close()

    return db_path


if __name__ == "__main__":  # pragma: no cover
    create_sample_database("data/empresa.db")
