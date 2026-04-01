# SOMA Demo — Behavioral Monitoring for AI Agents
# Record with: vhs demo.tape
# Requires: https://github.com/charmbracelet/vhs

Output demo.gif
Set FontSize 14
Set Width 1200
Set Height 600
Set Theme "Catppuccin Mocha"
Set Padding 20
Set TypingSpeed 50ms

# --- Installation ---
Type "pip install soma-ai"
Enter
Sleep 2s

# --- Setup for Claude Code ---
Type "soma setup-claude"
Enter
Sleep 2s

# --- Check monitoring status ---
Type "soma status"
Enter
Sleep 2s

# --- Run a quick monitoring session ---
Type@50ms "python3 -c \""
Type@30ms "import soma; "
Type@30ms "engine = soma.quickstart(); "
Type@30ms "engine.register_agent('demo'); "
Type@30ms "[engine.record_action('demo', soma.Action("
Type@30ms "tool_name='Bash', output_text='ok', token_count=100"
Type@30ms ")) for _ in range(5)]; "
Type@30ms "v = engine.get_vitals('demo'); "
Type@30ms "print(f'Pressure: {engine.get_pressure(\"demo\"):.0%}'); "
Type@30ms "print(f'Mode: {engine.get_mode(\"demo\").name}'); "
Type@30ms "print(f'Actions: {v.action_count}')"
Type@30ms "\""
Enter
Sleep 3s

# --- Show final status ---
Type "soma status"
Enter
Sleep 3s
