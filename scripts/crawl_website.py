"""Script CLI para rastreamento e indexação de qualquer site corporativo no RAG (`scripts/crawl_website.py` — Spec 002, T058).

Uso:
    uv run python scripts/crawl_website.py --url https://mawwal.com.br --max-pages 15
    uv run python scripts/crawl_website.py --url https://sua-empresa.com.br
"""

import argparse

from langchain_text_splitters import RecursiveCharacterTextSplitter

from harness.cognition.retrievers.factory import (
    PGVectorRetrieverAdapter,
    VectorStoreFactory,
)
from harness.ingress.database import DatabasePoolManager, run_with_selector_loop
from harness.ingress.web_crawler import HttpWebsiteCrawlerAdapter
from harness.settings import get_settings


async def run_crawler_and_index(
    target_url: str,
    max_pages: int = 15,
    chunk_size: int = 800,
    chunk_overlap: int = 100,
) -> None:
    cfg = get_settings()
    db_manager: DatabasePoolManager | None = None

    print(f"\n[CRAWLER] Iniciando rastreamento do site: {target_url} (teto: {max_pages} paginas)...")

    crawler = HttpWebsiteCrawlerAdapter(timeout_seconds=10.0, request_delay_seconds=0.3)
    pages = await crawler.crawl_site(target_url, max_pages=max_pages)

    if not pages:
        print("[CRAWLER] [AVISO] Nenhuma pagina valida com conteudo foi extraida do site.")
        return

    print(f"[CRAWLER] [OK] {len(pages)} pagina(s) rastreada(s) com sucesso. Fatiando em chunks...")

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        separators=["\n## ", "\n### ", "\n\n", "\n", " "],
    )

    chunks_to_index: list[str] = []

    for page in pages:
        page_chunks = splitter.split_text(page.content)
        print(f"[CRAWLER] - '{page.title[:50]}...' -> {len(page_chunks)} chunk(s)")
        for idx, chunk in enumerate(page_chunks):
            entry = f"[{page.title} - Parte {idx + 1} | URL: {page.url}]\n{chunk.strip()}"
            chunks_to_index.append(entry)

    print(f"[CRAWLER] Indexando {len(chunks_to_index)} chunks no banco de dados vetorial...")

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

        if isinstance(retriever, PGVectorRetrieverAdapter):
            count = await retriever.seed_documents(chunks_to_index)
            print(f"[CRAWLER] [SUCESSO] {count} chunks indexados com sucesso na tabela knowledge_documents!")
        else:
            print("[CRAWLER] [INFO] Conexao com base vetorial realizada.")
    finally:
        if db_manager is not None:
            await db_manager.close()


def main() -> None:
    cfg = get_settings()
    default_url = cfg.website_crawler.target_url or "https://mawwal.com.br"
    default_max = cfg.website_crawler.max_pages or 15

    parser = argparse.ArgumentParser(
        description="Rastreador agnostico de sites corporativos para RAG."
    )
    parser.add_argument("--url", type=str, default=default_url, help="URL base do site")
    parser.add_argument("--max-pages", type=int, default=default_max, help="Maximo de paginas")
    parser.add_argument("--chunk-size", type=int, default=800, help="Tamanho dos chunks semanticos")

    args = parser.parse_args()

    run_with_selector_loop(
        run_crawler_and_index(
            target_url=args.url,
            max_pages=args.max_pages,
            chunk_size=args.chunk_size,
        )
    )


if __name__ == "__main__":
    main()
