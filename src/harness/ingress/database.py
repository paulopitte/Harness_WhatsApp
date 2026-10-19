"""Gerenciador de Pool de Conexões Assíncronas com PostgreSQL (`psycopg` v3).

Equivalente no C#/.NET: `NpgsqlDataSource` registrado como Singleton na Injeção de Dependência.
Fornece conexões assíncronas eficientes para a Borda, Workers e Admin API.

Nota sobre Windows + `psycopg` v3:
O driver C `libpq` do `psycopg` exige `SelectorEventLoop` no Windows (não suporta `ProactorEventLoop`).
A função `run_with_selector_loop` configura automaticamente a `loop_factory` compatível no Python 3.13.
"""

import asyncio
from collections.abc import Coroutine
from pathlib import Path
import selectors
import sys
from typing import Any
from urllib.parse import urlparse, urlunparse

import psycopg
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool


def configure_windows_selector_event_loop() -> None:
    """Configura `WindowsSelectorEventLoopPolicy` quando executado no Windows (necessário para Uvicorn + psycopg)."""
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


def run_with_selector_loop[T](coro: Coroutine[Any, Any, T]) -> T:
    """Executa uma corrotina principal garantindo `SelectorEventLoop` no Windows para compatibilidade com `psycopg`."""
    if sys.platform == "win32":
        configure_windows_selector_event_loop()
        return asyncio.run(
            coro,
            loop_factory=lambda: asyncio.SelectorEventLoop(selectors.SelectSelector()),
        )
    return asyncio.run(coro)


class DatabasePoolManager:
    """Encapsula o ciclo de vida do `AsyncConnectionPool` do `psycopg` v3."""

    def __init__(
        self,
        conninfo: str,
        *,
        min_size: int = 2,
        max_size: int = 10,
    ) -> None:
        configure_windows_selector_event_loop()
        self._conninfo = conninfo
        self._min_size = min_size
        self._max_size = max_size
        self._pool: AsyncConnectionPool[Any] | None = None

    async def ensure_database_exists(self) -> None:
        """Cria o banco de dados alvo (ex.: `whatsapp_harness`) caso ainda não exista na instância PostgreSQL."""
        parsed = urlparse(self._conninfo)
        target_db = (parsed.path or "").lstrip("/")
        if not target_db or target_db == "postgres":
            return

        admin_conninfo = urlunparse(parsed._replace(path="/postgres"))
        try:
            async with await psycopg.AsyncConnection.connect(
                admin_conninfo,
                autocommit=True,
            ) as conn:
                async with conn.cursor() as cur:
                    await cur.execute(
                        "SELECT 1 FROM pg_database WHERE datname = %s;",
                        (target_db,),
                    )
                    exists = await cur.fetchone()
                    if not exists:
                        await cur.execute(f'CREATE DATABASE "{target_db}";')
        except Exception:
            # Se o usuário não tiver permissão no banco 'postgres', prossegue para conexão direta
            pass

    async def open(self) -> AsyncConnectionPool[Any]:
        """Inicializa e abre o pool de conexões assíncronas."""
        if self._pool is None:
            self._pool = AsyncConnectionPool(
                conninfo=self._conninfo,
                min_size=self._min_size,
                max_size=self._max_size,
                open=False,
                kwargs={"row_factory": dict_row, "autocommit": False},
            )
            await self._pool.open()
        return self._pool

    @property
    def pool(self) -> AsyncConnectionPool[Any]:
        """Retorna o pool ativo ou lança RuntimeError se ainda não foi aberto."""
        if self._pool is None:
            raise RuntimeError(
                "O DatabasePoolManager ainda não foi aberto. Chame `await db.open()` na inicialização."
            )
        return self._pool

    async def apply_migration(self, sql_file_path: str | Path) -> None:
        """Garante a existência do banco e executa um script DDL SQL idempotente."""
        await self.ensure_database_exists()
        sql_text = Path(sql_file_path).read_text(encoding="utf-8")
        pool = await self.open()
        async with pool.connection() as conn:
            try:
                async with conn.cursor() as cur:
                    await cur.execute(sql_text)
                await conn.commit()
            except psycopg.errors.FeatureNotSupported:
                await conn.rollback()
                print(
                    "[AVISO] Extensão 'vector' (pgvector) não encontrada no PostgreSQL local. "
                    "Aplicando schema com coluna de embedding em formato JSONB compatível..."
                )
                fallback_sql = sql_text.replace(
                    'CREATE EXTENSION IF NOT EXISTS "vector";',
                    '-- pgvector ausente no Postgres local (usando JSONB)',
                ).replace("embedding vector(64) NOT NULL", "embedding JSONB NOT NULL")
                async with conn.cursor() as cur:
                    await cur.execute(fallback_sql)
                await conn.commit()

    async def close(self) -> None:
        """Fecha todas as conexões do pool com graceful shutdown."""
        if self._pool is not None:
            await self._pool.close()
            self._pool = None
