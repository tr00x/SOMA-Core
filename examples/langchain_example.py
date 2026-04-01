"""Example: SOMA proxy with LangChain tools.

Shows two approaches:
1. SomaLangChainCallback — callback-based monitoring (existing)
2. wrap_langchain_tools — proxy-based tool wrapping (new, preferred)

Requires: pip install langchain-core
This example works without LangChain installed (uses stubs).
"""

import soma


def main():
    engine = soma.quickstart(budget={"tokens": 50_000}, agents=["lc-agent"])

    # --- Proxy approach (new, preferred) ---
    proxy = soma.SOMAProxy(engine, "lc-agent")

    # Simulate LangChain-style tools (callables with names)
    def calculator(expression: str) -> str:
        return str(eval(expression))  # noqa: S307

    def web_search(query: str) -> str:
        return f"Top result for '{query}': example.com"

    # Wrap tools — SOMA monitors each call
    safe_calc = proxy.wrap_tool(calculator, "calculator")
    safe_search = proxy.wrap_tool(web_search, "web_search")

    # Use normally
    print(safe_calc("2 + 2"))
    print(safe_search("SOMA monitoring"))

    print(f"\nAgent: {proxy.action_count} actions, "
          f"pressure={proxy.pressure:.0%}, mode={proxy.mode.name}")

    # --- With wrap_langchain_tools (for real LangChain BaseTool objects) ---
    # from soma.sdk.langchain import wrap_langchain_tools
    # safe_tools = wrap_langchain_tools(engine, "lc-agent", tools)
    # agent = create_react_agent(llm, safe_tools, prompt)


if __name__ == "__main__":
    main()
