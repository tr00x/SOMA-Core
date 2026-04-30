"""SOMA Dashboard — modular FastAPI application."""
from __future__ import annotations

import hmac
import os
import sys
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse


def _token_auth_middleware_factory(token: str):
    """Build a middleware that rejects requests without
    ``Authorization: Bearer <token>`` or a ``?token=<token>`` query
    param. Static assets (``/static/*``, ``/favicon.svg``) and health
    probes (``/healthz``) bypass auth.
    """
    async def middleware(request: Request, call_next):
        path = request.url.path
        if (
            path == "/healthz"
            or path.startswith("/static/")
            or path == "/favicon.svg"
        ):
            return await call_next(request)
        auth = request.headers.get("authorization", "")
        provided: str | None = None
        if auth.lower().startswith("bearer "):
            provided = auth[7:].strip()
        elif "token" in request.query_params:
            provided = request.query_params["token"]
        if not hmac.compare_digest(provided or "", token):
            return JSONResponse(
                status_code=401,
                content={"detail": "missing or invalid SOMA_DASHBOARD_TOKEN"},
            )
        return await call_next(request)

    return middleware


def create_app() -> FastAPI:
    """Factory function that builds the SOMA Dashboard FastAPI app.

    Set ``SOMA_DASHBOARD_TOKEN`` to require ``Authorization: Bearer
    <token>`` (or ``?token=<token>``) on every endpoint. Without it
    the dashboard remains open — fine on a localhost-bound socket
    but a footgun if the user reverse-proxies it. Default off so
    existing setups keep working.
    """
    app = FastAPI(title="SOMA Dashboard", version="0.5.0")

    token = os.environ.get("SOMA_DASHBOARD_TOKEN", "").strip()
    if token:
        app.middleware("http")(_token_auth_middleware_factory(token))
        print("[SOMA] dashboard auth: enabled (SOMA_DASHBOARD_TOKEN)", file=sys.stderr)
    else:
        print("[SOMA] dashboard auth: disabled (open) — set SOMA_DASHBOARD_TOKEN to require a bearer token", file=sys.stderr)

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
        roi,
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
        roi.router,
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
