"""Quick SOMA monitoring session for demo recording."""
import soma

engine = soma.quickstart()
engine.register_agent("demo")

for _ in range(5):
    engine.record_action("demo", soma.Action(
        tool_name="Bash", output_text="ok", token_count=100
    ))

v = engine.get_vitals("demo")
p = engine.get_pressure("demo")
m = engine.get_mode("demo")

print(f"Pressure: {p:.0%}")
print(f"Mode:     {m.name}")
print(f"Actions:  {v.action_count}")
