"""SOMA Dashboard — `soma` CLI entry point."""


def run() -> None:
    from soma.dashboard.app import SOMADashboard
    from soma.engine import SOMAEngine
    engine = SOMAEngine(budget={"tokens": 100_000, "cost_usd": 1.0})
    app = SOMADashboard(engine)
    app.run()
