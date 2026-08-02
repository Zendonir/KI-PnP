"""Logging-Feinschliff, der ueber die Standardkonfiguration hinausgeht."""

from __future__ import annotations

import logging

_HEALTH_PATH = "/api/health"


class HealthCheckLogFilter(logging.Filter):
    """Zeigt Zugriffs-Logs fuer den Gesundheitscheck nur bei Zustandswechsel.

    Docker/Reverse-Proxy fragen ``/api/health`` alle paar Sekunden ab. Bei
    dauerhaftem "200 OK" fuellt jede einzelne Antwort das Log, ohne neue
    Information zu liefern. Diese Filterung laesst nur den ersten Aufruf,
    jeden Wechsel von "io" (ok) auf "nio" (Fehler) und die anschliessende
    Erholung durch -- ein unveraendert bleibender Zustand wird unterdrueckt.
    Alle anderen Pfade sind unberuehrt.
    """

    def __init__(self) -> None:
        super().__init__()
        self._last_ok: bool | None = None

    def filter(self, record: logging.LogRecord) -> bool:
        # uvicorns Zugriffslog ruft mit den Positionsargumenten
        # (client_addr, method, path, http_version, status) auf -- siehe
        # uvicorn.protocols.http.{h11,httptools}_impl. Alles, was nicht in
        # dieses Muster passt (z. B. ein anderer Logeintrag desselben
        # Loggers), bleibt unangetastet sichtbar.
        args = record.args
        if not isinstance(args, tuple) or len(args) < 5:
            return True
        path = str(args[2]).split("?", 1)[0]
        if path != _HEALTH_PATH:
            return True
        try:
            status = int(args[4])  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return True

        ok = status < 400
        show = ok != self._last_ok
        self._last_ok = ok
        return show
