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
Type "python3 demo_session.py"
Enter
Sleep 3s

# --- Show final status ---
Type "soma status"
Enter
Sleep 3s
