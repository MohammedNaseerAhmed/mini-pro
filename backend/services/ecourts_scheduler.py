"""
backend/services/ecourts_scheduler.py

Background scheduler for periodic eCourts data refresh.
Currently a stub — runs no-ops to keep the startup/shutdown lifecycle intact.
"""

import logging

logger = logging.getLogger(__name__)
_scheduler = None


def sync_all_active_cases():
    """Background task to refresh eCourts data for all tracked cases."""
    # Future: iterate over CNR mappings in Mongo and call sync_with_captcha
    logger.debug("[eCourts] Nightly sync task placeholder — no-op.")


def start_ecourts_scheduler() -> None:
    """Start the background scheduler (no-op stub)."""
    logger.info("[eCourts] Scheduler stub initialised (nightly sync not yet active).")


def stop_ecourts_scheduler() -> None:
    """Stop the background scheduler (no-op stub)."""
    global _scheduler
    if _scheduler is not None:
        try:
            _scheduler.shutdown(wait=False)
        except Exception:
            pass
        _scheduler = None
    logger.info("[eCourts] Scheduler stopped.")
