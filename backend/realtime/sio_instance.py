"""
Socket.IO server instance — defined here to avoid circular imports.
Import `sio` from this module everywhere you need Socket.IO.
"""
import socketio

sio: socketio.AsyncServer = socketio.AsyncServer(
    async_mode="asgi",
    cors_allowed_origins="*",
    logger=False,
    engineio_logger=False,
)
