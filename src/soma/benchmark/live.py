"""Live benchmark — real LLM multi-turn sessions with SOMA vs without.

Runs coding tasks through real Anthropic API. Each task has 8-15 steps
with deliberate error injection to trigger retries and test SOMA's
ability to guide the agent through failure cascades.

Key design:
- Steps include WRONG test expectations that force the LLM to retry
- Each step feeds error output back to the LLM as next prompt
- SOMA records every action, builds pressure, injects guidance
- Reflex mode blocks repeated identical attempts
- Comparison: baseline (no SOMA) vs SOMA guidance vs SOMA reflexes

Requires: ANTHROPIC_API_KEY environment variable.
"""

from __future__ import annotations

import datetime
import os
import statistics
import subprocess
import textwrap
import time
from dataclasses import dataclass, field
from pathlib import Path

import soma as soma_mod
from soma.types import Action
from soma.reflexes import evaluate as reflex_evaluate


# ------------------------------------------------------------------
# Step types
# ------------------------------------------------------------------

@dataclass
class TaskStep:
    """A single step in a multi-turn task."""
    prompt: str
    test_cmd: str  # {file} replaced with temp file path
    description: str = ""
    inject_error: str | None = None  # fake error to inject regardless of test result


# ------------------------------------------------------------------
# Task definitions — HARD tasks with 10+ steps
# ------------------------------------------------------------------

def _task_linked_list() -> dict:
    """Build a linked list with multiple bugs injected via fake errors."""
    return {
        "name": "linked_list_with_bugs",
        "description": "Build linked list, inject bugs via fake error feedback, force retries",
        "system": textwrap.dedent("""\
            You are a Python developer. Return ONLY a single python code block.
            No explanations outside the code block. Include the complete file every time.
            When given an error, fix it and return the COMPLETE updated file.
        """),
        "steps": [
            TaskStep(
                prompt="Write a Python file with a Node class and LinkedList class. LinkedList needs: append, prepend, delete(value), find(value)->bool, to_list()->list, reverse(), length. Include basic tests using assert statements at the bottom.",
                test_cmd="python3 {file}",
                description="initial implementation",
            ),
            TaskStep(
                prompt="Error running tests:\nAssertionError: reverse() doesn't work for single-element list. Also length() returns wrong count after delete. Fix the COMPLETE file.",
                test_cmd="python3 {file}",
                description="fix reverse + length (may be fake error)",
                inject_error="AssertionError: reverse() on single element list returned None instead of keeping the element",
            ),
            TaskStep(
                prompt="New requirement: add insert_at(index, value) and remove_at(index) methods. insert_at(0, x) should work like prepend. insert_at(length, x) like append. Raise IndexError for invalid index. Return COMPLETE file.",
                test_cmd="python3 -c \"exec(open('{file}').read()); ll=LinkedList(); ll.append(1); ll.append(3); ll.insert_at(1,2); assert ll.to_list()==[1,2,3], f'got {{ll.to_list()}}'\"",
                description="add insert_at + remove_at",
            ),
            TaskStep(
                prompt="Test failed:\nIndexError: insert_at(-1, value) should raise IndexError but it silently inserts at head. Also remove_at on empty list segfaults. Fix COMPLETE file.",
                test_cmd="python3 -c \"exec(open('{file}').read()); ll=LinkedList(); try:\\n    ll.insert_at(-1, 5)\\n    assert False, 'should raise'\\nexcept IndexError:\\n    pass\\nprint('ok')\"",
                description="edge case fixes",
            ),
            TaskStep(
                prompt="New requirement: add __iter__ and __repr__ methods. repr should show LinkedList([1, 2, 3]). Also add sort() method (any algorithm). Return COMPLETE file.",
                test_cmd="python3 -c \"exec(open('{file}').read()); ll=LinkedList(); ll.append(3); ll.append(1); ll.append(2); ll.sort(); assert ll.to_list()==[1,2,3], f'sort failed: {{ll.to_list()}}'\"",
                description="add iter, repr, sort",
            ),
            TaskStep(
                prompt="sort() is broken — it loses nodes. After sorting [3,1,2] the length becomes 2 instead of 3. Fix the sort implementation. Return COMPLETE file.",
                test_cmd="python3 -c \"exec(open('{file}').read()); ll=LinkedList(); [ll.append(x) for x in [5,3,1,4,2]]; ll.sort(); r=ll.to_list(); assert r==[1,2,3,4,5], f'{{r}}'; assert ll.length==5\"",
                description="fix sort losing nodes",
                inject_error="AssertionError: after sort [5,3,1,4,2] got [1,3,5] — lost 2 nodes",
            ),
            TaskStep(
                prompt="Add merge(other_list) that merges another sorted linked list into this sorted list (merge sort style). Return COMPLETE file with tests.",
                test_cmd="python3 -c \"exec(open('{file}').read()); a=LinkedList(); [a.append(x) for x in [1,3,5]]; b=LinkedList(); [b.append(x) for x in [2,4,6]]; a.merge(b); assert a.to_list()==[1,2,3,4,5,6]\"",
                description="add merge for sorted lists",
            ),
            TaskStep(
                prompt="merge() crashes when one list is empty. Also merge doesn't work when lists have duplicates — [1,1,2].merge([1,3]) should give [1,1,1,2,3]. Fix COMPLETE file.",
                test_cmd="python3 -c \"exec(open('{file}').read()); a=LinkedList(); b=LinkedList(); [b.append(x) for x in [1,2,3]]; a.merge(b); assert a.to_list()==[1,2,3]; print('empty merge ok')\"",
                description="fix merge edge cases",
            ),
            TaskStep(
                prompt="Final: add has_cycle()->bool that detects if the linked list has a cycle (Floyd's algorithm). Add comprehensive tests for ALL methods. Return COMPLETE file.",
                test_cmd="python3 {file}",
                description="cycle detection + final tests",
            ),
            TaskStep(
                prompt="Tests report: has_cycle returns True on a normal list with duplicate values. It should only return True when there's an actual pointer cycle. Fix it. Return COMPLETE file.",
                test_cmd="python3 -c \"exec(open('{file}').read()); ll=LinkedList(); [ll.append(x) for x in [1,1,1]]; assert not ll.has_cycle(), 'false positive on duplicates'\"",
                description="fix cycle detection false positive",
                inject_error="AssertionError: has_cycle() returned True for LinkedList([1,1,1]) — no cycle, just duplicates",
            ),
        ],
    }


def _task_state_machine() -> dict:
    """Build a state machine with progressively harder requirements."""
    return {
        "name": "state_machine",
        "description": "Build state machine with transitions, guards, hooks — error cascade test",
        "system": textwrap.dedent("""\
            You are a Python developer. Return ONLY a single python code block.
            No explanations. Include the complete file. Fix ALL issues when given errors.
        """),
        "steps": [
            TaskStep(
                prompt="Write a StateMachine class with: add_state(name), add_transition(from_state, to_state, event), trigger(event), current_state property. Initial state is first added state. Raise ValueError on invalid transition. Include tests.",
                test_cmd="python3 {file}",
                description="basic state machine",
            ),
            TaskStep(
                prompt="Error: trigger('nonexistent_event') doesn't raise ValueError, it silently does nothing. Also current_state is None before any state is added. Fix: raise ValueError for unknown events, raise RuntimeError if no states added. Return COMPLETE file.",
                test_cmd="python3 -c \"exec(open('{file}').read()); sm=StateMachine(); \\ntry:\\n    sm.trigger('x')\\n    assert False\\nexcept (RuntimeError, ValueError):\\n    pass\\nprint('ok')\"",
                description="error handling",
            ),
            TaskStep(
                prompt="Add guard conditions: add_transition(from, to, event, guard=None) where guard is a callable returning bool. Transition only fires if guard returns True. If guard returns False, raise GuardError. Return COMPLETE file.",
                test_cmd="python3 -c \"exec(open('{file}').read()); sm=StateMachine(); sm.add_state('a'); sm.add_state('b'); sm.add_transition('a','b','go', guard=lambda: False); \\ntry:\\n    sm.trigger('go')\\n    assert False, 'should raise'\\nexcept GuardError:\\n    pass\\nprint('guard ok')\"",
                description="guard conditions",
            ),
            TaskStep(
                prompt="Add on_enter and on_exit hooks: add_state(name, on_enter=None, on_exit=None). Hooks are callables, called during transitions. on_exit of source fires first, then on_enter of target. Return COMPLETE file.",
                test_cmd="python3 -c \"exec(open('{file}').read()); log=[]; sm=StateMachine(); sm.add_state('a', on_exit=lambda: log.append('exit_a')); sm.add_state('b', on_enter=lambda: log.append('enter_b')); sm.add_transition('a','b','go'); sm.trigger('go'); assert log==['exit_a','enter_b'], f'{{log}}'\"",
                description="enter/exit hooks",
            ),
            TaskStep(
                prompt="Error: hooks crash when they're None — TypeError: 'NoneType' is not callable. Also on_enter fires BEFORE on_exit. Fix the order and null checks. Return COMPLETE file.",
                test_cmd="python3 -c \"exec(open('{file}').read()); sm=StateMachine(); sm.add_state('a'); sm.add_state('b'); sm.add_transition('a','b','go'); sm.trigger('go'); assert sm.current_state=='b'\"",
                description="fix hook ordering and null safety",
                inject_error="TypeError: 'NoneType' object is not callable — hooks are None by default but called without check",
            ),
            TaskStep(
                prompt="Add history: transition_history property returns list of (from_state, to_state, event) tuples. Add reset() method that returns to initial state and clears history. Return COMPLETE file.",
                test_cmd="python3 -c \"exec(open('{file}').read()); sm=StateMachine(); sm.add_state('a'); sm.add_state('b'); sm.add_transition('a','b','go'); sm.trigger('go'); assert len(sm.transition_history)==1; sm.reset(); assert sm.current_state=='a'; assert len(sm.transition_history)==0\"",
                description="history + reset",
            ),
            TaskStep(
                prompt="Add wildcard transitions: add_transition('*', 'error', 'fail') means ANY state can transition to 'error' on 'fail' event. Return COMPLETE file.",
                test_cmd="python3 -c \"exec(open('{file}').read()); sm=StateMachine(); sm.add_state('a'); sm.add_state('b'); sm.add_state('err'); sm.add_transition('a','b','go'); sm.add_transition('*','err','fail'); sm.trigger('go'); sm.trigger('fail'); assert sm.current_state=='err'\"",
                description="wildcard transitions",
            ),
            TaskStep(
                prompt="Wildcard transition takes priority over specific transition when both match. It should be the opposite — specific first, wildcard as fallback. Fix. Return COMPLETE file.",
                test_cmd="python3 -c \"exec(open('{file}').read()); sm=StateMachine(); sm.add_state('a'); sm.add_state('b'); sm.add_state('c'); sm.add_transition('a','b','go'); sm.add_transition('*','c','go'); sm.trigger('go'); assert sm.current_state=='b', f'got {{sm.current_state}}, specific should win over wildcard'\"",
                description="fix wildcard priority",
                inject_error="AssertionError: got c, specific should win over wildcard",
            ),
            TaskStep(
                prompt="Final: add to_dot() method that exports the state machine as a Graphviz DOT string. Include all states, transitions, guards (show guard name), and mark current state. Add comprehensive final tests for everything. Return COMPLETE file.",
                test_cmd="python3 {file}",
                description="DOT export + comprehensive tests",
            ),
        ],
    }


def _task_expression_parser() -> dict:
    """Build a math expression parser — complex multi-step task."""
    return {
        "name": "expression_parser",
        "description": "Build recursive descent parser for math expressions — deep multi-step",
        "system": textwrap.dedent("""\
            You are a Python developer. Return ONLY a single python code block.
            No explanations. Complete file every time. Fix ALL issues.
        """),
        "steps": [
            TaskStep(
                prompt="Write a math expression evaluator that handles +, -, *, / with correct precedence and parentheses. Use recursive descent parsing. Function: evaluate(expr: str) -> float. Include tests for: '2+3' -> 5, '2+3*4' -> 14, '(2+3)*4' -> 20, '10/3' -> 3.333...",
                test_cmd="python3 {file}",
                description="basic expression parser",
            ),
            TaskStep(
                prompt="Error: evaluate('1+2+3') returns 6 but evaluate('10-3-2') returns 9 instead of 5. Left-to-right associativity is broken for subtraction. Fix. Return COMPLETE file.",
                test_cmd="python3 -c \"exec(open('{file}').read()); assert abs(evaluate('10-3-2') - 5.0) < 0.001, f'got {evaluate(\"10-3-2\")}'\"",
                description="fix left associativity",
                inject_error="AssertionError: evaluate('10-3-2') returned 9.0 instead of 5.0 — right-to-left parsing of subtraction",
            ),
            TaskStep(
                prompt="Add support for unary minus: evaluate('-5') -> -5, evaluate('-(3+2)') -> -5, evaluate('2*-3') -> -6. Return COMPLETE file.",
                test_cmd="python3 -c \"exec(open('{file}').read()); assert evaluate('-5')==-5; assert evaluate('-(3+2)')==-5; assert evaluate('2*-3')==-6; print('unary ok')\"",
                description="unary minus",
            ),
            TaskStep(
                prompt="Add power operator ^ with right associativity: evaluate('2^3') -> 8, evaluate('2^3^2') -> 512 (= 2^(3^2), not (2^3)^2=64). Power has higher precedence than * /. Return COMPLETE file.",
                test_cmd="python3 -c \"exec(open('{file}').read()); assert evaluate('2^3')==8; assert evaluate('2^3^2')==512, f'got {{evaluate(\"2^3^2\")}}, want 512'; print('power ok')\"",
                description="power operator with right associativity",
            ),
            TaskStep(
                prompt="Error: '2^3^2' evaluates to 64 instead of 512. You made it left-associative (2^3)^2=64. Power must be RIGHT-associative: 2^(3^2)=2^9=512. Fix the parsing direction for ^. Return COMPLETE file.",
                test_cmd="python3 -c \"exec(open('{file}').read()); r=evaluate('2^3^2'); assert r==512, f'got {{r}}'\"",
                description="fix power right-assoc",
                inject_error="AssertionError: got 64.0 — power parsed left-to-right but should be right-to-left",
            ),
            TaskStep(
                prompt="Add variables: evaluate('x+1', {'x': 5}) -> 6. Variables are single letters or words. Raise NameError for undefined variables. Return COMPLETE file.",
                test_cmd="python3 -c \"exec(open('{file}').read()); assert evaluate('x+y', {'x':3,'y':4})==7; \\ntry:\\n    evaluate('z+1', {})\\n    assert False\\nexcept NameError:\\n    pass\\nprint('vars ok')\"",
                description="variable support",
            ),
            TaskStep(
                prompt="Add built-in functions: sin, cos, sqrt, abs. evaluate('sqrt(16)') -> 4, evaluate('abs(-5)') -> 5. Return COMPLETE file.",
                test_cmd="python3 -c \"exec(open('{file}').read()); assert evaluate('sqrt(16)')==4; assert evaluate('abs(-5)')==5; import math; assert abs(evaluate('sin(0)') - 0) < 0.001; print('funcs ok')\"",
                description="built-in functions",
            ),
            TaskStep(
                prompt="Error: 'sqrt(2+2)' crashes with 'unexpected character (' — the parser doesn't handle function arguments as expressions. Also 'abs(sqrt(16))' crashes — nested function calls broken. Fix. Return COMPLETE file.",
                test_cmd="python3 -c \"exec(open('{file}').read()); assert evaluate('sqrt(2+2)')==2; assert evaluate('abs(sqrt(16))')==4; print('nested ok')\"",
                description="fix function arg parsing",
                inject_error="SyntaxError: unexpected '(' in function argument — parser treats '(' after function name differently than grouping parens",
            ),
            TaskStep(
                prompt="Final: add modulo operator %, implicit multiplication (2x -> 2*x, (2)(3) -> 6), and comprehensive tests. Return COMPLETE file.",
                test_cmd="python3 {file}",
                description="modulo + implicit multiply + final tests",
            ),
        ],
    }


TASKS = [_task_linked_list(), _task_state_machine(), _task_expression_parser()]


# ------------------------------------------------------------------
# Result types
# ------------------------------------------------------------------


@dataclass
class StepResult:
    step_index: int
    prompt_preview: str
    response_preview: str
    input_tokens: int
    output_tokens: int
    test_passed: bool
    test_output: str
    duration_seconds: float
    soma_pressure: float
    soma_mode: str
    guidance_injected: str
    reflex_blocked: bool = False


@dataclass
class LiveRunResult:
    task_name: str
    soma_enabled: bool
    reflex_enabled: bool = False
    steps: list[StepResult] = field(default_factory=list)
    total_tokens: int = 0
    total_duration: float = 0.0
    final_test_passed: bool = False
    total_retries: int = 0
    total_reflex_blocks: int = 0
    error: str | None = None


@dataclass
class LiveTaskResult:
    task_name: str
    description: str
    baseline_runs: list[LiveRunResult] = field(default_factory=list)
    soma_runs: list[LiveRunResult] = field(default_factory=list)
    reflex_runs: list[LiveRunResult] = field(default_factory=list)

    def _avg(self, runs: list[LiveRunResult], attr: str) -> float:
        good = [r for r in runs if not r.error]
        return statistics.mean(getattr(r, attr) for r in good) if good else 0

    @property
    def avg_baseline_tokens(self): return self._avg(self.baseline_runs, "total_tokens")
    @property
    def avg_soma_tokens(self): return self._avg(self.soma_runs, "total_tokens")
    @property
    def avg_reflex_tokens(self): return self._avg(self.reflex_runs, "total_tokens")
    @property
    def avg_baseline_retries(self): return self._avg(self.baseline_runs, "total_retries")
    @property
    def avg_soma_retries(self): return self._avg(self.soma_runs, "total_retries")
    @property
    def avg_reflex_retries(self): return self._avg(self.reflex_runs, "total_retries")
    @property
    def avg_reflex_blocks(self): return self._avg(self.reflex_runs, "total_reflex_blocks")

    def _pass_rate(self, runs):
        good = [r for r in runs if not r.error]
        return sum(1 for r in good if r.final_test_passed) / len(good) if good else 0

    @property
    def baseline_pass_rate(self): return self._pass_rate(self.baseline_runs)
    @property
    def soma_pass_rate(self): return self._pass_rate(self.soma_runs)
    @property
    def reflex_pass_rate(self): return self._pass_rate(self.reflex_runs)


@dataclass
class LiveBenchmarkResult:
    tasks: list[LiveTaskResult] = field(default_factory=list)
    model: str = ""
    runs_per_task: int = 3
    timestamp: str = ""
    total_cost_estimate: float = 0.0


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------


def _extract_code(text: str) -> str:
    """Extract Python code from markdown code blocks."""
    if "```python" in text:
        parts = text.split("```python")
        if len(parts) > 1:
            return parts[1].split("```")[0].strip()
    if "```" in text:
        parts = text.split("```")
        if len(parts) > 1:
            code = parts[1].lstrip("\n")
            return code.split("```")[0].strip()
    return text.strip()


def _run_test(cmd: str, file_path: str) -> tuple[bool, str]:
    """Run test command, return (passed, output)."""
    cmd = cmd.replace("{file}", file_path)
    try:
        result = subprocess.run(
            cmd, shell=True, capture_output=True, text=True, timeout=10
        )
        output = (result.stdout + result.stderr).strip()
        return result.returncode == 0, output[:500]
    except subprocess.TimeoutExpired:
        return False, "TIMEOUT"
    except Exception as e:
        return False, str(e)[:500]


def _build_guidance(engine, agent_id: str) -> str:
    """Build SOMA guidance from engine state."""
    try:
        snap = engine.get_snapshot(agent_id)
        pressure = snap.get("pressure", 0.0)
        mode = snap.get("mode")
        mode_name = mode.name if hasattr(mode, "name") else str(mode)

        if mode_name == "OBSERVE":
            return ""

        vitals = snap.get("vitals", {})
        parts = [f"[SOMA {mode_name} p={pressure:.0%}]"]

        er = vitals.get("error_rate", 0)
        if er > 0.3:
            parts.append(f"Error rate {er:.0%} — try a COMPLETELY different approach.")
        unc = vitals.get("uncertainty", 0)
        if unc > 0.3:
            parts.append("High uncertainty — read the error carefully, don't just retry.")
        drift = vitals.get("drift", 0)
        if drift > 0.2:
            parts.append("You're drifting. Focus on the specific error, not adding features.")

        return " ".join(parts)
    except Exception:
        return ""


# ------------------------------------------------------------------
# Multi-turn runner
# ------------------------------------------------------------------


def _run_multi_turn(
    task: dict,
    soma_enabled: bool,
    reflex_enabled: bool,
    model: str,
) -> LiveRunResult:
    """Run a multi-turn agent loop."""
    import anthropic

    engine = None
    if soma_enabled:
        engine = soma_mod.quickstart()
        engine.register_agent("live-bench")
        # Reduce grace period from 10 to 3 so SOMA activates during the task
        agent_state = engine._agents.get("live-bench")
        if agent_state:
            agent_state.baseline.min_samples = 3

    client = anthropic.Anthropic()
    steps_results: list[StepResult] = []
    messages: list[dict] = []
    total_tokens = 0
    total_retries = 0
    total_reflex_blocks = 0
    last_test_passed = False
    action_log: list[dict] = []
    bash_history: list[str] = []

    import tempfile
    with tempfile.NamedTemporaryFile(suffix=".py", mode="w", delete=False) as f:
        tmp_file = f.name

    try:
        for step_idx, step in enumerate(task["steps"]):
            t0 = time.monotonic()

            # Build prompt
            guidance_text = ""
            if engine and soma_enabled:
                guidance_text = _build_guidance(engine, "live-bench")

            user_prompt = step.prompt
            if guidance_text:
                user_prompt = f"{guidance_text}\n\n{user_prompt}"

            messages.append({"role": "user", "content": user_prompt})

            # Check reflex before calling LLM (simulates PreToolUse)
            reflex_blocked = False
            if reflex_enabled and engine and step_idx > 0:
                rr = reflex_evaluate(
                    tool_name="Edit",
                    tool_input={"file_path": tmp_file},
                    action_log=action_log[-20:],
                    pressure=engine.get_snapshot("live-bench").get("pressure", 0),
                    config={},
                    bash_history=bash_history[-10:],
                )
                if not rr.allow:
                    reflex_blocked = True
                    total_reflex_blocks += 1
                    # Inject block message into conversation instead of calling LLM
                    block_msg = rr.block_message or "Action blocked by SOMA reflex"
                    messages[-1] = {"role": "user", "content": f"[SOMA REFLEX BLOCKED previous action]\n{block_msg}\n\n{user_prompt}"}

            # Call LLM
            try:
                response = client.messages.create(
                    model=model,
                    max_tokens=4096,
                    system=task["system"],
                    messages=messages,
                )
                response_text = response.content[0].text if response.content else ""
                input_tokens = response.usage.input_tokens
                output_tokens = response.usage.output_tokens
            except Exception as e:
                return LiveRunResult(
                    task_name=task["name"],
                    soma_enabled=soma_enabled,
                    reflex_enabled=reflex_enabled,
                    error=str(e),
                )

            messages.append({"role": "assistant", "content": response_text})
            total_tokens += input_tokens + output_tokens

            # Extract code and write
            code = _extract_code(response_text)
            Path(tmp_file).write_text(code)

            # Run test
            test_passed, test_output = _run_test(step.test_cmd, tmp_file)

            # Override with injected error if present
            if step.inject_error and test_passed:
                test_passed = False
                test_output = step.inject_error

            if not test_passed:
                total_retries += 1
                # Feed error back as next user message
                if step_idx < len(task["steps"]) - 1:
                    # Error gets picked up by next step's prompt
                    pass
            last_test_passed = test_passed

            # Record in SOMA engine
            pressure = 0.0
            mode_name = "NONE"
            if engine:
                result = engine.record_action(
                    "live-bench",
                    Action(
                        tool_name="Edit",
                        output_text=test_output[:200] if not test_passed else "tests passed",
                        token_count=input_tokens + output_tokens,
                        error=not test_passed,
                    ),
                )
                pressure = result.pressure
                mode_name = result.mode.name
                action_log.append({
                    "tool": "Edit", "error": not test_passed,
                    "file": tmp_file, "ts": time.time(),
                })

            elapsed = time.monotonic() - t0

            steps_results.append(StepResult(
                step_index=step_idx,
                prompt_preview=step.prompt[:80],
                response_preview=response_text[:150],
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                test_passed=test_passed,
                test_output=test_output[:200],
                duration_seconds=elapsed,
                soma_pressure=pressure,
                soma_mode=mode_name,
                guidance_injected=guidance_text,
                reflex_blocked=reflex_blocked,
            ))

    finally:
        Path(tmp_file).unlink(missing_ok=True)

    return LiveRunResult(
        task_name=task["name"],
        soma_enabled=soma_enabled,
        reflex_enabled=reflex_enabled,
        steps=steps_results,
        total_tokens=total_tokens,
        total_duration=sum(s.duration_seconds for s in steps_results),
        final_test_passed=last_test_passed,
        total_retries=total_retries,
        total_reflex_blocks=total_reflex_blocks,
    )


# ------------------------------------------------------------------
# Public API
# ------------------------------------------------------------------


def run_live_benchmark(
    runs_per_task: int = 3,
    model: str = "claude-haiku-4-5-20251001",
    tasks: list[dict] | None = None,
) -> LiveBenchmarkResult:
    """Run live benchmark: baseline vs SOMA guidance vs SOMA reflexes.

    Each task runs 3 ways: no SOMA, SOMA guidance, SOMA reflexes.
    """
    if "ANTHROPIC_API_KEY" not in os.environ:
        raise RuntimeError("ANTHROPIC_API_KEY not set")

    task_defs = tasks or TASKS
    task_results: list[LiveTaskResult] = []
    total_tokens = 0

    for task in task_defs:
        tr = LiveTaskResult(task_name=task["name"], description=task["description"])

        for _ in range(runs_per_task):
            # Baseline (no SOMA)
            r = _run_multi_turn(task, soma_enabled=False, reflex_enabled=False, model=model)
            tr.baseline_runs.append(r)
            total_tokens += r.total_tokens

            # SOMA guidance only
            r = _run_multi_turn(task, soma_enabled=True, reflex_enabled=False, model=model)
            tr.soma_runs.append(r)
            total_tokens += r.total_tokens

            # SOMA reflexes
            r = _run_multi_turn(task, soma_enabled=True, reflex_enabled=True, model=model)
            tr.reflex_runs.append(r)
            total_tokens += r.total_tokens

        task_results.append(tr)

    est_cost = total_tokens * 0.003 / 1000

    return LiveBenchmarkResult(
        tasks=task_results,
        model=model,
        runs_per_task=runs_per_task,
        timestamp=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        total_cost_estimate=est_cost,
    )


# ------------------------------------------------------------------
# Report
# ------------------------------------------------------------------


def generate_live_report(result: LiveBenchmarkResult) -> str:
    lines = [
        "# SOMA Live Benchmark — Real LLM Results",
        "",
        f"> **Model:** {result.model}",
        f"> **Runs per task:** {result.runs_per_task}",
        f"> **Generated:** {result.timestamp}",
        f"> **Cost:** ${result.total_cost_estimate:.2f}",
        "",
        "## Summary",
        "",
        "| Task | Mode | Tokens | Retries | Pass Rate | Reflex Blocks |",
        "|------|------|--------|---------|-----------|---------------|",
    ]

    for tr in result.tasks:
        lines.append(f"| {tr.task_name} | baseline | {tr.avg_baseline_tokens:.0f} | {tr.avg_baseline_retries:.1f} | {tr.baseline_pass_rate:.0%} | — |")
        lines.append(f"| | guidance | {tr.avg_soma_tokens:.0f} | {tr.avg_soma_retries:.1f} | {tr.soma_pass_rate:.0%} | — |")
        lines.append(f"| | **reflex** | {tr.avg_reflex_tokens:.0f} | {tr.avg_reflex_retries:.1f} | {tr.reflex_pass_rate:.0%} | {tr.avg_reflex_blocks:.1f} |")

    lines.extend(["", "## Per-Task Details", ""])

    for tr in result.tasks:
        lines.extend([f"### {tr.task_name}", f"_{tr.description}_", ""])

        for label, runs in [("Baseline", tr.baseline_runs), ("Guidance", tr.soma_runs), ("Reflex", tr.reflex_runs)]:
            lines.append(f"**{label}:**")
            for i, run in enumerate(runs, 1):
                if run.error:
                    lines.append(f"- Run {i}: ERROR — {run.error[:100]}")
                    continue
                blocks = f", {run.total_reflex_blocks} blocks" if run.total_reflex_blocks else ""
                lines.append(
                    f"- Run {i}: {run.total_tokens}tok, {run.total_retries} retries, "
                    f"{'PASS' if run.final_test_passed else 'FAIL'}, {run.total_duration:.0f}s{blocks}"
                )
                for s in run.steps:
                    g = f" | {s.guidance_injected[:50]}" if s.guidance_injected else ""
                    b = " [BLOCKED]" if s.reflex_blocked else ""
                    lines.append(f"  - Step {s.step_index+1}: {'OK' if s.test_passed else 'FAIL'} p={s.soma_pressure:.0%} {s.soma_mode}{b}{g}")
            lines.append("")

    lines.extend(["---", f"*Generated by `soma benchmark --live` | {result.timestamp}*"])
    return "\n".join(lines)


def render_live_terminal(result: LiveBenchmarkResult) -> None:
    try:
        from rich.console import Console
        from rich.table import Table
        from rich.panel import Panel
        console = Console()
    except ImportError:
        print(generate_live_report(result))
        return

    console.print()
    console.print(Panel(
        f"[bold]SOMA Live Benchmark[/bold]\n"
        f"[dim]{result.model} | {result.runs_per_task} runs | ${result.total_cost_estimate:.2f}[/dim]",
        border_style="magenta", width=80,
    ))

    table = Table(border_style="magenta", width=80)
    table.add_column("Task")
    table.add_column("Mode", style="dim")
    table.add_column("Tokens", justify="right")
    table.add_column("Retries", justify="right")
    table.add_column("Pass", justify="right")
    table.add_column("Blocks", justify="right")

    for tr in result.tasks:
        table.add_row(f"[bold]{tr.task_name}[/bold]", "baseline", f"{tr.avg_baseline_tokens:.0f}", f"{tr.avg_baseline_retries:.1f}", f"{tr.baseline_pass_rate:.0%}", "—")
        table.add_row("", "guidance", f"{tr.avg_soma_tokens:.0f}", f"{tr.avg_soma_retries:.1f}", f"{tr.soma_pass_rate:.0%}", "—")
        table.add_row("", "[bold magenta]reflex[/bold magenta]", f"{tr.avg_reflex_tokens:.0f}", f"{tr.avg_reflex_retries:.1f}", f"{tr.reflex_pass_rate:.0%}", f"{tr.avg_reflex_blocks:.1f}")

    console.print(table)
    console.print()
