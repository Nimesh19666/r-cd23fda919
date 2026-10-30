"""Serve the built React app from FastAPI (production only)."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles


def mount_frontend(app: FastAPI, directory: Path) -> bool:
    """Serve a Vite build and fall back to index.html for page routes.

    Returns False, mounting nothing, when the build is not there.
    """
    root = directory.resolve()
    index = root / "index.html"
    if not index.is_file():
        return False

    assets = root / "assets"
    if assets.is_dir():
        app.mount("/assets", StaticFiles(directory=assets), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    async def frontend(path: str) -> FileResponse:
        if path == "api" or path.startswith("api/"):
            raise HTTPException(status_code=404, detail="Not found")
        candidate = (root / path).resolve()
        # Only files inside the build folder are ever served.
        if candidate.is_file() and root in candidate.parents:
            return FileResponse(candidate)
        return FileResponse(index)

    return True
