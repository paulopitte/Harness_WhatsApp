"""Entrypoint do Processo 1: Borda HTTP (`webhook` — T026)."""

import uvicorn

from harness.app import build_container
from harness.edge.webhook import create_webhook_app
from harness.ingress.database import run_with_selector_loop
from harness.settings import get_settings


async def _serve() -> None:
    cfg = get_settings()
    container = await build_container(cfg)
    try:
        app = create_webhook_app(
            settings=cfg,
            queue_enqueuer=container.queue_enqueuer,
            quarantine_repo=container.quarantine_repo,
            outbound_sender=container.outbound_sender,
            media_resolver=container.media_router.resolve_to_text,
            rate_limiter=container.rate_limiter.check_and_increment,
        )
        config = uvicorn.Config(
            app=app,
            host=cfg.app.webhook_host,
            port=cfg.app.webhook_port,
        )
        server = uvicorn.Server(config)
        await server.serve()
    finally:
        if container.db_manager is not None:
            await container.db_manager.close()


if __name__ == "__main__":
    run_with_selector_loop(_serve())
