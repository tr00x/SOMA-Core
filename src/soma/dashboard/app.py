"""SOMA Dashboard — modular FastAPI application."""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles


def create_app() -> FastAPI:
    """Factory function that builds the SOMA Dashboard FastAPI app."""
    app = FastAPI(title="SOMA Dashboard", version="0.5.0")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
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

    # Static files
    static_dir = Path(__file__).parent / "static"
    if static_dir.is_dir():
        app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

        # SPA catch-all -- serve index.html for non-API paths
        @app.get("/{path:path}", response_model=None)
        async def spa_catchall(path: str):
            index = static_dir / "index.html"
            if index.exists():
                return FileResponse(str(index))
            return {"error": "Frontend not built"}

    return app


# For `uvicorn soma.dashboard.app:app`
app = create_app()
