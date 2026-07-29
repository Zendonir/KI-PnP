"""Worker fuer Medienauftraege (Sprachausgabe, spaeter Bilder).

Der Worker ist bewusst optional: der Spielfluss haengt nie an ihm. Er holt
offene Auftraege aus der Datenbank, laesst sie vom konfigurierten Anbieter
erzeugen und schreibt das Ergebnis zurueck.

Start:  ``python -m app.workers.media``
"""

from __future__ import annotations

import asyncio
import logging
import signal

import sqlalchemy as sa

from app.core.config import get_settings
from app.core.container import Container
from app.db.models import AudioJob
from app.tts.providers import SpeechRequest

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-8s %(message)s")
logger = logging.getLogger("kipnp.worker")

_POLL_SECONDS = 3.0
_BATCH = 5


async def process_once(container: Container) -> int:
    """Bearbeitet einen Schwung offener Auftraege. Gibt deren Anzahl zurueck."""
    async with container.database.session() as session:
        stmt = (
            sa.select(AudioJob)
            .where(AudioJob.status == "pending")
            .order_by(AudioJob.created_at.asc())
            .limit(_BATCH)
        )
        jobs = list((await session.execute(stmt)).scalars().all())
        for job in jobs:
            job.status = "running"
        await session.commit()

        for job in jobs:
            try:
                result = await container.tts.synthesize(
                    SpeechRequest(
                        text=job.text,
                        voice=job.voice,
                        mood=str(job.meta.get("mood", "")),
                    )
                )
                job.status = result.status if result.status != "pending" else "failed"
                job.url = result.url
                job.error = result.error
            except Exception as exc:  # noqa: BLE001 - ein Auftrag darf den Worker nie stoppen
                logger.exception("Auftrag %s fehlgeschlagen", job.id)
                job.status = "failed"
                job.error = str(exc)
            else:
                logger.info("Auftrag %s -> %s", job.id, job.status)
            await container.hub.publish(
                job.game_id,
                "audio.updated",
                {"audio_id": str(job.id), "status": job.status, "url": job.url},
            )
        await session.commit()
        return len(jobs)


async def main() -> None:
    """Endlosschleife mit sauberem Herunterfahren."""
    container = Container.create(get_settings())
    await container.startup()
    stopping = asyncio.Event()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stopping.set)

    logger.info("Medien-Worker gestartet (TTS=%s)", container.tts.name)
    try:
        while not stopping.is_set():
            handled = await process_once(container)
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
