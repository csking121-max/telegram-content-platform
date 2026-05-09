"""
Worker entry-point — polls Redis queues and dispatches tasks.

Each worker type runs in its own asyncio loop.
The Docker Compose service starts this file; the ``WORKER_TYPE`` env var
selects which worker to run (delivery | deletion | credit | backup | all).
"""

from __future__ import annotations

import asyncio
import logging
import os
import signal
import sys

from dotenv import load_dotenv

# Ensure the project root is importable
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

load_dotenv()

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger("workers.main")


async def _run_all() -> None:
    """Import workers lazily and run selected type(s)."""
    from workers.delivery_worker import DeliveryWorker
    from workers.deletion_worker import DeletionWorker
    from workers.credit_worker import CreditWorker
    from workers.daily_credit_worker import DailyCreditWorker
    from workers.expiry_worker import ExpiryWorker
    from workers.expiry_notify_worker import ExpiryNotifyWorker
    from workers.payment_recheck_worker import PaymentRecheckWorker
    from workers.low_credit_notify_worker import LowCreditNotifyWorker
    from workers.backup_worker import BackupWorker

    worker_type = os.getenv("WORKER_TYPE", "all").lower()

    async def _supervised(name: str, coro_factory):
        """Run a worker with automatic restart on crash."""
        while True:
            try:
                await coro_factory()
            except asyncio.CancelledError:
                logger.info("Worker %s cancelled", name)
                raise
            except Exception:
                logger.exception("Worker %s crashed — restarting in 5s", name)
                await asyncio.sleep(5)

    tasks: list[asyncio.Task] = []

    if worker_type in ("delivery", "all"):
        tasks.append(asyncio.create_task(_supervised("delivery", lambda: DeliveryWorker().run())))
    if worker_type in ("deletion", "all"):
        tasks.append(asyncio.create_task(_supervised("deletion", lambda: DeletionWorker().run())))
    if worker_type in ("credit", "all"):
        tasks.append(asyncio.create_task(_supervised("credit", lambda: CreditWorker().run())))
    if worker_type in ("daily_credit", "all"):
        tasks.append(asyncio.create_task(_supervised("daily_credit", lambda: DailyCreditWorker().run())))
    if worker_type in ("expiry", "all"):
        tasks.append(asyncio.create_task(_supervised("expiry", lambda: ExpiryWorker().run())))
    if worker_type in ("expiry_notify", "all"):
        tasks.append(asyncio.create_task(_supervised("expiry_notify", lambda: ExpiryNotifyWorker().run())))
    if worker_type in ("payment_recheck", "all"):
        tasks.append(asyncio.create_task(_supervised("payment_recheck", lambda: PaymentRecheckWorker().run())))
    if worker_type in ("low_credit_notify", "all"):
        tasks.append(asyncio.create_task(_supervised("low_credit_notify", lambda: LowCreditNotifyWorker().run())))
    if worker_type in ("backup", "all"):
        tasks.append(asyncio.create_task(_supervised("backup", lambda: BackupWorker().run())))

    if not tasks:
        logger.error("Unknown WORKER_TYPE=%s", worker_type)
        return

    logger.info("Starting %d worker task(s) (type=%s) …", len(tasks), worker_type)

    # Graceful shutdown on SIGTERM / SIGINT
    loop = asyncio.get_running_loop()
    shutdown_event = asyncio.Event()

    def _signal_handler() -> None:
        logger.info("Shutdown signal received — cancelling workers …")
        shutdown_event.set()
        for t in tasks:
            t.cancel()

    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, _signal_handler)
        except NotImplementedError:
            # Windows doesn't support add_signal_handler; fall back
            signal.signal(sig, lambda s, f: _signal_handler())

    try:
        await asyncio.gather(*tasks)
    except asyncio.CancelledError:
        logger.info("Workers cancelled — shutting down gracefully.")


def main() -> None:
    asyncio.run(_run_all())


if __name__ == "__main__":
    main()
