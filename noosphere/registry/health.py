"""Background health checker — periodically pings registered nodes."""

import asyncio
import logging
import threading
from datetime import datetime, timezone

import httpx

log = logging.getLogger(__name__)

_stop_event = threading.Event()
_thread: threading.Thread | None = None

# Check interval in seconds (default: 5 minutes)
CHECK_INTERVAL = 300
# Mark offline after this many consecutive failures
OFFLINE_THRESHOLD = 3
# Timeout per health check request
HEALTH_TIMEOUT = 10


def _run_health_loop(db_path: str):
    """Run the health check loop in a background thread."""
    import time
    from noosphere.registry.db import get_registry_conn

    # Wait a bit before the first check to let server start
    _stop_event.wait(30)

    while not _stop_event.is_set():
        try:
            conn = get_registry_conn(db_path)
            nodes = conn.execute("SELECT endpoint FROM nodes").fetchall()

            for node in nodes:
                if _stop_event.is_set():
                    break
                _check_node(conn, node["endpoint"])

        except Exception as e:
            log.error(f"Health check loop error: {e}")

        # Wait for the next interval or until stopped
        _stop_event.wait(CHECK_INTERVAL)


def _check_node(conn, endpoint: str):
    """Ping a single node's health endpoint and update its status."""
    now = datetime.now(timezone.utc).isoformat()

    try:
        resp = httpx.get(
            f"{endpoint}/api/v1/health",
            timeout=HEALTH_TIMEOUT,
            follow_redirects=True,
        )
        if resp.status_code == 200:
            conn.execute(
                """UPDATE nodes SET health_status='online', last_health_at=?,
                   consecutive_failures=0 WHERE endpoint=?""",
                (now, endpoint),
            )
            conn.commit()
            log.debug(f"Health OK: {endpoint}")
            return
    except (httpx.ConnectError, httpx.TimeoutException):
        pass
    except Exception as e:
        log.debug(f"Health check error for {endpoint}: {e}")

    # Failed — increment failures
    row = conn.execute(
        "SELECT consecutive_failures FROM nodes WHERE endpoint=?", (endpoint,)
    ).fetchone()
    if not row:
        return

    failures = (row["consecutive_failures"] or 0) + 1
    status = "offline" if failures >= OFFLINE_THRESHOLD else "degraded"

    conn.execute(
        """UPDATE nodes SET health_status=?, last_health_at=?,
           consecutive_failures=? WHERE endpoint=?""",
        (status, now, failures, endpoint),
    )
    conn.commit()
    log.info(f"Health {status}: {endpoint} (failures: {failures})")


def start_health_checker(db_path: str) -> threading.Thread:
    """Start the background health checker thread."""
    global _thread
    _stop_event.clear()
    _thread = threading.Thread(target=_run_health_loop, args=(db_path,), daemon=True)
    _thread.start()
    log.info("Background health checker started")
    return _thread


def stop_health_checker():
    """Stop the background health checker."""
    _stop_event.set()
    if _thread and _thread.is_alive():
        _thread.join(timeout=5)
    log.info("Background health checker stopped")
