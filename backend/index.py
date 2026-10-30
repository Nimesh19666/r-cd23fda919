"""Vercel entry point: exposes the API as a module-level `app`.

Locally and in Docker the app is built by the factories in app/main.py instead.
"""

from app.main import create_app

app = create_app()
