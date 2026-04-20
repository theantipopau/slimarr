"""
Real-time event emitter.
Call emit_event() from anywhere in the backend to push events to all connected UI clients.

Events reference:
    scan:started        {"total_movies": int}
    scan:progress       {"movie_id": int, "title": str, "current": int, "total": int}
    scan:completed      {"total_movies": int}
    search:started      {"movie_id": int, "title": str}
    search:results      {"movie_id": int, "title": str, "total_results": int,
                         "accepted_count": int, "best_savings_pct": float}
    download:started    {"movie_id": int, "title": str, "release": str}
    download:progress   {"movie_id": int, "download_id": int,
                         "progress": float, "speed": str, "eta": str}
    download:completed  {"movie_id": int, "title": str}
    download:failed     {"movie_id": int, "title": str, "error": str}
    replace:completed   {"movie_id": int, "title": str, "old_size": int,
                         "new_size": int, "savings_pct": float}
    queue:updated       {"queue_length": int, "current_movie_id": int | None}
    activity:new        {"id": int, "action": str, "movie_title": str, "detail": str}
    orchestrator:status {"running": bool, "current_movie_id": int | None}
"""
from backend.realtime.sio_instance import sio


async def emit_event(event: str, data: dict) -> None:
    """Emit a Socket.IO event to all connected clients."""
    await sio.emit(event, data)
