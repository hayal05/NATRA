from flask_socketio import SocketIO

# threading async_mode keeps deployment simple (no eventlet/gevent needed).
socketio = SocketIO(async_mode="threading", cors_allowed_origins="*")


def broadcast(event, data):
    """Send a live-update event to every connected client."""
    socketio.emit(event, data)
