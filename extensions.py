from flask_socketio import SocketIO

# gevent async_mode — see app.py for why the Turso client is created before
# gevent.monkey.patch_all() runs.
# Start command must be:
#   gunicorn -k geventwebsocket.gunicorn.workers.GeventWebSocketWorker -w 1 app:app
socketio = SocketIO(async_mode="gevent", cors_allowed_origins="*")


def broadcast(event, data):
    """Send a live-update event to every connected client."""
    socketio.emit(event, data)
