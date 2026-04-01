# SOMA Demo — Real behavioral monitoring of a degrading AI agent
# Record with: vhs demo.tape
# Requires: https://github.com/charmbracelet/vhs

Output demo.gif
Set FontSize 14
Set Width 1200
Set Height 700
Set Theme "Catppuccin Mocha"
Set Padding 20
Set TypingSpeed 40ms

# --- Show what SOMA is ---
Type "# SOMA — real-time behavioral monitoring for AI agents"
Enter
Sleep 1.5s

# --- Run the real demo session ---
Type "uv run python3 demo_session.py"
Enter
Sleep 12s
