"""Entrypoint do Processo 1: Borda HTTP (`webhook` — T026)."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
import uvicorn

from harness.app import build_container
from harness.edge.webhook import create_webhook_app
from harness.settings import get_settings


def create_production_webhook_app() -> FastAPI:
    settings = get_settings()
    container_holder: dict[str, object] = {}

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        container = await build_container(settings)
        container_holder["c"] = container
        inner_app = create_webhook_app(
            settings=settings,
            queue_enqueuer=container.queue_enqueuer,
            quarantine_repo=container.quarantine_repo,
            outbound_sender=container.outbound_sender,
        )
        app.router.routes.extend(inner_app.router.routes)
        try:
            yield
        finally:
            if container.db_manager is not None:
                await container.db_manager.close()

    return FastAPI(title="WhatsApp Harness — Edge Webhook", lifespan=lifespan)


if __name__ == "__main__":
    cfg = get_settings()
    uvicorn.run(
        "scripts.run_webhook:create_production_webhook_app",
        host=cfg.app.webhook_host,
        port=cfg.app.webhook_port,
        factory=True,
        reload=False,
    )

