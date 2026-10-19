"""Script CLI para indexação da Base de Conhecimento Institucional no RAG (`scripts/seed_knowledge.py` — T040).

Uso:
    uv run python scripts/seed_knowledge.py
"""

import asyncio

from harness.cognition.retrievers.factory import (
    DEFAULT_COMPANY_KNOWLEDGE,
    InMemoryRetrieverAdapter,
    PGVectorRetrieverAdapter,
    QdrantRetrieverAdapter,
    VectorStoreFactory,
)
from harness.ingress.database import DatabasePoolManager
from harness.settings import get_settings


async def main() -> None:
    cfg = get_settings()
    db_manager: DatabasePoolManager | None = None

    try:
        pool = None
        if cfg.rag.provider == "postgres":
            db_manager = DatabasePoolManager(cfg.database_url)
            pool = await db_manager.open()

        retriever = VectorStoreFactory.create(
            cfg.rag,
            settings=cfg,
            pool=pool,
            seed_defaults_if_in_memory=False,
        )
        if isinstance(
            retriever,
            (PGVectorRetrieverAdapter, InMemoryRetrieverAdapter, QdrantRetrieverAdapter),
        ):
            count = await retriever.seed_documents(DEFAULT_COMPANY_KNOWLEDGE)
            print(
                f"[SEED-RAG] {count} documentos institucionais indexados com sucesso "
                f"(provider='{cfg.rag.provider}', collection='{cfg.rag.collection_name}')."
            )
    finally:
        if db_manager is not None:
            await db_manager.close()


if __name__ == "__main__":
    asyncio.run(main())

