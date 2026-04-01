"""Example: SOMA proxy with AutoGen-style agents.

Shows how SOMAProxy.wrap_agent() intercepts AutoGen's generate_reply
and function_map patterns.

Requires: pip install pyautogen (for real usage)
This example works without AutoGen installed (uses stubs).
"""

import soma


class FakeAutoGenAgent:
    """Simulates AutoGen ConversableAgent interface."""
    def __init__(self, name: str):
        self.name = name
        self.function_map = {
            "search": lambda q: f"Found: {q}",
            "calculate": lambda expr: str(eval(expr)),  # noqa: S307
        }

    def generate_reply(self, messages=None, sender=None, **kwargs):
        if messages:
            last = messages[-1].get("content", "")
            return f"[{self.name}] Reply to: {last[:50]}"
        return f"[{self.name}] No messages"


def main():
    engine = soma.quickstart(budget={"tokens": 50_000})

    assistant = FakeAutoGenAgent("assistant")
    proxy = soma.SOMAProxy(engine, "assistant")
    proxy.wrap_agent(assistant)

    # generate_reply is now monitored
    reply = assistant.generate_reply(
        messages=[{"content": "What is the meaning of life?"}]
    )
    print(reply)

    # function_map tools are also monitored
    print(assistant.function_map["search"]("SOMA proxy"))
    print(assistant.function_map["calculate"]("42 * 2"))

    print(f"\nAssistant: {proxy.action_count} actions, "
          f"pressure={proxy.pressure:.0%}")

    # --- With wrap_autogen_agent helper ---
    # from soma.sdk.autogen import wrap_autogen_agent
    # wrap_autogen_agent(engine, agent)


if __name__ == "__main__":
    main()
