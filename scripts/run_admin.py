"""Entrypoint do Processo 3: API Administrativa e de Operação (`admin` — T048)."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI

from harness.app import build_container
from harness.ops.admin_api import create_admin_app
from harness.settings import get_settings


def create_production_admin_app() -> FastAPI:
    settings = get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        container = await build_container(settings)
        inner_app = create_admin_app(
            settings=settings,
            queue_consumer=container.queue_consumer,
            threads_repo=container.threads_repo,
            runs_repo=container.agent_run_repo,
        )
        app.router.routes.extend(inner_app.router.routes)
        try:
            yield
        finally:
            if container.db_manager is not None:
                await container.db_manager.close()

    return FastAPI(title="WhatsApp Harness — Admin API", lifespan=lifespan)


if __name__ == "__main__":
    cfg = get_settings()
    uvicorn.run(
        "scripts.run_admin:create_production_admin_app",
        host=cfg.app.admin_host,
        port=cfg.app.admin_port,
        factory=True,
        reload=False,
    )

