"""Runner Concorrente de Workers Assíncronos (`WorkerRunner` — T024).

Equivalente no C#/.NET: `BackgroundService` (`ExecuteAsync(CancellationToken stoppingToken)`)
executando múltiplas corrotinas concorrentes que consomem a fila via `SKIP LOCKED`.
"""

import asyncio

from harness.workers.pipeline import ProcessQueueItemPipeline


class WorkerRunner:
    """Gerencia N corrotinas de worker fazendo polling e processando a fila com graceful shutdown."""

    def __init__(
        self,
        pipeline: ProcessQueueItemPipeline,
        *,
        concurrency: int = 4,
        poll_interval_seconds: float = 0.5,
    ) -> None:
        self._pipeline = pipeline
        self._concurrency = max(1, concurrency)
        self._poll_interval = max(0.05, poll_interval_seconds)
        self._stop_event = asyncio.Event()

    def request_stop(self) -> None:
        """Sinaliza parada graciosa para todas as corrotinas do worker."""
        self._stop_event.set()

    async def _worker_loop(self, worker_id: str) -> None:
        while not self._stop_event.is_set():
            processed = await self._pipeline.process_next(worker_id=worker_id)
            if processed is None:
                try:
                    await asyncio.wait_for(self._stop_event.wait(), timeout=self._poll_interval)
                except TimeoutError:
                    continue

    async def run_forever(self) -> None:
        """Inicia o pool de workers concorrentes até que `request_stop()` seja chamado."""
        tasks = [
            asyncio.create_task(self._worker_loop(f"worker-{idx + 1}"))
            for idx in range(self._concurrency)
        ]
        try:
            await asyncio.gather(*tasks)
        except asyncio.CancelledError:
            self.request_stop()
            await asyncio.gather(*tasks, return_exceptions=True)

