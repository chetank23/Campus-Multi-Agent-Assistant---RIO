"""
backend/realtime/timetable_sync.py
----------------------------------
Authenticated WebSocket room manager and optional Redis Pub/Sub fan-out
for real-time collaborative timetable editing and publication sync.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from collections import defaultdict
from typing import Any, Dict, Optional, Set

import jwt
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from backend.config import ALGORITHM, SECRET_KEY
from backend.database import SessionLocal
from backend.models.identity import User
from backend.utils.datetime_utils import utc_now

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Timetable Realtime"])


class TimetableSyncManager:
    """Manages WebSocket rooms per TimetableVersion with optional Redis Pub/Sub."""

    def __init__(self) -> None:
        self._rooms: Dict[int, Set[WebSocket]] = defaultdict(set)
        self._lock = asyncio.Lock()
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    def set_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    async def connect(self, version_id: int, websocket: WebSocket) -> None:
        self._loop = asyncio.get_running_loop()
        await websocket.accept()
        async with self._lock:
            self._rooms[version_id].add(websocket)

    async def disconnect(self, version_id: int, websocket: WebSocket) -> None:
        async with self._lock:
            if version_id in self._rooms:
                self._rooms[version_id].discard(websocket)
                if not self._rooms[version_id]:
                    del self._rooms[version_id]

    async def broadcast_local(self, version_id: int, payload: Dict[str, Any]) -> None:
        async with self._lock:
            targets = list(self._rooms.get(version_id, ()))
        if not targets:
            return
        message = json.dumps(payload, default=str)
        dead: list[WebSocket] = []
        for ws in targets:
            try:
                await ws.send_text(message)
            except Exception:
                dead.append(ws)
        if dead:
            async with self._lock:
                for ws in dead:
                    self._rooms.get(version_id, set()).discard(ws)

    async def publish_event(self, version_id: int, payload: Dict[str, Any]) -> None:
        await self.broadcast_local(version_id, payload)
        redis_url = os.getenv("REDIS_URL")
        if not redis_url:
            return
        try:
            import redis.asyncio as aioredis  # type: ignore

            client = aioredis.from_url(redis_url, decode_responses=True)
            try:
                await client.publish(f"timetable:version:{version_id}", json.dumps(payload, default=str))
            finally:
                await client.aclose()
        except Exception as exc:
            logger.debug("Redis Pub/Sub unavailable, using local WebSocket broadcast: %s", exc)


sync_manager = TimetableSyncManager()


def broadcast_version_update(
    version_id: int,
    revision: int,
    status_value: str,
    actor_name: str,
    event_type: str = "VERSION_UPDATED",
    extra: Optional[Dict[str, Any]] = None,
) -> None:
    """
    Thread-safe helper callable from synchronous FastAPI routes after DB commit.
    """
    payload: Dict[str, Any] = {
        "type": event_type,
        "version_id": version_id,
        "revision": revision,
        "status": status_value,
        "actor_name": actor_name,
        "timestamp": utc_now().isoformat(),
    }
    if extra:
        payload.update(extra)

    loop = sync_manager._loop
    if loop and loop.is_running():
        try:
            asyncio.run_coroutine_threadsafe(sync_manager.publish_event(version_id, payload), loop)
            return
        except Exception as exc:
            logger.debug("Failed scheduling WS broadcast on running loop: %s", exc)

    try:
        running = asyncio.get_running_loop()
        running.create_task(sync_manager.publish_event(version_id, payload))
    except RuntimeError:
        # No active event loop (e.g. unit test calling service directly)
        pass


def _authenticate_websocket_token(token: Optional[str]) -> Optional[User]:
    if not token:
        return None
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        if payload.get("token_type") != "access":
            return None
        user_id_str = payload.get("sub")
        if user_id_str is None:
            return None
        user_id = int(user_id_str)
    except (jwt.PyJWTError, ValueError, TypeError):
        return None

    db = SessionLocal()
    try:
        user = db.query(User).filter(User.id == user_id).first()
        if not user or not user.is_active:
            return None
        if user.role not in ("ADMIN", "SUPER_ADMIN"):
            return None
        return user
    finally:
        db.close()


@router.websocket("/ws/timetable/versions/{version_id}")
async def timetable_version_ws(websocket: WebSocket, version_id: int) -> None:
    """
    Authenticated WebSocket endpoint for real-time timetable version updates.
    Clients pass JWT via `?token=<access_token>` or `Authorization: Bearer <token>`.
    """
    token = websocket.query_params.get("token")
    if not token:
        auth_header = websocket.headers.get("authorization", "")
        if auth_header.lower().startswith("bearer "):
            token = auth_header.split(" ", 1)[1].strip()

    user = _authenticate_websocket_token(token)
    if not user:
        await websocket.close(code=4401)
        return

    await sync_manager.connect(version_id, websocket)
    try:
        await websocket.send_text(
            json.dumps(
                {
                    "type": "CONNECTED",
                    "version_id": version_id,
                    "user": user.name,
                    "timestamp": utc_now().isoformat(),
                }
            )
        )
        while True:
            raw = await websocket.receive_text()
            if raw.strip().lower() == "ping":
                await websocket.send_text(json.dumps({"type": "PONG", "version_id": version_id}))
    except WebSocketDisconnect:
        await sync_manager.disconnect(version_id, websocket)
    except Exception:
        await sync_manager.disconnect(version_id, websocket)
