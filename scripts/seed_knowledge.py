"""Script CLI para indexação da Base de Conhecimento Institucional no RAG (`scripts/seed_knowledge.py` — T040).

Suporta:
1. Leitura automática de documentos na pasta `docs/knowledge/` (*.md, *.txt, *.pdf)
2. Fatiamento inteligente em chunks com `RecursiveCharacterTextSplitter`
3. Fallback para os dados base `DEFAULT_COMPANY_KNOWLEDGE` caso a pasta esteja vazia.

Uso:
    uv run python scripts/seed_knowledge.py
"""

from pathlib import Path

from langchain_text_splitters import RecursiveCharacterTextSplitter
from pypdf import PdfReader

from harness.cognition.retrievers.factory import (
    DEFAULT_COMPANY_KNOWLEDGE,
    InMemoryRetrieverAdapter,
    PGVectorRetrieverAdapter,
    QdrantRetrieverAdapter,
    VectorStoreFactory,
)
from harness.ingress.database import DatabasePoolManager, run_with_selector_loop
from harness.settings import get_settings


def load_documents_from_folder(
    folder_path: str | Path = "docs/knowledge",
    chunk_size: int = 800,
    chunk_overlap: int = 100,
) -> list[str]:
    """Lê todos os arquivos .md, .txt e .pdf da pasta e os divide em chunks semânticos."""
    path = Path(folder_path)
    if not path.exists():
        path.mkdir(parents=True, exist_ok=True)
        return []

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        separators=["\n## ", "\n### ", "\n\n", "\n", " "],
    )

    documents_to_index: list[str] = []

    for file_path in path.glob("*"):
        if file_path.is_dir():
            continue

        raw_text = ""
        file_ext = file_path.suffix.lower()

        if file_ext in (".md", ".txt"):
            try:
                raw_text = file_path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                raw_text = file_path.read_text(encoding="latin-1")

        elif file_ext == ".pdf":
            try:
                reader = PdfReader(str(file_path))
                raw_text = "\n\n".join(
                    page.extract_text() or "" for page in reader.pages
                )
            except Exception as e:
                print(f"[SEED-RAG] [AVISO] Erro ao ler PDF '{file_path.name}': {e}")
                continue

        if not raw_text.strip():
            continue

        chunks = splitter.split_text(raw_text)
        print(f"[SEED-RAG] [DOC] Arquivo '{file_path.name}' processado: {len(chunks)} chunk(s) gerado(s).")

        for idx, chunk in enumerate(chunks):
            chunk_entry = f"[{file_path.name} - Parte {idx + 1}]\n{chunk.strip()}"
            documents_to_index.append(chunk_entry)

    return documents_to_index


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

        folder_docs = load_documents_from_folder("docs/knowledge")

        # Combina os documentos dos arquivos com o conhecimento padrão (evitando duplicar se vazio)
        docs_to_seed = list(DEFAULT_COMPANY_KNOWLEDGE)
        if folder_docs:
            docs_to_seed.extend(folder_docs)

        if isinstance(
            retriever,
            (PGVectorRetrieverAdapter, InMemoryRetrieverAdapter, QdrantRetrieverAdapter),
        ):
            count = await retriever.seed_documents(docs_to_seed)
            print(
                f"\n[SEED-RAG] [SUCESSO] Total de {count} documentos/chunks indexados com sucesso no banco "
                f"(provider='{cfg.rag.provider}', collection='{cfg.rag.collection_name}')."
            )
    finally:
        if db_manager is not None:
            await db_manager.close()


if __name__ == "__main__":
    run_with_selector_loop(main())

