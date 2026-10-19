"""Testes de Integração da Borda, Worker, Handoff Humano e Admin API (`T043`)."""

import httpx
import pytest

from harness.app import build_container
from harness.edge.webhook import create_webhook_app
from harness.ops.admin_api import create_admin_app
from harness.outbound.providers.console import ConsoleOutboundProvider
from harness.settings import CognitionConfig, HarnessSettings


def _build_meta_text_payload(wamid: str, phone: str, text: str) -> dict[str, object]:
    return {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "WABA_1",
                "changes": [
                    {
                        "field": "messages",
                        "value": {
                            "messaging_product": "whatsapp",
                            "contacts": [{"profile": {"name": "Marina"}, "wa_id": phone}],
                            "messages": [
                                {
                                    "from": phone,
                                    "id": wamid,
                                    "timestamp": "1760000000",
                                    "type": "text",
                                    "text": {"body": text},
                                }
                            ],
                        },
                    }
                ],
            }
        ],
    }


@pytest.mark.asyncio
async def test_human_handoff_and_admin_api_end_to_end() -> None:
    """Valida o fluxo completo da User Story 4 (FR-015, FR-018, FR-019, SC-008):
    1. Autenticação obrigatória via `X-Admin-Api-Key` na Admin API.
    2. Mensagem recebida no webhook em modo `bot` -> processada pelo LangGraph e enviada no Outbound.
    3. Admin altera a thread para `mode = 'human'` via `PATCH /admin/threads/{id}/mode`.
    4. Nova mensagem do cliente -> Worker registra no histórico da conversa para o humano ver,
       marca o item como `done`, e NÃO aciona a LLM nem envia resposta automática.
    5. Admin consulta `/admin/threads/{id}/facts` e `/admin/queue/stats`.
    """
    settings = HarnessSettings(
        harness_env="test",
        admin_api_key="secret_admin_key_999",
        cognition=CognitionConfig(agent_mode="langgraph"),
    )
    # Desativa debounce (0s) para consumo imediato no teste
    settings.queue.debounce_seconds = 0.0

    container = await build_container(settings, force_in_memory=True)
    webhook_app = create_webhook_app(
        settings=settings,
        queue_enqueuer=container.queue_enqueuer,
        quarantine_repo=container.quarantine_repo,
        outbound_sender=container.outbound_sender,
        media_resolver=container.media_router.resolve_to_text,
        rate_limiter=container.rate_limiter.check_and_increment,
    )
    admin_app = create_admin_app(
        settings=settings,
        queue_consumer=container.queue_consumer,
        threads_repo=container.threads_repo,
        runs_repo=container.agent_run_repo,
    )

    assert isinstance(container.outbound_provider, ConsoleOutboundProvider)
    console_out = container.outbound_provider
    phone = "5511922221111"
    thread_id = f"wa:{phone}"
    admin_headers = {"X-Admin-Api-Key": "secret_admin_key_999"}

    async with (
        httpx.AsyncClient(
            transport=httpx.ASGITransport(app=webhook_app),
            base_url="http://edge.test",
        ) as edge_client,
        httpx.AsyncClient(
            transport=httpx.ASGITransport(app=admin_app),
            base_url="http://admin.test",
        ) as admin_client,
    ):
        # 1. Sem X-Admin-Api-Key deve retornar 401 Unauthorized
        unauth_resp = await admin_client.get("/admin/queue/stats")
        assert unauth_resp.status_code == 401

        # 2. Envia 1ª mensagem pelo Webhook com thread em modo 'bot'
        w_resp1 = await edge_client.post(
            "/webhook",
            json=_build_meta_text_payload(
                "wamid.handoff.1",
                phone,
                "Olá! Meu nome é Marina Costa e quero contratar o plano Starter.",
            ),
        )
        assert w_resp1.status_code == 200
        assert w_resp1.json()["disposition"] == "queued"

        # Worker processa o item -> LLM responde e Outbound envia
        await container.worker_pipeline.process_next("worker-1")
        assert len(console_out.sent_messages) == 1
        assert len(await container.agent_run_repo.list_recent_runs()) == 1

        # 3. Admin ativa Handoff Humano (`mode = 'human'`)
        patch_resp = await admin_client.patch(
            f"/admin/threads/{thread_id}/mode",
            headers=admin_headers,
            json={"mode": "human"},
        )
        assert patch_resp.status_code == 200
        assert patch_resp.json()["mode"] == "human"
        assert patch_resp.json()["is_bot_active"] is False

        # 4. Cliente envia 2ª mensagem enquanto está em atendimento humano
        w_resp2 = await edge_client.post(
            "/webhook",
            json=_build_meta_text_payload(
                "wamid.handoff.2",
                phone,
                "Atendente humano, você pode emitir o boleto para mim?",
            ),
        )
        assert w_resp2.status_code == 200

        # Caso o item tenha entrado na fila ou sido filtrado, garante que o worker não chama a LLM
        await container.worker_pipeline.process_next("worker-1")
        assert len(console_out.sent_messages) == 1  # Nenhuma nova mensagem enviada pelo robô!
        assert len(await container.agent_run_repo.list_recent_runs()) == 1  # Nenhum novo run de LLM!

        # 5. Admin inspeciona `/admin/threads/{thread_id}/facts` e `/admin/queue/stats`
        facts_resp = await admin_client.get(
            f"/admin/threads/{thread_id}/facts",
            headers=admin_headers,
        )
        assert facts_resp.status_code == 200
        facts_data = facts_resp.json()
        assert facts_data["mode"] == "human"
        assert facts_data["semantic_facts"].get("nome_cliente") == "Marina Costa"
        assert facts_data["semantic_facts"].get("plano_interesse") == "Starter"

        stats_resp = await admin_client.get("/admin/queue/stats", headers=admin_headers)
        assert stats_resp.status_code == 200
        assert stats_resp.json()["done"] >= 1

