from flask_socketio import SocketIO

# eventlet async_mode: required for gunicorn deployments so WebSocket
# connections don't tie up gthread/sync worker threads indefinitely (which
# causes gunicorn's arbiter to kill the worker on heartbeat timeout and
# restart it — seen as the port repeatedly dropping in production logs).
# Start command must be: gunicorn -k eventlet -w 1 app:app
socketio = SocketIO(async_mode="eventlet", cors_allowed_origins="*")


def broadcast(event, data):
    """Send a live-update event to every connected client."""
    socketio.emit(event, data)
