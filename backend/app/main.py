"""Einstiegspunkt der FastAPI-Anwendung."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as installed_version

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_router, ws_router
from app.core.config import Settings, get_settings
from app.core.container import Container
from app.core.errors import register_exception_handlers
from app.core.logging import HealthCheckLogFilter

try:
    APP_VERSION = installed_version("ki-pnp-backend")
except PackageNotFoundError:  # z. B. beim Ausfuehren ohne Installation (Tests)
    APP_VERSION = "0.0.0-dev"

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(levelname)-8s %(name)s: %(message)s"
)
logger = logging.getLogger(__name__)

_access_logger = logging.getLogger("uvicorn.access")
if not any(isinstance(f, HealthCheckLogFilter) for f in _access_logger.filters):
    # uvicorn baut seine Logger-Konfiguration beim Start von Config() auf --
    # vor dem Import dieses Moduls (der ueber den App-Importpfad "app.main:app"
    # erst beim anschliessenden config.load_app() erfolgt). Der Filter laesst
    # sich also hier gefahrlos anhaengen, ohne von uvicorns eigener
    # Konfiguration ueberschrieben zu werden. Die Existenzpruefung verhindert
    # doppelte Filter, falls dieses Modul mehrfach importiert wird (Tests).
    _access_logger.addFilter(HealthCheckLogFilter())

DESCRIPTION = """\
Backend der KI-gestuetzten Pen-&-Paper-Plattform.

Grundsatz: Die Datenbank ist die einzige Wahrheit. Das Backend verwaltet
saemtliche Spiellogik, wuerfelt und validiert jede Zustandsaenderung. Die KI
erzaehlt, bewertet Ergebnisse und liefert ausschliesslich Vorschlaege.
"""


def create_app(settings: Settings | None = None, container: Container | None = None) -> FastAPI:
    """Baut die Anwendung.

    ``container`` laesst sich in Tests ersetzen, um KI, Datenbank oder
    Realtime-Hub gezielt auszutauschen.
    """
    resolved = settings or get_settings()
    app_container = container or Container.create(resolved)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.container = app_container
        await app_container.startup()
        logger.info(
            "KI-PnP gestartet (Umgebung=%s, KI=%s, TTS=%s)",
            resolved.environment,
            app_container.llm.name,
            app_container.tts.name,
        )
        try:
            yield
        finally:
            await app_container.shutdown()

    app = FastAPI(
        title="KI-PnP",
        description=DESCRIPTION,
        version=APP_VERSION,
        lifespan=lifespan,
        openapi_url="/api/openapi.json",
        docs_url="/api/docs",
    )
    app.state.container = app_container

    app.add_middleware(
        CORSMiddleware,
        allow_origins=resolved.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    register_exception_handlers(app)
    app.include_router(api_router, prefix="/api/v1")
    app.include_router(ws_router, prefix="/api/v1")

    @app.get("/api/health", tags=["system"])
    async def health() -> dict[str, str]:
        """Einfacher Gesundheitscheck fuer Container und Reverse Proxy.

        Nennt auch Version und Commit -- sonst laesst sich einem laufenden
        Container nicht ansehen, ob ein ":latest"-Zug tatsaechlich einen
        neuen Stand gebracht hat.
        """
        return {
            "status": "ok",
            "version": APP_VERSION,
            "git_sha": resolved.git_sha,
            "ai_provider": app_container.llm.name,
            "tts_provider": app_container.tts.name,
        }

    return app


app = create_app()
