import os
from app import create_app, socketio

# Create the Flask application using the factory
app = create_app()

if __name__ == "__main__":
    """
    Development entry point.

    In production (Render), gunicorn starts the app using the command:
        gunicorn --worker-class geventwebsocket.gunicorn.workers.GeventWebSocketWorker -w 1 run:app

    Flask-SocketIO requires exactly 1 worker when using gevent/eventlet,
    because WebSocket connections are long-lived and stateful.
    Multiple workers would cause socket rooms to be isolated per-process.
    """
    port = int(os.environ.get("PORT", 5000))

    socketio.run(
        app,
        host="0.0.0.0",
        port=port,
        debug=app.config.get("DEBUG", False),
    )