"""WebSocket endpoint for real-time authenticated job progress streaming."""

from __future__ import annotations

import asyncio
import json
import time
from typing import Optional

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect, status
import redis.asyncio as aioredis

from app.core.config import settings
from app.core.logging import get_logger
from app.core.security import decode_access_token
from app.db.session import SessionLocal
from app.models.analysis_run import AnalysisRun
from app.models.project import Project
from app.models.repository import Repository
from app.models.user import User

logger = get_logger("ws")

router = APIRouter(tags=["websocket"])


def _verify_job_ownership(user_id: str, job_id: str) -> bool:
    """Verify that user_id owns the project/repository associated with job_id."""
    with SessionLocal() as db:
        user = db.query(User).filter(User.id == user_id).first()
        if not user or not user.is_active:
            return False

        if user.role == "admin":
            return True

        # Check AnalysisRun ownership
        run = db.query(AnalysisRun).filter(AnalysisRun.id == job_id).first()
        if run:
            if run.requested_by == user.id:
                return True
            # Also check if project owner matches
            repo = (
                db.query(Repository)
                .join(Project, Repository.project_id == Project.id)
                .filter(Repository.id == run.repository_id, Project.owner_id == user.id)
                .first()
            )
            return repo is not None

        return False


def _get_latest_job_state(job_id: str) -> dict:
    """Retrieve the latest known job state from DB to guarantee late subscribers are never blank."""
    with SessionLocal() as db:
        run = db.query(AnalysisRun).filter(AnalysisRun.id == job_id).first()
        if run:
            return {
                "stage": run.stage,
                "progress": run.progress,
                "message": run.error or f"Stage: {run.stage} ({run.progress}%)",
                "status": run.status,
            }
    return {
        "stage": "queued",
        "progress": 0,
        "message": "Initializing...",
        "status": "queued",
    }


@router.websocket("/ws/jobs/{job_id}")
async def websocket_job_progress(
    websocket: WebSocket,
    job_id: str,
    token: Optional[str] = Query(None),
):
    """Authenticated WebSocket endpoint streaming live progress for an analysis run.
    
    - Verifies JWT and ownership before accepting
    - Sends latest saved state immediately (late subscriber resilience)
    - Subscribes to Redis channel progress:{job_id}
    - Emits heartbeats every 15 seconds
    """
    if not token:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    token_data = decode_access_token(token)
    if not token_data or not token_data.user_id:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    user_id = token_data.user_id
    if not _verify_job_ownership(user_id, job_id):
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    await websocket.accept()

    # Send latest known state first so late subscriber is never blank
    initial_state = _get_latest_job_state(job_id)
    await websocket.send_json(initial_state)

    # If job is already completed or failed, keep socket alive briefly then finish
    if initial_state.get("status") in ("completed", "failed"):
        try:
            # Wait for disconnect
            while True:
                await asyncio.sleep(15)
                await websocket.send_json({"type": "heartbeat", "timestamp": time.time()})
        except WebSocketDisconnect:
            pass
        return

    redis_client: Optional[aioredis.Redis] = None
    pubsub: Optional[aioredis.client.PubSub] = None

    try:
        redis_client = aioredis.from_url(
            settings.REDIS_URL,
            socket_timeout=5.0,
            decode_responses=True,
        )
        pubsub = redis_client.pubsub()
        channel = f"progress:{job_id}"
        await pubsub.subscribe(channel)

        last_heartbeat = time.time()

        while True:
            # Poll for Redis pubsub message with short timeout
            try:
                msg = await asyncio.wait_for(
                    pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0),
                    timeout=1.5,
                )
                if msg and msg.get("type") == "message":
                    raw_data = msg.get("data", "")
                    if isinstance(raw_data, str) and raw_data.strip():
                        payload = json.loads(raw_data)
                        client_msg = {
                            "stage": payload.get("stage", "running"),
                            "progress": payload.get("progress", 0),
                            "message": payload.get("message", ""),
                            "status": payload.get("status", "running"),
                        }
                        await websocket.send_json(client_msg)

                        # If reached terminal state, socket can close or stay open
                        if client_msg.get("status") in ("completed", "failed"):
                            pass

            except (asyncio.TimeoutError, TimeoutError):
                pass

            # Heartbeat every 15 seconds
            now = time.time()
            if now - last_heartbeat >= 15.0:
                await websocket.send_json({"type": "heartbeat", "timestamp": now})
                last_heartbeat = now

    except WebSocketDisconnect:
        logger.debug(f"WebSocket client disconnected from job {job_id}")
    except Exception as e:
        logger.warning(f"Error in WebSocket progress relay for job {job_id}: {e}")
    finally:
        if pubsub is not None:
            try:
                await pubsub.unsubscribe()
                await pubsub.close()
            except Exception:
                pass
        if redis_client is not None:
            try:
                await redis_client.close()
            except Exception:
                pass
