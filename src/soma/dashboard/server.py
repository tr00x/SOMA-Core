"""SOMA Dashboard server entry point."""

from __future__ import annotations


def main() -> None:
    import uvicorn

    uvicorn.run(
        "soma.dashboard.app:app",
        host="0.0.0.0",
        port=7777,
        reload=True,
    )


if __name__ == "__main__":
    main()
