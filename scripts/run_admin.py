"""Entrypoint do Processo 3: API Administrativa e de Operação (`admin` — T048)."""

import uvicorn

from harness.app import build_container
from harness.ingress.database import run_with_selector_loop
from harness.ops.admin_api import create_admin_app
from harness.settings import get_settings


async def _serve() -> None:
    cfg = get_settings()
    container = await build_container(cfg)
    try:
        app = create_admin_app(
            settings=cfg,
            queue_consumer=container.queue_consumer,
            threads_repo=container.threads_repo,
            runs_repo=container.agent_run_repo,
        )
        config = uvicorn.Config(
            app=app,
            host=cfg.app.admin_host,
            port=cfg.app.admin_port,
        )
        server = uvicorn.Server(config)
        await server.serve()
    finally:
        if container.db_manager is not None:
            await container.db_manager.close()


if __name__ == "__main__":
    run_with_selector_loop(_serve())
