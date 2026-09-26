"""Single worker thread and job queue for SiliconRoute.

Enforces the hard rule that only one benchmark/measurement job runs at any
given time, returning HTTP 409 if a second job is submitted while busy.
"""

import logging
import queue
import threading
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)

_jobs: queue.Queue = queue.Queue()
_lock = threading.Lock()

# Global state of the currently executing job
current_job: dict[str, Any] = {
    "session_id": None,
    "done": 0,
    "total": 0,
    "item": None,
    "cancel": False,
}

_worker_thread: Optional[threading.Thread] = None
_stop_event = threading.Event()


def try_submit(session_id: int, fn: Callable[[dict[str, Any]], None]) -> bool:
    """Attempt to submit a job. Returns False if a job is already in progress."""
    with _lock:
        if current_job["session_id"] is not None:
            return False
        current_job.update(
            session_id=session_id,
            done=0,
            total=0,
            item=None,
            cancel=False,
        )
    _jobs.put((session_id, fn))
    return True


def cancel_job(session_id: int) -> bool:
    """Request cancellation for the currently executing job."""
    with _lock:
        if current_job["session_id"] == session_id:
            current_job["cancel"] = True
            return True
    return False


def get_progress(session_id: int) -> Optional[dict[str, Any]]:
    """Return in-memory progress for the specified session if active."""
    with _lock:
        if current_job["session_id"] == session_id:
            return {
                "session_id": current_job["session_id"],
                "done": current_job["done"],
                "total": current_job["total"],
                "item": current_job["item"],
                "cancel": current_job["cancel"],
            }
    return None


def worker_loop(stop: threading.Event) -> None:
    """Background worker loop executing submitted jobs sequentially."""
    logger.info("SiliconRoute job worker thread started.")
    while not stop.is_set():
        try:
            session_id, fn = _jobs.get(timeout=0.5)
        except queue.Empty:
            continue

        try:
            logger.info("Starting execution of session %d", session_id)
            fn(current_job)
            logger.info("Finished execution of session %d", session_id)
        except Exception as exc:
            logger.exception("Error executing session %d: %s", session_id, exc)
        finally:
            with _lock:
                current_job["session_id"] = None
                current_job["item"] = None
            _jobs.task_done()

    logger.info("SiliconRoute job worker thread stopped.")


def start_worker() -> None:
    """Start the single job worker thread if not already running."""
    global _worker_thread
    if _worker_thread is None or not _worker_thread.is_alive():
        _stop_event.clear()
        _worker_thread = threading.Thread(
            target=worker_loop,
            args=(_stop_event,),
            name="JobWorkerThread",
            daemon=True,
        )
        _worker_thread.start()


def stop_worker() -> None:
    """Signal the worker thread to stop and wait for termination."""
    _stop_event.set()
    if _worker_thread is not None and _worker_thread.is_alive():
        _worker_thread.join(timeout=2.0)
