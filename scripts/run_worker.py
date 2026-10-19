"""Entrypoint do Processo 2: Worker Assíncrono (`worker` — T026)."""

import asyncio
import contextlib
import signal

from harness.app import build_container
from harness.ingress.database import run_with_selector_loop
from harness.settings import get_settings


async def main() -> None:
    settings = get_settings()
    container = await build_container(settings)

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        with contextlib.suppress(NotImplementedError):
            loop.add_signal_handler(sig, container.worker_runner.request_stop)

    print(
        f"⚙️  [WorkerRunner] Iniciando {settings.queue.worker_concurrency} workers concorrentes "
        f"(mode={settings.cognition.agent_mode}, debounce={settings.queue.debounce_seconds}s)..."
    )
    try:
        await container.worker_runner.run_forever()
    finally:
        if container.db_manager is not None:
            await container.db_manager.close()


if __name__ == "__main__":
    try:
        run_with_selector_loop(main())
    except KeyboardInterrupt:
        print("\n[WorkerRunner] Encerrado pelo usuário.")

