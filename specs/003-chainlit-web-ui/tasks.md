# Tasks: Interface Web Interativa com Chainlit (003-chainlit-web-ui)

> **SpecKit — Checklist de Tarefas (TDD)**  
> *Continuidade sequencial a partir da Tarefa T061 da Fase 2.*

---

## 📋 Lista de Tarefas (P1 a P2)

- [x] **T062**: Instalar e homologar a dependência `chainlit` no ambiente virtual com `uv`.
- [x] **T063**: Implementar o entrypoint `scripts/run_chainlit.py` conectando o `build_container` da Harness ao ciclo de vida do Chainlit.
- [x] **T064**: Configurar a personalização visual em `.chainlit/config.toml` (nome do assistente, tema e descrições).
- [x] **T065**: Criar testes unitários em `tests/unit/test_chainlit_entrypoint.py` validando o binding de sessões e `ThreadId`.
- [x] **T066**: Atualizar o `README.md` com as instruções para rodar a interface web com `uv run chainlit run scripts/run_chainlit.py --port 8002`.

