"""Script utilitário para aplicar o schema inicial do banco PostgreSQL 16 + pgvector."""

import sys
from pathlib import Path

from harness.ingress.database import DatabasePoolManager, run_with_selector_loop
from harness.settings import get_settings


async def main() -> None:
    settings = get_settings()
    migration_file = Path("migrations/001_initial_schema.sql")
    if not migration_file.exists():
        print(f"[ERRO] Arquivo de migração não encontrado: {migration_file}", file=sys.stderr)
        sys.exit(1)

    db = DatabasePoolManager(settings.database_url, min_size=1, max_size=2)
    try:
        print(f"Conectando ao PostgreSQL e aplicando {migration_file}...")
        await db.apply_migration(migration_file)
        print("[OK] Schema inicial aplicado com sucesso!")
    finally:
        await db.close()


if __name__ == "__main__":
    run_with_selector_loop(main())
