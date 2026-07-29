#!/usr/bin/env bash
# Wartet auf die Datenbank, spielt Migrationen ein und startet die Anwendung.
set -euo pipefail

echo "[kipnp] warte auf die Datenbank ..."
python - <<'PY'
import asyncio
import sys

from sqlalchemy.ext.asyncio import create_async_engine

from app.core.config import get_settings


async def wait() -> None:
    engine = create_async_engine(get_settings().database_url)
    for attempt in range(1, 61):
        try:
            async with engine.connect():
                print("[kipnp] Datenbank erreichbar.")
                await engine.dispose()
                return
        except Exception as exc:  # noqa: BLE001
            print(f"[kipnp] Versuch {attempt}/60: {exc}")
            await asyncio.sleep(2)
    await engine.dispose()
    sys.exit("[kipnp] Datenbank nicht erreichbar.")


asyncio.run(wait())
PY

echo "[kipnp] spiele Migrationen ein ..."
alembic upgrade head

echo "[kipnp] starte Anwendung: $*"
exec "$@"
