"""Example: SOMA proxy with CrewAI-style agents.

Shows how SOMAProxy.wrap_agent() intercepts CrewAI's execute_task pattern.

Requires: pip install crewai (for real usage)
This example works without CrewAI installed (uses stubs).
"""

import soma


class FakeCrewAgent:
    """Simulates CrewAI Agent interface."""
    def __init__(self, role: str):
        self.role = role

    def execute_task(self, task):
        return f"[{self.role}] completed: {task}"


class FakeCrewTask:
    def __init__(self, description: str):
        self.description = description

    def __str__(self):
        return self.description


def main():
    engine = soma.quickstart(budget={"tokens": 50_000})

    # Create agents
    researcher = FakeCrewAgent("researcher")
    writer = FakeCrewAgent("writer")

    # Wrap with SOMA — each agent gets its own proxy
    proxy_r = soma.SOMAProxy(engine, "researcher")
    proxy_r.wrap_agent(researcher)

    proxy_w = soma.SOMAProxy(engine, "writer")
    proxy_w.wrap_agent(writer)

    # Wire researcher → writer in graph (writer depends on researcher)
    engine._graph.add_edge("researcher", "writer", trust=0.9)

    # Execute tasks
    task1 = FakeCrewTask("Research AI monitoring tools")
    task2 = FakeCrewTask("Write blog post about findings")

    print(researcher.execute_task(task1))
    print(writer.execute_task(task2))

    print(f"\nResearcher: pressure={proxy_r.pressure:.0%}")
    print(f"Writer: pressure={proxy_w.pressure:.0%}")

    # --- With wrap_crewai_agent helper ---
    # from soma.sdk.crewai import wrap_crewai_agent
    # wrap_crewai_agent(engine, agent)


if __name__ == "__main__":
    main()
