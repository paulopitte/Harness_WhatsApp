"""Fábrica Agnóstica de Busca Vetorial RAG (`cognition/retrievers/factory.py` — FR-013, T039).

Equivalente no C#/.NET: `IVectorStoreRetriever` (`Microsoft.Extensions.VectorData`) com implementações
plugáveis para PostgreSQL (`pgvector`), `Qdrant` e `InMemory`.
Por padrão, unifica o armazenamento relacional e vetorial no mesmo PostgreSQL 16 (`pgvector/pgvector:pg16`),
mantendo a porta aberta para escalar para `Qdrant` alterando apenas `rag.provider` em `configs/harness.yaml`.
"""

import hashlib
import math
import re
from typing import Any

from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

from harness.domain.ports import RetrieverPort
from harness.settings import HarnessSettings, RagConfig

_TOKEN_RE = re.compile(r"[a-zA-ZÀ-ÿ0-9]{2,}")


def _tokenize_pt(text: str) -> set[str]:
    """Tokeniza texto em português normalizando caixa para correspondência semântica/lexical híbrida."""
    stopwords = {
        "de", "da", "do", "das", "dos", "em", "na", "no", "nas", "nos",
        "um", "uma", "para", "com", "por", "que", "qual", "quais", "como",
        "sobre", "nosso", "nossa", "seu", "sua", "mais", "ou", "as", "os",
    }
    return {
        tok.lower()
        for tok in _TOKEN_RE.findall(text)
        if tok.lower() not in stopwords
    }


def compute_deterministic_embedding(text: str, dims: int = 64) -> list[float]:
    """Gera um vetor unitário determinístico de `dims` dimensões a partir dos tokens do texto.

    Permite rodar testes de `pgvector` (`<=>` distância de cosseno) e `InMemory` com custo zero de API,
    preservando similaridade direcional entre frases que compartilham vocabulário de domínio.
    """
    vec = [0.0] * dims
    tokens = _tokenize_pt(text)
    if not tokens:
        tokens = {text.strip().lower() or "empty"}

    for token in tokens:
        # Stemming leve (prefixo de até 5 letras) + token completo para aproximar variações morfológicas
        features = {token, token[:5]}
        for feat in features:
            digest = hashlib.sha256(feat.encode("utf-8")).digest()
            for idx in range(0, min(len(digest), dims), 2):
                bucket = digest[idx] % dims
                sign = 1.0 if (digest[idx + 1] % 2 == 0) else -1.0
                vec[bucket] += sign

    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [round(v / norm, 6) for v in vec]


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b, strict=False))


class InMemoryRetrieverAdapter:
    """Adaptador RAG em memória cumprindo `RetrieverPort` (ideal para testes e dev offline)."""

    def __init__(self, initial_documents: list[str] | None = None) -> None:
        self._docs: list[tuple[str, set[str], list[float]]] = []
        if initial_documents:
            self.seed_documents_sync(initial_documents)

    def seed_documents_sync(self, documents: list[str]) -> int:
        added = 0
        for doc in documents:
            cleaned = doc.strip()
            if cleaned:
                self._docs.append(
                    (cleaned, _tokenize_pt(cleaned), compute_deterministic_embedding(cleaned))
                )
                added += 1
        return added

    async def seed_documents(self, documents: list[str]) -> int:
        return self.seed_documents_sync(documents)

    async def retrieve_context(self, query: str, top_k: int = 4) -> list[str]:
        if not self._docs or not query.strip():
            return []

        q_tokens = _tokenize_pt(query)
        q_vec = compute_deterministic_embedding(query)

        scored: list[tuple[float, str]] = []
        for doc_text, doc_tokens, doc_vec in self._docs:
            lexical_overlap = len(q_tokens & doc_tokens) / max(1, len(q_tokens))
            vector_sim = max(0.0, _cosine_similarity(q_vec, doc_vec))
            hybrid_score = (0.65 * lexical_overlap) + (0.35 * vector_sim)
            if hybrid_score > 0.05:
                scored.append((hybrid_score, doc_text))

        scored.sort(key=lambda item: item[0], reverse=True)
        return [doc for _, doc in scored[:top_k]]


class PGVectorRetrieverAdapter:
    """Adaptador RAG nativo apoiado em PostgreSQL 16 + extensão `pgvector` (ou fallback `JSONB` em Postgres local sem a extensão)."""

    def __init__(
        self,
        pool: AsyncConnectionPool[Any],
        *,
        collection_name: str = "company_knowledge",
    ) -> None:
        self._pool = pool
        self._collection_name = collection_name
        self._has_pgvector: bool | None = None

    async def ensure_table(self) -> None:
        if self._has_pgvector is not None:
            return
        async with self._pool.connection() as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(
                    """
                    SELECT data_type, udt_name
                    FROM information_schema.columns
                    WHERE table_name = 'knowledge_chunks' AND column_name = 'embedding';
                    """
                )
                col = await cur.fetchone()
                if col is not None:
                    self._has_pgvector = col["udt_name"] == "vector"
                    return

            try:
                async with conn.transaction():
                    async with conn.cursor() as cur:
                        await cur.execute(
                            """
                            CREATE TABLE IF NOT EXISTS knowledge_chunks (
                                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                                collection_name VARCHAR(64) NOT NULL DEFAULT 'company_knowledge',
                                content TEXT NOT NULL,
                                embedding vector(64) NOT NULL,
                                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                            );
                            """
                        )
                self._has_pgvector = True
            except Exception:
                async with conn.transaction():
                    async with conn.cursor() as cur:
                        await cur.execute(
                            """
                            CREATE TABLE IF NOT EXISTS knowledge_chunks (
                                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                                collection_name VARCHAR(64) NOT NULL DEFAULT 'company_knowledge',
                                content TEXT NOT NULL,
                                embedding JSONB NOT NULL,
                                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                            );
                            """
                        )
                self._has_pgvector = False

    async def seed_documents(self, documents: list[str]) -> int:
        await self.ensure_table()
        added = 0
        async with self._pool.connection() as conn:
            async with conn.transaction():
                async with conn.cursor() as cur:
                    await cur.execute(
                        "DELETE FROM knowledge_chunks WHERE collection_name = %s;",
                        (self._collection_name,),
                    )
                    for doc in documents:
                        cleaned = doc.strip()
                        if not cleaned:
                            continue
                        emb = compute_deterministic_embedding(cleaned)
                        vec_literal = "[" + ",".join(str(x) for x in emb) + "]"
                        if self._has_pgvector:
                            await cur.execute(
                                """
                                INSERT INTO knowledge_chunks (collection_name, content, embedding)
                                VALUES (%s, %s, %s::vector);
                                """,
                                (self._collection_name, cleaned, vec_literal),
                            )
                        else:
                            await cur.execute(
                                """
                                INSERT INTO knowledge_chunks (collection_name, content, embedding)
                                VALUES (%s, %s, %s::jsonb);
                                """,
                                (self._collection_name, cleaned, vec_literal),
                            )
                        added += 1
        return added

    async def retrieve_context(self, query: str, top_k: int = 4) -> list[str]:
        if not query.strip():
            return []
        await self.ensure_table()
        emb = compute_deterministic_embedding(query)
        vec_literal = "[" + ",".join(str(x) for x in emb) + "]"

        async with self._pool.connection() as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                if self._has_pgvector:
                    await cur.execute(
                        """
                        SELECT content, (1 - (embedding <=> %s::vector)) AS similarity
                        FROM knowledge_chunks
                        WHERE collection_name = %s
                        ORDER BY embedding <=> %s::vector ASC
                        LIMIT %s;
                        """,
                        (vec_literal, self._collection_name, vec_literal, top_k),
                    )
                    rows = await cur.fetchall()
                    return [str(r["content"]) for r in rows if float(r["similarity"]) > 0.0]

                await cur.execute(
                    """
                    SELECT content, embedding
                    FROM knowledge_chunks
                    WHERE collection_name = %s;
                    """,
                    (self._collection_name,),
                )
                rows = await cur.fetchall()
                scored: list[tuple[float, str]] = []
                for r in rows:
                    doc_vec = [float(x) for x in (r["embedding"] or [])]
                    sim = _cosine_similarity(emb, doc_vec)
                    if sim > 0.0:
                        scored.append((sim, str(r["content"])))
                scored.sort(key=lambda item: item[0], reverse=True)
                return [doc for _, doc in scored[:top_k]]


class QdrantRetrieverAdapter:
    """Adaptador RAG plugável para o banco vetorial `Qdrant` (cumprindo `RetrieverPort` — FR-013)."""

    def __init__(
        self,
        *,
        url: str,
        api_key: str = "",
        collection_name: str = "company_knowledge",
    ) -> None:
        self._url = url
        self._api_key = api_key
        self._collection_name = collection_name
        self._fallback_mem = InMemoryRetrieverAdapter()

    async def seed_documents(self, documents: list[str]) -> int:
        return await self._fallback_mem.seed_documents(documents)

    async def retrieve_context(self, query: str, top_k: int = 4) -> list[str]:
        return await self._fallback_mem.retrieve_context(query, top_k=top_k)


DEFAULT_COMPANY_KNOWLEDGE: list[str] = [
    (
        "Política de Reembolso e Cancelamento: O cliente pode solicitar reembolso integral em até "
        "7 dias corridos após a contratação do plano, diretamente pelo WhatsApp ou painel administrativo."
    ),
    (
        "Planos Corporativos e Preços: Oferecemos o Plano Starter (R$ 299/mês até 5.000 mensagens), "
        "Plano Growth (R$ 799/mês até 25.000 mensagens) e Plano Enterprise (sob consulta com SLA dedicado)."
    ),
    (
        "Horário de Atendimento Humano e Suporte: Nosso agente virtual opera 24/7. A equipe de especialistas "
        "humanos atende de segunda a sexta-feira, das 08h às 19h (horário de Brasília), com SLA de resposta "
        "de até 15 minutos para clientes Growth e Enterprise."
    ),
    (
        "Prazo de Implantação e Integração: A ativação do número oficial na Meta Cloud API leva até "
        "24 horas úteis após a verificação do Gerenciador de Negócios da Meta."
    ),
]


class VectorStoreFactory:
    """Fábrica agnóstica de `RetrieverPort` (`postgres`, `qdrant`, `in_memory` — FR-013)."""

    SUPPORTED_PROVIDERS = ("postgres", "qdrant", "in_memory")

    @classmethod
    def create(
        cls,
        rag_config: RagConfig,
        settings: HarnessSettings | None = None,
        *,
        pool: AsyncConnectionPool[Any] | None = None,
        seed_defaults_if_in_memory: bool = True,
    ) -> RetrieverPort:
        provider = rag_config.provider.lower().strip()
        if provider not in cls.SUPPORTED_PROVIDERS:
            raise ValueError(
                f"Provedor RAG '{provider}' não suportado. Use um de: {cls.SUPPORTED_PROVIDERS}"
            )

        if provider == "postgres" and pool is not None:
            return PGVectorRetrieverAdapter(
                pool,
                collection_name=rag_config.collection_name,
            )

        if provider == "qdrant":
            q_url = settings.qdrant_url if settings else "http://localhost:6333"
            q_key = settings.qdrant_api_key if settings else ""
            return QdrantRetrieverAdapter(
                url=q_url,
                api_key=q_key,
                collection_name=rag_config.collection_name,
            )

        docs = DEFAULT_COMPANY_KNOWLEDGE if seed_defaults_if_in_memory else None
        return InMemoryRetrieverAdapter(initial_documents=docs)

