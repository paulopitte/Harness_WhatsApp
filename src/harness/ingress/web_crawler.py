"""Rastreador Agnóstico de Sites Corporativos (`ingress/web_crawler.py` — Spec 002, T057).

Equivalente no C#/.NET: `WebCrawlerService : IWebsiteCrawler`
que rastreia páginas, descarta tags HTML supérfluas (scripts/estilos) e extrai
conteúdo semântico de qualquer site corporativo (e-commerce, clínica, escritório, etc.).
"""

import asyncio
import re
from urllib.parse import urljoin, urlparse

import httpx
import structlog
from bs4 import BeautifulSoup

from harness.domain.ports import CrawledPage

logger = structlog.get_logger(component="web-crawler")


class HttpWebsiteCrawlerAdapter:
    """Rastreador web assíncrono para sites corporativos com limpeza HTML e controle de profundidade."""

    def __init__(
        self,
        *,
        timeout_seconds: float = 10.0,
        request_delay_seconds: float = 0.2,
        user_agent: str = "WhatsAppHarnessBot/1.0 (+https://github.com/paulopitte/harness-whatsapp)",
    ) -> None:
        self._timeout_seconds = timeout_seconds
        self._request_delay_seconds = request_delay_seconds
        self._user_agent = user_agent

    async def crawl_site(self, base_url: str, max_pages: int = 50) -> list[CrawledPage]:
        clean_base = base_url.strip()
        if not clean_base:
            return []

        parsed_base = urlparse(clean_base)
        base_domain = parsed_base.netloc.lower()

        visited: set[str] = set()
        queue: list[str] = [clean_base]
        crawled_pages: list[CrawledPage] = []

        headers = {"User-Agent": self._user_agent}

        async with httpx.AsyncClient(
            timeout=self._timeout_seconds,
            headers=headers,
            follow_redirects=True,
        ) as client:
            while queue and len(crawled_pages) < max_pages:
                current_url = queue.pop(0)
                normalized_url = current_url.split("#")[0].rstrip("/")
                if normalized_url in visited:
                    continue
                visited.add(normalized_url)

                try:
                    response = await client.get(current_url)
                    if response.status_code != 200:
                        continue

                    content_type = response.headers.get("content-type", "")
                    if "text/html" not in content_type:
                        continue

                    page = self._parse_html(current_url, response.text)
                    if page is not None and len(page.content) > 50:
                        crawled_pages.append(page)

                    # Coleta links internos do mesmo domínio
                    if len(crawled_pages) < max_pages:
                        new_links = self._extract_internal_links(
                            current_url, base_domain, response.text
                        )
                        for link in new_links:
                            norm = link.split("#")[0].rstrip("/")
                            if norm not in visited and norm not in queue:
                                queue.append(link)

                    if self._request_delay_seconds > 0:
                        await asyncio.sleep(self._request_delay_seconds)

                except Exception as exc:
                    logger.warning("crawl_page_failed", url=current_url, error=str(exc))
                    continue

        return crawled_pages

    def _parse_html(self, url: str, html_content: str) -> CrawledPage | None:
        soup = BeautifulSoup(html_content, "html.parser")

        # Remove elementos irrelevantes para o RAG
        for tag in soup(["script", "style", "nav", "footer", "iframe", "noscript"]):
            tag.decompose()

        title_tag = soup.find("title")
        title = title_tag.get_text().strip() if title_tag else url

        # Extrai textos principais priorizando artigos, seções ou corpo
        main_container = soup.find("main") or soup.find("article") or soup.body
        if not main_container:
            return None

        # Limpeza e normalização de espaços em branco
        raw_text = main_container.get_text(separator="\n")
        cleaned_text = re.sub(r"\n\s*\n+", "\n\n", raw_text).strip()

        # Metadados adicionais
        meta_desc = ""
        meta_tag = soup.find("meta", attrs={"name": "description"})
        if meta_tag and isinstance(meta_tag, dict) and "content" in meta_tag:
            meta_desc = str(meta_tag["content"]).strip()

        metadata = {
            "source": "web_crawler",
            "url": url,
            "description": meta_desc,
        }

        return CrawledPage(
            url=url,
            title=title,
            content=cleaned_text,
            metadata=metadata,
        )

    def _extract_internal_links(
        self, current_url: str, base_domain: str, html_content: str
    ) -> list[str]:
        soup = BeautifulSoup(html_content, "html.parser")
        links: list[str] = []

        for a_tag in soup.find_all("a", href=True):
            raw_href = str(a_tag["href"]).strip()
            if not raw_href or raw_href.startswith(
                ("mailto:", "tel:", "javascript:", "#")
            ):
                continue

            absolute_url = urljoin(current_url, raw_href)
            parsed = urlparse(absolute_url)

            # Apenas links do mesmo domínio e protocolo HTTP/HTTPS (sem arquivos de mídia)
            is_same_domain = (
                parsed.netloc.lower() == base_domain
                and parsed.scheme in ("http", "https")
            )
            is_not_binary = not parsed.path.lower().endswith(
                (".png", ".jpg", ".jpeg", ".gif", ".svg", ".pdf", ".zip", ".mp4")
            )
            if is_same_domain and is_not_binary:
                links.append(absolute_url)

        return links


class DeterministicStubWebsiteCrawlerAdapter:
    """Adaptador de teste para simulação determinística de rastreamento."""

    def __init__(self, stub_pages: list[CrawledPage] | None = None) -> None:
        self.stub_pages = stub_pages or [
            CrawledPage(
                url="https://exemplo.com.br/produtos/perfume-malek",
                title="Perfume Malek Eau de Parfum 100ml — Mawwal Arábia",
                content="Fragrância marcante com notas de oud real, âmbar e madeiras preciosas. Preço: R$ 489,00.",
                metadata={"category": "perfumes"},
            )
        ]

    async def crawl_site(self, base_url: str, max_pages: int = 50) -> list[CrawledPage]:
        return self.stub_pages[:max_pages]
