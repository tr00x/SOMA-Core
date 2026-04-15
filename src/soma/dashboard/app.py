"""SOMA Dashboard — modular FastAPI application."""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse


def create_app() -> FastAPI:
    """Factory function that builds the SOMA Dashboard FastAPI app."""
    app = FastAPI(title="SOMA Dashboard", version="0.5.0")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:7777", "http://127.0.0.1:7777"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Import and include all route modules
    from soma.dashboard.routes import (
        agents,
        analytics,
        baselines,
        budget,
        config,
        export,
        findings,
        graph,
        guidance,
        learning,
        overview,
        quality,
        sessions,
        tools,
    )
    from soma.dashboard.ws import ws_router

    for router in [
        agents.router,
        sessions.router,
        overview.router,
        guidance.router,
        analytics.router,
        config.router,
        budget.router,
        export.router,
        quality.router,
        graph.router,
        learning.router,
        baselines.router,
        findings.router,
        tools.router,
        ws_router,
    ]:
        app.include_router(router)

    # SSE endpoint (from existing sse.py)
    from soma.dashboard.sse import sse_endpoint
    app.add_api_route("/api/stream", sse_endpoint, methods=["GET"])

    # Static files + SPA routing
    static_dir = Path(__file__).parent / "static"

    if static_dir.is_dir():
        # Favicon at root
        favicon = static_dir / "favicon.svg"
        if favicon.exists():
            @app.get("/favicon.svg", include_in_schema=False)
            async def serve_favicon():
                return FileResponse(str(favicon), media_type="image/svg+xml")

        # SPA catch-all: serve static files if they exist, else index.html
        @app.get("/{path:path}", include_in_schema=False, response_model=None)
        async def spa_catchall(path: str):
            # Try to serve static file first
            if path.startswith("static/"):
                file_path = static_dir / path.removeprefix("static/")
                if file_path.is_file():
                    # Guess content type
                    suffix = file_path.suffix.lower()
                    media_types = {
                        ".js": "application/javascript",
                        ".css": "text/css",
                        ".html": "text/html",
                        ".svg": "image/svg+xml",
                        ".json": "application/json",
                        ".png": "image/png",
                        ".ico": "image/x-icon",
                    }
                    return FileResponse(
                        str(file_path),
                        media_type=media_types.get(suffix, "application/octet-stream"),
                    )
            # SPA fallback — serve index.html
            index = static_dir / "index.html"
            if index.exists():
                return FileResponse(str(index), media_type="text/html")
            return {"error": "Frontend not built"}

    return app


# For `uvicorn soma.dashboard.app:app`
app = create_app()
