"""Tests fuer den Gesundheitscheck-Log-Filter.

Docker/Reverse-Proxy fragen /api/health alle paar Sekunden ab -- bei
dauerhaftem "200 OK" fuellt jede einzelne Antwort das Log ohne neuen
Informationsgehalt. Der Filter zeigt nur den ersten Aufruf sowie jeden
Zustandswechsel (io -> nio -> io).
"""

from __future__ import annotations

import logging

from app.core.logging import HealthCheckLogFilter


def _access_record(path: str, status: int) -> logging.LogRecord:
    """Baut einen Log-Eintrag im selben Format wie uvicorns Zugriffslog."""
    return logging.LogRecord(
        name="uvicorn.access",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg='%s - "%s %s HTTP/%s" %d',
        args=("127.0.0.1:1234", "GET", path, "1.1", status),
        exc_info=None,
    )


class TestGesundheitscheckFilter:
    def test_erster_aufruf_wird_gezeigt(self) -> None:
        assert HealthCheckLogFilter().filter(_access_record("/api/health", 200)) is True

    def test_wiederholtes_ok_wird_unterdrueckt(self) -> None:
        f = HealthCheckLogFilter()
        assert f.filter(_access_record("/api/health", 200)) is True
        assert f.filter(_access_record("/api/health", 200)) is False
        assert f.filter(_access_record("/api/health", 200)) is False

    def test_fehlschlag_wird_gezeigt_und_danach_unterdrueckt(self) -> None:
        f = HealthCheckLogFilter()
        assert f.filter(_access_record("/api/health", 200)) is True
        assert f.filter(_access_record("/api/health", 500)) is True
        assert f.filter(_access_record("/api/health", 500)) is False

    def test_erholung_nach_fehlschlag_wird_wieder_gezeigt(self) -> None:
        f = HealthCheckLogFilter()
        f.filter(_access_record("/api/health", 200))
        f.filter(_access_record("/api/health", 503))
        assert f.filter(_access_record("/api/health", 200)) is True
        assert f.filter(_access_record("/api/health", 200)) is False

    def test_andere_pfade_bleiben_unberuehrt(self) -> None:
        f = HealthCheckLogFilter()
        assert f.filter(_access_record("/api/v1/games", 200)) is True
        assert f.filter(_access_record("/api/v1/games", 200)) is True
        assert f.filter(_access_record("/api/v1/games", 200)) is True

    def test_pfad_mit_query_string_wird_erkannt(self) -> None:
        f = HealthCheckLogFilter()
        assert f.filter(_access_record("/api/health?probe=1", 200)) is True
        assert f.filter(_access_record("/api/health", 200)) is False

    def test_unerwartetes_format_bleibt_sichtbar(self) -> None:
        f = HealthCheckLogFilter()
        record = logging.LogRecord(
            name="uvicorn.access",
            level=logging.INFO,
            pathname=__file__,
            lineno=1,
            msg="Started server process [%d]",
            args=(1234,),
            exc_info=None,
        )
        assert f.filter(record) is True
