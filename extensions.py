from flask_socketio import SocketIO

# gevent async_mode: eventlet has known incompatibilities with Python 3.12's
# logging internals (gunicorn's master process creates an RLock via
# `import logging` before any worker can monkey-patch, which eventlet can't
# retroactively "green" — causes RLock/context errors under load). gevent
# handles this cleanly and is Flask-SocketIO's other first-class async mode.
# Start command must be:
#   gunicorn -k geventwebsocket.gunicorn.workers.GeventWebSocketWorker -w 1 app:app
socketio = SocketIO(async_mode="gevent", cors_allowed_origins="*")


def broadcast(event, data):
    """Send a live-update event to every connected client."""
    socketio.emit(event, data)
