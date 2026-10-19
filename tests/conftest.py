"""Fixtures globais do Pytest para a suíte de testes da WhatsApp Harness."""

import pytest

from harness.settings import HarnessSettings


@pytest.fixture
def test_settings() -> HarnessSettings:
    """Retorna uma instância isolada de HarnessSettings carregada do YAML padrão."""
    return HarnessSettings.load("configs/harness.yaml")

