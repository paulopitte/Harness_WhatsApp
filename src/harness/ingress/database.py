"""Gerenciador de Pool de Conexões Assíncronas com PostgreSQL (`psycopg` v3).

Equivalente no C#/.NET: `NpgsqlDataSource` registrado como Singleton na Injeção de Dependência.
Fornece conexões assíncronas eficientes para a Borda, Workers e Admin API.
"""

from pathlib import Path
from typing import Any

from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool


class DatabasePoolManager:
    """Encapsula o ciclo de vida do `AsyncConnectionPool` do `psycopg` v3."""

    def __init__(
        self,
        conninfo: str,
        *,
        min_size: int = 2,
        max_size: int = 10,
    ) -> None:
        self._conninfo = conninfo
        self._min_size = min_size
        self._max_size = max_size
        self._pool: AsyncConnectionPool[Any] | None = None

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
        """Executa um script DDL SQL idempotente no banco de dados."""
        sql_text = Path(sql_file_path).read_text(encoding="utf-8")
        pool = await self.open()
        async with pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(sql_text)
            await conn.commit()

    async def close(self) -> None:
        """Fecha todas as conexões do pool com graceful shutdown."""
        if self._pool is not None:
            await self._pool.close()
            self._pool = None

