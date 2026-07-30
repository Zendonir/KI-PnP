"""Worker fuer Medienauftraege (Sprachausgabe, spaeter Bilder).

Der Worker ist bewusst entkoppelt: der Spielfluss haengt nie an ihm. Er holt
offene Auftraege aus der Datenbank, laesst sie vom konfigurierten Anbieter
erzeugen, legt die Aufnahme in der Datenbank ab und meldet den Clients per
WebSocket, dass Ton bereitsteht.

Start:  ``python -m app.workers.media``
"""

from __future__ import annotations

import asyncio
import logging
import signal
from datetime import timedelta

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.container import Container
from app.db.base import utcnow
from app.db.models import AudioJob
from app.services import events as ev
from app.tts.providers import SpeechRequest

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-8s %(message)s")
logger = logging.getLogger("kipnp.worker")

_POLL_SECONDS = 3.0
_BATCH = 5
_STALE_AFTER = timedelta(minutes=10)


async def recover_stale_jobs(session: AsyncSession) -> int:
    """Setzt haengengebliebene Auftraege zurueck.

    Wird der Worker mitten in einem Auftrag beendet, bliebe dieser sonst
    dauerhaft auf ``running`` stehen und niemand wuerde ihn erneut anfassen.
    """
    cutoff = utcnow() - _STALE_AFTER
    result = await session.execute(
        sa.update(AudioJob)
        .where(AudioJob.status == "running", AudioJob.updated_at < cutoff)
        .values(status="pending")
        # Reines SQL statt Auswertung in Python: schneller und unabhaengig
        # davon, was gerade in der Sitzung liegt.
        .execution_options(synchronize_session=False)
    )
    await session.commit()
    return int(result.rowcount or 0)


async def prune_audio(session: AsyncSession, game_id, keep_last: int) -> int:
    """Gibt die Audiodaten aelterer Aufnahmen einer Runde frei.

    Der Auftrag selbst bleibt als Protokolleintrag erhalten, nur die Bytes
    verschwinden -- eine Kampagne ueber viele Abende laesst die Datenbank so
    nicht unbegrenzt wachsen.
    """
    keep_ids = (
        sa.select(AudioJob.id)
        .where(AudioJob.game_id == game_id, AudioJob.data.isnot(None))
        .order_by(AudioJob.created_at.desc())
        .limit(keep_last)
        .scalar_subquery()
    )
    result = await session.execute(
        sa.update(AudioJob)
        .where(
            AudioJob.game_id == game_id,
            AudioJob.data.isnot(None),
            AudioJob.id.notin_(keep_ids),
        )
        .values(data=None)
        .execution_options(synchronize_session=False)
    )
    return int(result.rowcount or 0)


async def process_once(container: Container, settings: Settings) -> int:
    """Bearbeitet einen Schwung offener Auftraege. Gibt deren Anzahl zurueck."""
    async with container.database.session() as session:
        stmt = (
            sa.select(AudioJob)
            .where(AudioJob.status == "pending")
            .order_by(AudioJob.created_at.asc())
            .limit(_BATCH)
        )
        jobs = list((await session.execute(stmt)).scalars().all())
        if not jobs:
            return 0

        # Sofort beanspruchen, damit ein zweiter Worker sie nicht doppelt holt.
        for job in jobs:
            job.status = "running"
        await session.commit()

        for job in jobs:
            try:
                result = await container.tts.synthesize(
                    SpeechRequest(
                        text=job.text,
                        voice=job.voice,
                        speed=job.speed,
                        mood=str((job.meta or {}).get("mood", "")),
                    )
                )
            except Exception as exc:  # noqa: BLE001 - ein Auftrag darf den Worker nie stoppen
                logger.exception("Auftrag %s fehlgeschlagen", job.id)
                job.status = "failed"
                job.error = str(exc)[:500]
            else:
                if result.status == "ready" and result.audio:
                    job.status = "ready"
                    job.data = result.audio
                    job.mime_type = result.mime_type
                    job.size_bytes = len(result.audio)
                    job.url = f"/api/v1/games/{job.game_id}/audio/{job.id}"
                    job.error = None
                    job.meta = {**(job.meta or {}), **result.meta}
                elif result.status == "skipped":
                    job.status = "skipped"
                else:
                    job.status = "failed"
                    job.error = result.error or "Unbekannter Fehler"

            if job.status == "ready":
                logger.info("Auftrag %s bereit (%d Bytes)", job.id, job.size_bytes)
                await prune_audio(session, job.game_id, settings.audio_keep_last)
            else:
                logger.warning("Auftrag %s -> %s (%s)", job.id, job.status, job.error)

        await session.commit()

        # Erst nach dem Speichern melden, damit die Clients die Aufnahme
        # auch wirklich abrufen koennen.
        for job in jobs:
            await container.hub.publish(
                job.game_id,
                "event",
                {
                    "type": ev.AUDIO_READY if job.status == "ready" else "audio.failed",
                    "payload": {
                        "audio_id": str(job.id),
                        "status": job.status,
                        "url": job.url,
                        "text": job.text,
                        "voice": job.voice,
                        "provider": job.provider,
                        "mime_type": job.mime_type,
                        "error": job.error,
                    },
                },
            )
        return len(jobs)


async def main() -> None:
    """Endlosschleife mit sauberem Herunterfahren."""
    settings = get_settings()
    container = Container.create(settings)
    await container.startup()
    stopping = asyncio.Event()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stopping.set)

    logger.info(
        "Medien-Worker gestartet (TTS=%s, serverseitig=%s)",
        container.tts.name,
        container.tts.server_side,
    )
    if not container.tts.server_side:
        logger.info(
            "Der eingestellte Anbieter erzeugt kein Audio auf dem Server. "
            "Der Worker laeuft mit, hat aber nichts zu tun."
        )

    try:
        async with container.database.session() as session:
            recovered = await recover_stale_jobs(session)
        if recovered:
            logger.info("%d haengende Auftraege zurueckgesetzt.", recovered)

        while not stopping.is_set():
            try:
                handled = await process_once(container, settings)
            except Exception:  # noqa: BLE001 - z. B. Neustart der Datenbank
                logger.exception("Durchlauf fehlgeschlagen, versuche es erneut")
                handled = 0
            if handled == 0:
                try:
                    await asyncio.wait_for(stopping.wait(), timeout=_POLL_SECONDS)
                except TimeoutError:
                    continue
    finally:
        await container.shutdown()
        logger.info("Medien-Worker beendet.")


if __name__ == "__main__":
    asyncio.run(main())
