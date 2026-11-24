"""
backend/celery_app.py
----------------------
Celery distributed task queue application with Redis broker and resilient local fallback.

Configuration:
- Broker: Redis (default: redis://localhost:6379/0 via CELERY_BROKER_URL)
- Result Backend: Redis (default: redis://localhost:6379/0 via CELERY_RESULT_BACKEND)
- Local Development / Test Fallback:
  When CELERY_TASK_ALWAYS_EAGER=true or when Redis is absent/unreachable, tasks execute
  synchronously in eager mode with in-memory result tracking.
- Worker Execution:
  On Windows, Celery worker must use the solo pool:
  .\\venv\\Scripts\\celery.exe -A backend.celery_app.celery_app worker -P solo -l info
"""

import os
import logging
from typing import Any, Callable, Dict, Optional

logger = logging.getLogger("campus_ai.celery")

CELERY_BROKER_URL: str = os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0")
CELERY_RESULT_BACKEND: str = os.getenv("CELERY_RESULT_BACKEND", "redis://localhost:6379/0")


def is_redis_available(url: str = CELERY_BROKER_URL, timeout: float = 0.5) -> bool:
    """
    Check if the Redis broker is reachable.
    Uses a fast socket ping with 0.5s timeout.
    """
    try:
        import redis
        client = redis.from_url(url, socket_connect_timeout=timeout, socket_timeout=timeout)
        return bool(client.ping())
    except Exception:
        return False


# Determine execution mode:
# If CELERY_TASK_ALWAYS_EAGER is explicitly set, honor that setting.
# Otherwise, auto-detect: if Redis is reachable, run async worker mode; if Redis is unreachable, fallback to eager dev mode.
_eager_env = os.getenv("CELERY_TASK_ALWAYS_EAGER", "").strip().lower()
if _eager_env in ("true", "1", "yes"):
    CELERY_TASK_ALWAYS_EAGER = True
elif _eager_env in ("false", "0", "no"):
    CELERY_TASK_ALWAYS_EAGER = False
else:
    # Auto-detect reachability
    _redis_up = is_redis_available(CELERY_BROKER_URL)
    CELERY_TASK_ALWAYS_EAGER = not _redis_up

try:
    from celery import Celery
    from celery.result import AsyncResult

    celery_app = Celery(
        "campus_ai",
        broker=CELERY_BROKER_URL,
        backend=CELERY_RESULT_BACKEND,
        include=[
            "backend.tasks.curriculum_tasks",
            "backend.tasks.timetable_tasks",
        ],
    )

    if CELERY_TASK_ALWAYS_EAGER:
        logger.info(
            "Configuring Celery in local eager fallback mode (always_eager=True, result_backend=cache+memory://)"
        )
        celery_app.conf.update(
            task_always_eager=True,
            task_eager_propagates=True,
            task_store_eager_result=True,
            result_backend="cache+memory://",
            result_extended=True,
        )
    else:
        logger.info(
            "Configuring Celery with Redis broker: %s and backend: %s",
            CELERY_BROKER_URL,
            CELERY_RESULT_BACKEND,
        )
        celery_app.conf.update(
            task_always_eager=False,
            task_eager_propagates=False,
            result_backend=CELERY_RESULT_BACKEND,
            result_extended=True,
            broker_connection_retry_on_startup=True,
        )

except ImportError:
    logger.warning("Celery package not installed; falling back to in-memory synchronous wrapper.")
    CELERY_TASK_ALWAYS_EAGER = True

    class EagerResult:
        def __init__(self, result: Any, task_id: str = "local-eager-task"):
            self.result = result
            self.id = task_id
            self.status = "SUCCESS"

        def get(self, *args: Any, **kwargs: Any) -> Any:
            return self.result

        def ready(self) -> bool:
            return True

        def successful(self) -> bool:
            return True

    class EagerTask:
        def __init__(self, func: Callable):
            self.func = func
            self.__name__ = getattr(func, "__name__", "task")
            self.__doc__ = getattr(func, "__doc__", "")

        def __call__(self, *args: Any, **kwargs: Any) -> Any:
            return self.func(*args, **kwargs)

        def delay(self, *args: Any, **kwargs: Any) -> EagerResult:
            return self.apply_async(args=args, kwargs=kwargs)

        def apply_async(self, args: Any = None, kwargs: Any = None, **_: Any) -> EagerResult:
            import uuid
            args = args or ()
            kwargs = kwargs or {}
            res = self.func(*args, **kwargs)
            return EagerResult(res, task_id=str(uuid.uuid4()))

    class EagerCeleryApp:
        def __init__(self):
            self.conf = type("Conf", (), {"task_always_eager": True})()

        def task(self, *args: Any, **kwargs: Any):
            if args and callable(args[0]):
                return EagerTask(args[0])

            def decorator(func: Callable):
                return EagerTask(func)

            return decorator

        def AsyncResult(self, task_id: str):
            return EagerResult(None, task_id=task_id)

    celery_app = EagerCeleryApp()


def get_task_status(task_id: str) -> Dict[str, Any]:
    """
    Retrieve task status, progress metadata, result payload, or error detail.
    Maps Celery task states to standardized system states:
    - PENDING -> QUEUED
    - STARTED / PROGRESS / RETRY -> PROCESSING
    - SUCCESS -> SUCCESS
    - FAILURE / REVOKED -> FAILURE
    """
    try:
        from celery.result import AsyncResult
        res = AsyncResult(task_id, app=celery_app)
        state = res.state

        if state == "SUCCESS":
            return {
                "task_id": task_id,
                "status": "SUCCESS",
                "progress": 100,
                "meta": res.info if isinstance(res.info, dict) else {},
                "result": res.result,
                "error": None,
            }
        elif state == "FAILURE":
            return {
                "task_id": task_id,
                "status": "FAILURE",
                "progress": 100,
                "meta": res.info if isinstance(res.info, dict) else {},
                "result": None,
                "error": str(res.result) if res.result is not None else "Task execution failed.",
            }
        elif state in ("STARTED", "PROGRESS", "RETRY"):
            meta = res.info if isinstance(res.info, dict) else {}
            progress = meta.get("progress", 50) if isinstance(meta, dict) else 50
            return {
                "task_id": task_id,
                "status": "PROCESSING",
                "progress": progress,
                "meta": meta,
                "result": None,
                "error": None,
            }
        else:  # PENDING or unknown
            return {
                "task_id": task_id,
                "status": "QUEUED",
                "progress": 0,
                "meta": {},
                "result": None,
                "error": None,
            }
    except Exception as exc:
        logger.warning("Could not query AsyncResult for task %s: %s", task_id, exc)
        return {
            "task_id": task_id,
            "status": "QUEUED",
            "progress": 0,
            "meta": {"warning": str(exc)},
            "result": None,
            "error": None,
        }
