"""Example: SOMA proxy with a custom agent — no framework needed.

Shows wrap_tool, spawn_subagent, and pressure propagation.
"""

import soma


def search(query: str) -> str:
    """Simulate a search tool."""
    return f"Found 3 results for '{query}'"


def write_file(path: str, content: str) -> str:
    """Simulate a file write tool."""
    return f"Wrote {len(content)} bytes to {path}"


def bash(command: str) -> str:
    """Simulate a bash command."""
    if "rm -rf" in command:
        raise RuntimeError("Permission denied")
    return f"$ {command}\nOK"


def main():
    # 1. Setup engine
    engine = soma.quickstart(budget={"tokens": 50_000}, agents=["orchestrator"])
    proxy = soma.SOMAProxy(engine, "orchestrator")

    # 2. Wrap tools
    safe_search = proxy.wrap_tool(search, "search")
    safe_write = proxy.wrap_tool(write_file, "write")
    safe_bash = proxy.wrap_tool(bash, "bash")

    # 3. Use tools normally — SOMA monitors transparently
    print(safe_search("python monitoring"))
    print(safe_write("/tmp/output.txt", "hello world"))
    print(safe_bash("ls -la"))

    print(f"\nOrchestrator: {proxy.action_count} actions, "
          f"pressure={proxy.pressure:.0%}, mode={proxy.mode.name}")

    # 4. Spawn a subagent
    child = proxy.spawn_subagent("researcher")
    child_search = child.wrap_tool(search, "search")

    for i in range(5):
        child_search(f"topic {i}")

    print(f"Researcher: {child.action_count} actions, "
          f"pressure={child.pressure:.0%}")

    # 5. Simulate subagent errors
    child_bash = child.wrap_tool(bash, "bash")
    for _ in range(3):
        try:
            child_bash("rm -rf /")
        except RuntimeError:
            pass

    print(f"After errors — Researcher: pressure={child.pressure:.0%}")

    # 6. Check graph propagation
    parent_snap = engine.get_snapshot("orchestrator")
    child_snap = engine.get_snapshot("researcher")
    print(f"Orchestrator effective pressure: {parent_snap['pressure']:.2%}")
    print(f"Researcher effective pressure: {child_snap['pressure']:.2%}")


if __name__ == "__main__":
    main()
