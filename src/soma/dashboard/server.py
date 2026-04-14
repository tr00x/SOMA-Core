"""SOMA Dashboard server entry point."""

from __future__ import annotations


def main() -> None:
    import uvicorn

    uvicorn.run(
        "soma.dashboard.app:app",
        host="127.0.0.1",
        port=7777,
    )


if __name__ == "__main__":
    main()
