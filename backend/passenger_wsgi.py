"""cPanel "Setup Python App" (Phusion Passenger) entry point.

Passenger speaks WSGI, FastAPI speaks ASGI: a2wsgi converts between them. The app starts no background threads and needs no
ASGI lifespan, so nothing is lost; reminders and email run from the cron job (app/jobs/run_once.py), not from this process.
In cPanel set:  Application startup file = passenger_wsgi.py   Application Entry point = application"""

import os
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)
os.chdir(BASE_DIR)  # relative paths (uploads/) resolve next to the app

from a2wsgi import ASGIMiddleware  # noqa: E402

from app.main import app  # noqa: E402

application = ASGIMiddleware(app, wait_time=5.0)
