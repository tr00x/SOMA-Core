"""Benchmark task definitions for live LLM A/B testing.

Contains 10 multi-turn coding tasks with deliberate error injection
to create realistic failure cascades. Tasks range from easy to hard
and cover diverse software engineering scenarios.

Difficulty distribution:
  - Easy:   write_documentation, cli_argument_parser, add_test_coverage
  - Medium: debug_failing_test, fix_security_vuln, optimize_performance, multi_file_refactor
  - Hard:   linked_list_with_bugs, state_machine, expression_parser

Fairness: tasks are solvable without SOMA. inject_error creates realistic
confusion (not impossible situations). SOMA's guidance COULD help with
error cascades and retry patterns but is not required.
"""

from __future__ import annotations

import textwrap
from dataclasses import dataclass


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
# Task 1 (hard): Linked List with bugs
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


# ------------------------------------------------------------------
# Task 2 (hard): State Machine
# ------------------------------------------------------------------

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


# ------------------------------------------------------------------
# Task 3 (hard): Expression Parser
# ------------------------------------------------------------------

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


# ------------------------------------------------------------------
# Task 4 (medium): Debug Failing Test
# ------------------------------------------------------------------

def _task_debug_failing_test() -> dict:
    """Debug code with subtle bugs — misleading errors lead to deeper issues."""
    return {
        "name": "debug_failing_test",
        "description": "Given buggy code, debug through misleading errors to find real issues",
        "system": textwrap.dedent("""\
            You are a Python developer. Return ONLY a single python code block.
            No explanations. Include the complete file. Fix ALL issues when given errors.
        """),
        "steps": [
            TaskStep(
                prompt="Here's a TokenBucket rate limiter with bugs. Fix ALL issues:\n\n```python\nimport time\n\nclass TokenBucket:\n    def __init__(self, capacity, refill_rate):\n        self.capacity = capacity\n        self.tokens = capacity\n        self.refill_rate = refill_rate  # tokens per second\n        self.last_refill = time.time()\n    \n    def _refill(self):\n        now = time.time()\n        elapsed = now - self.last_refill\n        self.tokens += elapsed * self.refill_rate\n        # Bug: no cap at capacity\n        self.last_refill = now\n    \n    def consume(self, tokens=1):\n        self._refill()\n        if self.tokens >= tokens:\n            self.tokens -= tokens\n            return True\n        return False\n    \n    def wait_and_consume(self, tokens=1):\n        while not self.consume(tokens):\n            time.sleep(0.1)  # Bug: doesn't calculate optimal wait time\n        return True\n    \n    @property\n    def available(self):\n        return self.tokens  # Bug: doesn't refill before reporting\n\n# Tests\nb = TokenBucket(10, 2)\nassert b.consume(5)\nassert b.available == 5\nassert b.consume(6) == False  # only 5 left\nprint('basic tests pass')\n```\n\nFix the bugs: tokens should cap at capacity, available should refill before reporting, wait_and_consume should calculate sleep time. Return COMPLETE file with tests.",
                test_cmd="python3 {file}",
                description="initial buggy code — fix obvious bugs",
            ),
            TaskStep(
                prompt="Error: available property returns 5.0000234 instead of exactly 5. Floating point drift from time-based refill accumulates. The test `assert b.available == 5` fails intermittently. Fix by using min() cap and integer-friendly checks. Return COMPLETE file.",
                test_cmd="python3 -c \"exec(open('{file}').read()); b=TokenBucket(10,2); b.consume(5); assert b.available <= 10, 'exceeded capacity'; assert b.consume(5); assert not b.consume(1); print('cap ok')\"",
                description="fix floating point drift",
                inject_error="AssertionError: available returned 10.000047 — tokens exceeded capacity due to floating point accumulation in refill",
            ),
            TaskStep(
                prompt="New requirement: add a ThreadSafeTokenBucket subclass that uses threading.Lock for thread safety. consume() and _refill() must be atomic. Return COMPLETE file with a test that spawns 10 threads each consuming 1 token from a bucket of 5 — exactly 5 should succeed.",
                test_cmd="python3 -c \"exec(open('{file}').read()); import threading; b=ThreadSafeTokenBucket(5, 0); results=[]; threads=[threading.Thread(target=lambda: results.append(b.consume(1))) for _ in range(10)]; [t.start() for t in threads]; [t.join() for t in threads]; assert sum(results)==5, f'{{sum(results)}} succeeded instead of 5'; print('thread ok')\"",
                description="thread-safe subclass",
            ),
            TaskStep(
                prompt="Error: ThreadSafeTokenBucket deadlocks because consume() acquires lock, then calls _refill() which also tries to acquire the same lock. Fix using a reentrant lock or restructuring. Return COMPLETE file.",
                test_cmd="python3 -c \"exec(open('{file}').read()); b=ThreadSafeTokenBucket(10, 1); assert b.consume(1); assert b.available <= 10; print('no deadlock')\"",
                description="fix deadlock",
                inject_error="Deadlock detected: consume() holds lock, calls _refill() which blocks on same lock",
            ),
            TaskStep(
                prompt="New requirement: add a RateLimiter class that uses TokenBucket internally. Interface: RateLimiter(max_requests, per_seconds). check(key: str) -> bool where each key has its own bucket. Return COMPLETE file.",
                test_cmd="python3 -c \"exec(open('{file}').read()); rl=RateLimiter(3, 1); assert rl.check('user1'); assert rl.check('user1'); assert rl.check('user1'); assert not rl.check('user1'); assert rl.check('user2'); print('rate limit ok')\"",
                description="per-key rate limiter",
            ),
            TaskStep(
                prompt="RateLimiter leaks memory — it creates a new bucket for every unique key and never cleans up. After 1M keys, memory usage is enormous. Add cleanup of stale buckets (not used in last N seconds). Return COMPLETE file.",
                test_cmd="python3 -c \"exec(open('{file}').read()); rl=RateLimiter(10, 1); [rl.check(f'user{{i}}') for i in range(100)]; rl.cleanup(max_age=0); assert len(rl._buckets) == 0, f'{{len(rl._buckets)}} buckets remain'; print('cleanup ok')\"",
                description="fix memory leak with cleanup",
            ),
            TaskStep(
                prompt="Error: cleanup() removes active buckets too because it checks creation time, not last access time. A bucket created 10 seconds ago but used 1 second ago should NOT be cleaned up. Track last_access. Return COMPLETE file.",
                test_cmd="python3 -c \"exec(open('{file}').read()); import time; rl=RateLimiter(10, 60); rl.check('active'); time.sleep(0.05); rl.check('active'); rl.cleanup(max_age=0.01); assert 'active' in rl._buckets, 'removed active bucket'; print('cleanup fixed')\"",
                description="fix cleanup removing active buckets",
                inject_error="KeyError: 'active' — cleanup removed a bucket that was just used because it checked creation time, not last_access",
            ),
            TaskStep(
                prompt="Final: add comprehensive tests covering all edge cases — zero capacity, zero refill rate, negative consume, concurrent access, cleanup correctness, and a sliding window count test. Return COMPLETE file.",
                test_cmd="python3 {file}",
                description="comprehensive final tests",
            ),
        ],
    }


# ------------------------------------------------------------------
# Task 5 (easy): Write Documentation Generator
# ------------------------------------------------------------------

def _task_write_documentation() -> dict:
    """Build a markdown document generator class step by step."""
    return {
        "name": "write_documentation",
        "description": "Build a markdown generator class — straightforward incremental build",
        "system": textwrap.dedent("""\
            You are a Python developer. Return ONLY a single python code block.
            No explanations. Include the complete file. Fix ALL issues when given errors.
        """),
        "steps": [
            TaskStep(
                prompt="Write a MarkdownDoc class that generates markdown text. Start with: heading(text, level=1), paragraph(text), render() -> str. render() returns the full markdown string. Include tests with assert statements.",
                test_cmd="python3 {file}",
                description="basic markdown generator",
            ),
            TaskStep(
                prompt="Add code_block(code, language=None) that renders fenced code blocks with optional language tag. Also add horizontal_rule(). Return COMPLETE file.",
                test_cmd="python3 -c \"exec(open('{file}').read()); d=MarkdownDoc(); d.code_block('print(1)', 'python'); r=d.render(); assert '```python' in r; assert 'print(1)' in r; assert '```' in r; print('code ok')\"",
                description="code blocks + horizontal rule",
            ),
            TaskStep(
                prompt="Error: code_block doesn't properly escape backticks inside the code. If the code contains ``` the output breaks markdown rendering. Use ~~~~ as alternative fence when content contains backticks. Return COMPLETE file.",
                test_cmd="python3 -c \"exec(open('{file}').read()); d=MarkdownDoc(); d.code_block('x = \\\"```test```\\\"'); r=d.render(); assert '~~~~' in r or r.count('```') % 2 == 0; print('escape ok')\"",
                description="fix backtick escaping in code blocks",
                inject_error="Markdown rendering broken: code_block content containing ``` produces invalid markdown with unmatched fences",
            ),
            TaskStep(
                prompt="Add table(headers: list[str], rows: list[list[str]]) that renders a proper markdown table with alignment row. Return COMPLETE file.",
                test_cmd="python3 -c \"exec(open('{file}').read()); d=MarkdownDoc(); d.table(['Name','Age'], [['Alice','30'],['Bob','25']]); r=d.render(); assert '| Name | Age |' in r; assert '| --- | --- |' in r or '|---|---|' in r; assert 'Alice' in r; print('table ok')\"",
                description="markdown table support",
            ),
            TaskStep(
                prompt="Add bullet_list(items: list[str]) and numbered_list(items: list[str]). Support nested lists by accepting list[str | list[str]] where inner lists become indented sub-items. Return COMPLETE file.",
                test_cmd="python3 -c \"exec(open('{file}').read()); d=MarkdownDoc(); d.bullet_list(['a', ['sub1', 'sub2'], 'b']); r=d.render(); assert '- a' in r; assert '  - sub1' in r; assert '- b' in r; print('list ok')\"",
                description="nested list support",
            ),
            TaskStep(
                prompt="Add link(text, url) and image(alt, url) inline helpers that return markdown strings (not added to doc, just return the string). Also add blockquote(text) that adds a > prefixed block to the doc. Return COMPLETE file.",
                test_cmd="python3 -c \"exec(open('{file}').read()); d=MarkdownDoc(); assert d.link('click', 'http://x.com') == '[click](http://x.com)'; assert d.image('pic', 'img.png') == '![pic](img.png)'; d.blockquote('wise words'); assert '> wise words' in d.render(); print('inline ok')\"",
                description="links, images, blockquotes",
            ),
            TaskStep(
                prompt="Add table_of_contents() method that generates a TOC from all headings added so far. TOC entries should be indented by heading level and link to the heading using GitHub-style anchors (lowercase, spaces to hyphens). Return COMPLETE file.",
                test_cmd="python3 -c \"exec(open('{file}').read()); d=MarkdownDoc(); d.heading('Introduction', 1); d.heading('Sub Topic', 2); d.heading('Details', 3); toc=d.table_of_contents(); assert '#introduction' in toc.lower() or 'introduction' in toc.lower(); assert 'sub-topic' in toc.lower() or 'sub topic' in toc.lower(); print('toc ok')\"",
                description="table of contents generation",
                inject_error="TypeError: table_of_contents() cannot generate anchors — headings stored as rendered strings, not structured data. Need to track heading text and level separately.",
            ),
            TaskStep(
                prompt="Final: add a template(name) classmethod that returns pre-built docs. Support 'readme' (title, badges, install, usage, license sections) and 'api' (title, endpoints table, auth, errors). Add comprehensive tests for ALL features. Return COMPLETE file.",
                test_cmd="python3 {file}",
                description="templates + comprehensive tests",
            ),
        ],
    }


# ------------------------------------------------------------------
# Task 6 (easy): CLI Argument Parser
# ------------------------------------------------------------------

def _task_cli_argument_parser() -> dict:
    """Build a CLI tool with argparse, subcommands, and config file support."""
    return {
        "name": "cli_argument_parser",
        "description": "Build CLI tool with subcommands, validation, config — incremental build",
        "system": textwrap.dedent("""\
            You are a Python developer. Return ONLY a single python code block.
            No explanations. Include the complete file. Fix ALL issues when given errors.
        """),
        "steps": [
            TaskStep(
                prompt="Write a CLI tool using argparse with a TaskManager class. Commands: 'add <title>' adds a task, 'list' shows all tasks, 'done <id>' marks complete. Use a simple in-memory list. Parse args from a list (not sys.argv) so it's testable: parse_and_run(args: list[str], manager: TaskManager) -> str. Include tests.",
                test_cmd="python3 {file}",
                description="basic CLI with argparse",
            ),
            TaskStep(
                prompt="Add subcommands: 'task add', 'task list', 'task done'. Also add 'task edit <id> --title <new_title>' and 'task delete <id>'. Return COMPLETE file.",
                test_cmd="python3 -c \"exec(open('{file}').read()); m=TaskManager(); r=parse_and_run(['task','add','Buy milk'], m); assert 'added' in r.lower() or '1' in r; r=parse_and_run(['task','list'], m); assert 'milk' in r.lower() or 'Milk' in r; print('subcmd ok')\"",
                description="subcommands",
            ),
            TaskStep(
                prompt="Add input validation: title must be non-empty, id must be a positive integer that exists, done on already-done task shows warning. Return helpful error messages. Return COMPLETE file.",
                test_cmd="python3 -c \"exec(open('{file}').read()); m=TaskManager(); r=parse_and_run(['task','done','999'], m); assert 'not found' in r.lower() or 'error' in r.lower() or 'invalid' in r.lower(); print('validation ok')\"",
                description="input validation",
            ),
            TaskStep(
                prompt="Add config file support: 'config set <key> <value>' and 'config get <key>'. Store config as JSON dict. Supported keys: 'default_priority' (low/medium/high), 'show_completed' (true/false). Config modifies task list behavior. Return COMPLETE file.",
                test_cmd="python3 -c \"exec(open('{file}').read()); m=TaskManager(); parse_and_run(['config','set','default_priority','high'], m); r=parse_and_run(['config','get','default_priority'], m); assert 'high' in r; print('config ok')\"",
                description="config file support",
            ),
            TaskStep(
                prompt="Error: config get returns the raw dict repr instead of just the value. Also config set accepts invalid keys without error. Validate keys against supported set and format output cleanly. Return COMPLETE file.",
                test_cmd="python3 -c \"exec(open('{file}').read()); m=TaskManager(); r=parse_and_run(['config','set','invalid_key','x'], m); assert 'unknown' in r.lower() or 'invalid' in r.lower() or 'error' in r.lower(); print('config validation ok')\"",
                description="fix config output and validation",
                inject_error="KeyError: config set accepts any key name without validation — 'config set foo bar' silently succeeds but 'config get foo' crashes",
            ),
            TaskStep(
                prompt="Add output formatting: 'task list --format table' shows a formatted table (ASCII), 'task list --format json' outputs JSON. Default is table. Add --priority filter: 'task list --priority high'. Return COMPLETE file.",
                test_cmd="python3 -c \"exec(open('{file}').read()); m=TaskManager(); parse_and_run(['task','add','Test','--priority','high'], m) if '--priority' in str(parse_and_run.__code__.co_varnames) else parse_and_run(['task','add','Test'], m); r=parse_and_run(['task','list','--format','json'], m); import json; json.loads(r); print('format ok')\"",
                description="output formatting",
            ),
            TaskStep(
                prompt="Add error handling: wrap all commands in try/except, return user-friendly messages. Add --verbose flag that shows tracebacks. Add 'task search <query>' that searches titles. Return COMPLETE file.",
                test_cmd="python3 -c \"exec(open('{file}').read()); m=TaskManager(); parse_and_run(['task','add','Buy groceries'], m); parse_and_run(['task','add','Buy shoes'], m); r=parse_and_run(['task','search','Buy'], m); assert 'groceries' in r.lower() or 'Buy' in r; print('search ok')\"",
                description="error handling + search",
                inject_error="TypeError: parse_and_run() missing error handling — 'task search' with no query crashes with IndexError instead of showing help",
            ),
            TaskStep(
                prompt="Final: add 'task export <filename>' that writes tasks to JSON and 'task import <filename>' that loads from JSON. Add comprehensive tests for ALL features including edge cases. Return COMPLETE file.",
                test_cmd="python3 {file}",
                description="import/export + comprehensive tests",
            ),
        ],
    }


# ------------------------------------------------------------------
# Task 7 (medium): Fix Security Vulnerabilities
# ------------------------------------------------------------------

def _task_fix_security_vuln() -> dict:
    """Fix code with SQL injection, XSS, and path traversal vulnerabilities."""
    return {
        "name": "fix_security_vuln",
        "description": "Identify and fix security vulnerabilities in web-like code",
        "system": textwrap.dedent("""\
            You are a Python developer. Return ONLY a single python code block.
            No explanations. Include the complete file. Fix ALL issues when given errors.
        """),
        "steps": [
            TaskStep(
                prompt="Here's a vulnerable user management module. Identify and fix ALL security issues:\n\n```python\nimport sqlite3\nimport os\nimport hashlib\n\nclass UserDB:\n    def __init__(self, db_path=':memory:'):\n        self.conn = sqlite3.connect(db_path)\n        self.conn.execute('CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY, username TEXT, password TEXT, role TEXT)')\n    \n    def add_user(self, username, password, role='user'):\n        # SQL injection vulnerable\n        self.conn.execute(f\"INSERT INTO users (username, password, role) VALUES ('{username}', '{password}', '{role}')\")\n        self.conn.commit()\n    \n    def login(self, username, password):\n        # SQL injection vulnerable\n        cur = self.conn.execute(f\"SELECT * FROM users WHERE username='{username}' AND password='{password}'\")\n        return cur.fetchone()\n    \n    def get_profile_page(self, username):\n        # XSS vulnerable\n        return f'<html><body><h1>Welcome {username}!</h1></body></html>'\n    \n    def read_user_file(self, username, filename):\n        # Path traversal vulnerable\n        filepath = f'uploads/{username}/{filename}'\n        with open(filepath) as f:\n            return f.read()\n\n# Tests\ndb = UserDB()\ndb.add_user('alice', 'password123')\nresult = db.login('alice', 'password123')\nassert result is not None\nprint('basic tests pass')\n```\n\nFix SQL injection (use parameterized queries), add password hashing, fix XSS, fix path traversal. Return COMPLETE file.",
                test_cmd="python3 {file}",
                description="fix SQL injection, XSS, path traversal",
            ),
            TaskStep(
                prompt="Password hashing is using MD5 which is insecure. Switch to bcrypt or at minimum hashlib.pbkdf2_hmac with salt. Store salt alongside hash. Return COMPLETE file.",
                test_cmd="python3 -c \"exec(open('{file}').read()); db=UserDB(); db.add_user('test','secret'); row=db.login('test','secret'); assert row is not None; assert 'secret' not in str(row), 'password stored in plaintext'; print('hash ok')\"",
                description="upgrade password hashing",
            ),
            TaskStep(
                prompt="Error: login() compares hashed password with raw password — login always fails after switching to hashing. The login method needs to hash the input password with the same salt before comparing. Return COMPLETE file.",
                test_cmd="python3 -c \"exec(open('{file}').read()); db=UserDB(); db.add_user('alice','pass123'); assert db.login('alice','pass123') is not None, 'valid login failed'; assert db.login('alice','wrong') is None, 'invalid login succeeded'; print('login ok')\"",
                description="fix login after hashing change",
                inject_error="AssertionError: valid login failed — login('alice','pass123') returns None because password hash comparison is broken after adding salt-based hashing",
            ),
            TaskStep(
                prompt="Fix path traversal properly: read_user_file('alice', '../../etc/passwd') must raise a security error. Use os.path.realpath to canonicalize and verify the resolved path starts with the allowed base directory. Return COMPLETE file.",
                test_cmd="python3 -c \"exec(open('{file}').read()); db=UserDB(); \\ntry:\\n    db.read_user_file('alice', '../../etc/passwd')\\n    assert False, 'should raise'\\nexcept (PermissionError, ValueError, OSError):\\n    pass\\nprint('path traversal blocked')\"",
                description="fix path traversal defense",
            ),
            TaskStep(
                prompt="Add input validation: username must be alphanumeric 3-30 chars, password minimum 8 chars, role must be 'user' or 'admin'. Raise ValueError with descriptive messages for invalid input. Return COMPLETE file.",
                test_cmd="python3 -c \"exec(open('{file}').read()); db=UserDB(); \\ntry:\\n    db.add_user('ab', 'password123')\\n    assert False, 'short username should fail'\\nexcept ValueError as e:\\n    assert 'username' in str(e).lower() or '3' in str(e)\\ntry:\\n    db.add_user('alice', 'short')\\n    assert False, 'short password should fail'\\nexcept ValueError:\\n    pass\\nprint('validation ok')\"",
                description="input validation",
            ),
            TaskStep(
                prompt="Add rate limiting: after 5 failed login attempts for a username, lock the account for 60 seconds. Track failed attempts in a separate table. Return COMPLETE file.",
                test_cmd="python3 -c \"exec(open('{file}').read()); db=UserDB(); db.add_user('testuser','password123'); [db.login('testuser','wrong') for _ in range(5)]; result=db.login('testuser','password123'); assert result is None, 'should be locked after 5 failures'; print('rate limit ok')\"",
                description="add rate limiting / account lockout",
                inject_error="sqlite3.OperationalError: no such table: login_attempts — rate limiting table not created in __init__",
            ),
            TaskStep(
                prompt="Final: add comprehensive security tests — SQL injection attempts in all fields, XSS payloads, path traversal variants, brute force lockout, password hash verification. Add delete_user(username) with authorization check (only admin role). Return COMPLETE file.",
                test_cmd="python3 {file}",
                description="comprehensive security tests",
            ),
        ],
    }


# ------------------------------------------------------------------
# Task 8 (medium): Optimize Performance
# ------------------------------------------------------------------

def _task_optimize_performance() -> dict:
    """Optimize slow algorithms — profiling, caching, algorithmic improvements."""
    return {
        "name": "optimize_performance",
        "description": "Optimize naive O(n^2) code to efficient algorithms with caching and batching",
        "system": textwrap.dedent("""\
            You are a Python developer. Return ONLY a single python code block.
            No explanations. Include the complete file. Fix ALL issues when given errors.
        """),
        "steps": [
            TaskStep(
                prompt="Here's a slow DataAnalyzer. Optimize it without changing the public API:\n\n```python\nclass DataAnalyzer:\n    def __init__(self, data: list[int]):\n        self.data = data\n    \n    def find_duplicates(self) -> list[int]:\n        \"\"\"Find all duplicate values. Currently O(n^2).\"\"\"\n        dupes = []\n        for i, x in enumerate(self.data):\n            for j, y in enumerate(self.data):\n                if i != j and x == y and x not in dupes:\n                    dupes.append(x)\n        return sorted(dupes)\n    \n    def top_k(self, k: int) -> list[int]:\n        \"\"\"Find k largest elements. Currently sorts entire list.\"\"\"\n        return sorted(self.data, reverse=True)[:k]\n    \n    def pair_sum(self, target: int) -> list[tuple[int, int]]:\n        \"\"\"Find all pairs that sum to target. Currently O(n^2).\"\"\"\n        pairs = []\n        for i in range(len(self.data)):\n            for j in range(i+1, len(self.data)):\n                if self.data[i] + self.data[j] == target:\n                    pairs.append((self.data[i], self.data[j]))\n        return sorted(pairs)\n    \n    def moving_average(self, window: int) -> list[float]:\n        \"\"\"Compute moving average. Currently O(n*window).\"\"\"\n        result = []\n        for i in range(len(self.data) - window + 1):\n            avg = sum(self.data[i:i+window]) / window\n            result.append(avg)\n        return result\n\n# Tests\nimport time\nda = DataAnalyzer([3,1,4,1,5,9,2,6,5,3,5])\nassert da.find_duplicates() == [1, 3, 5]\nassert da.top_k(3) == [9, 6, 5]\nassert (1, 9) in da.pair_sum(10)\nassert len(da.moving_average(3)) == 9\nprint('all tests pass')\n```\n\nOptimize each method. find_duplicates to O(n), top_k using heapq for O(n log k), pair_sum to O(n) with hash set, moving_average to O(n) with sliding window. Return COMPLETE file with the same tests.",
                test_cmd="python3 {file}",
                description="optimize naive O(n^2) algorithms",
            ),
            TaskStep(
                prompt="Add timing benchmarks that prove the optimization: run each method on a list of 10000 random ints and assert it completes in under 0.1 seconds. Use time.perf_counter(). Return COMPLETE file.",
                test_cmd="python3 -c \"exec(open('{file}').read()); import random; data=random.sample(range(100000),10000); da=DataAnalyzer(data); import time; t=time.perf_counter(); da.find_duplicates(); assert time.perf_counter()-t < 0.5, 'too slow'; print('perf ok')\"",
                description="add performance benchmarks",
            ),
            TaskStep(
                prompt="Error: pair_sum returns duplicate pairs — (3,7) and (7,3) both appear when both 3 and 7 exist. Also pair_sum misses pairs when the same number appears twice: [5,5] with target 10 should find (5,5). Fix both issues. Return COMPLETE file.",
                test_cmd="python3 -c \"exec(open('{file}').read()); da=DataAnalyzer([5,5,3,7]); pairs=da.pair_sum(10); assert (3,7) in pairs or (7,3) in pairs; assert (5,5) in pairs, f'missing (5,5) in {{pairs}}'; assert len([p for p in pairs if set(p)=={3,7}])==1, 'duplicate pair'; print('pair ok')\"",
                description="fix duplicate and missing pairs",
                inject_error="AssertionError: missing (5,5) in [(3, 7)] — pair_sum with hash set skips pairs where both elements are the same value",
            ),
            TaskStep(
                prompt="Add caching with an LRU cache: repeated calls to the same method with unchanged data should return cached results. Add a _cache_valid flag that invalidates when data changes. Add set_data(new_data) method. Return COMPLETE file.",
                test_cmd="python3 -c \"exec(open('{file}').read()); da=DataAnalyzer([1,2,3,2]); r1=da.find_duplicates(); r2=da.find_duplicates(); assert r1==r2==[2]; da.set_data([4,5,4,5]); r3=da.find_duplicates(); assert r3==[4,5]; print('cache ok')\"",
                description="add result caching",
            ),
            TaskStep(
                prompt="Add batch_analyze(operations: list[str]) -> dict that runs multiple operations in one call and returns results keyed by operation name. Supported operations: 'duplicates', 'top_k:N', 'pair_sum:N', 'moving_avg:N'. Return COMPLETE file.",
                test_cmd="python3 -c \"exec(open('{file}').read()); da=DataAnalyzer([1,2,3,2,1]); r=da.batch_analyze(['duplicates','top_k:2','pair_sum:3']); assert r['duplicates']==[1,2]; assert r['top_k:2']==[3,2]; assert len(r['pair_sum:3'])>0; print('batch ok')\"",
                description="batch operations",
            ),
            TaskStep(
                prompt="Add memory optimization: for very large datasets (>100k elements), use generators instead of lists where possible. Add a memory_efficient flag to __init__. When enabled, moving_average returns a generator, and internal operations use itertools. Return COMPLETE file.",
                test_cmd="python3 -c \"exec(open('{file}').read()); da=DataAnalyzer(list(range(1000)), memory_efficient=True); result=da.moving_average(10); import types; assert isinstance(result, types.GeneratorType), 'should be generator'; vals=list(result); assert len(vals)==991; print('memory ok')\"",
                description="memory-efficient mode with generators",
            ),
            TaskStep(
                prompt="Final: add a benchmark() method that returns a dict with timing results for all operations on the current data. Add comprehensive tests covering edge cases (empty data, single element, all same values, negative numbers). Assert all optimized methods produce identical results to naive implementations. Return COMPLETE file.",
                test_cmd="python3 {file}",
                description="benchmark method + comprehensive tests",
                inject_error="AssertionError: moving_average([]) raises ZeroDivisionError instead of returning [] — empty data edge case not handled",
            ),
        ],
    }


# ------------------------------------------------------------------
# Task 9 (easy): Add Test Coverage
# ------------------------------------------------------------------

def _task_add_test_coverage() -> dict:
    """Add comprehensive tests to working but untested code."""
    return {
        "name": "add_test_coverage",
        "description": "Add comprehensive test coverage to untested but working code",
        "system": textwrap.dedent("""\
            You are a Python developer. Return ONLY a single python code block.
            No explanations. Include the complete file. Fix ALL issues when given errors.
        """),
        "steps": [
            TaskStep(
                prompt="Here's working but untested code. Add comprehensive tests using assert statements:\n\n```python\nfrom datetime import datetime, timedelta\n\nclass Event:\n    def __init__(self, title: str, start: datetime, end: datetime, recurring: bool = False):\n        if end <= start:\n            raise ValueError('end must be after start')\n        self.title = title\n        self.start = start\n        self.end = end\n        self.recurring = recurring\n        self.attendees: list[str] = []\n    \n    @property\n    def duration(self) -> timedelta:\n        return self.end - self.start\n    \n    def overlaps(self, other: 'Event') -> bool:\n        return self.start < other.end and other.start < self.end\n    \n    def add_attendee(self, name: str) -> None:\n        if name not in self.attendees:\n            self.attendees.append(name)\n    \n    def remove_attendee(self, name: str) -> None:\n        self.attendees.remove(name)  # raises ValueError if not found\n\nclass Calendar:\n    def __init__(self):\n        self.events: list[Event] = []\n    \n    def add_event(self, event: Event) -> bool:\n        for existing in self.events:\n            if existing.overlaps(event):\n                return False\n        self.events.append(event)\n        return True\n    \n    def events_on(self, date: datetime) -> list[Event]:\n        return [e for e in self.events if e.start.date() == date.date()]\n    \n    def free_slots(self, date: datetime, slot_minutes: int = 60) -> list[tuple[datetime, datetime]]:\n        day_start = date.replace(hour=9, minute=0, second=0, microsecond=0)\n        day_end = date.replace(hour=17, minute=0, second=0, microsecond=0)\n        day_events = sorted(self.events_on(date), key=lambda e: e.start)\n        \n        slots = []\n        current = day_start\n        for event in day_events:\n            while current + timedelta(minutes=slot_minutes) <= event.start:\n                slot_end = current + timedelta(minutes=slot_minutes)\n                slots.append((current, slot_end))\n                current = slot_end\n            current = max(current, event.end)\n        while current + timedelta(minutes=slot_minutes) <= day_end:\n            slot_end = current + timedelta(minutes=slot_minutes)\n            slots.append((current, slot_end))\n            current = slot_end\n        return slots\n    \n    def next_available(self, duration_minutes: int, after: datetime) -> datetime:\n        for day_offset in range(365):\n            date = after + timedelta(days=day_offset)\n            for start, end in self.free_slots(date, duration_minutes):\n                if start >= after:\n                    return start\n        raise ValueError('No availability in the next year')\n```\n\nWrite happy-path tests for Event creation, duration, overlaps, attendees, Calendar add_event, events_on, and free_slots. Return the code + tests in one file.",
                test_cmd="python3 {file}",
                description="happy path tests",
            ),
            TaskStep(
                prompt="Add edge case tests: zero-duration attempt (should raise ValueError), events at exactly midnight boundary, overlapping events (add_event returns False), events spanning multiple days with events_on, single-minute slots in free_slots. Return COMPLETE file.",
                test_cmd="python3 {file}",
                description="edge case tests",
            ),
            TaskStep(
                prompt="Add error condition tests: Event with end before start, remove non-existent attendee, add duplicate attendee (should be no-op), free_slots on day with no events (should return all slots), next_available when calendar is completely booked. Return COMPLETE file.",
                test_cmd="python3 {file}",
                description="error condition tests",
            ),
            TaskStep(
                prompt="Error: the test for 'completely booked calendar' doesn't work — it's hard to book every slot for 365 days. Instead, test next_available raises ValueError by mocking free_slots to return empty. Use unittest.mock.patch. Also add a test for events with same start time. Return COMPLETE file.",
                test_cmd="python3 {file}",
                description="fix impossible test with mocking",
                inject_error="MemoryError: tried to create 365 * 8 = 2920 events to fill calendar — test is too expensive. Use mocking instead.",
            ),
            TaskStep(
                prompt="Add parametrized tests using a helper function that runs multiple inputs through the same assertion. Test overlaps() with at least 6 scenarios: complete overlap, partial overlap, adjacent (touching), contained, no overlap, same event. Return COMPLETE file.",
                test_cmd="python3 {file}",
                description="parametrized overlap tests",
            ),
            TaskStep(
                prompt="Add fixture-like setup: create a helper function make_calendar() that returns a Calendar pre-populated with a realistic week of events. Use this fixture in tests for events_on, free_slots, and next_available across different days. Return COMPLETE file.",
                test_cmd="python3 {file}",
                description="test fixtures",
            ),
            TaskStep(
                prompt="Add tests that use unittest.mock to mock datetime.now() and verify time-dependent behavior. Also add a test that verifies free_slots handles events that start before 9am or end after 5pm correctly (they should clip to business hours). Return COMPLETE file.",
                test_cmd="python3 {file}",
                description="mock datetime + business hours clipping",
                inject_error="TypeError: cannot mock built-in datetime.datetime.now — need to mock at the module level or use a wrapper function",
            ),
            TaskStep(
                prompt="Final: count the number of test cases (assert statements) and add a summary print at the end showing how many tests passed. Verify at least 40 distinct test assertions exist. Organize tests into clearly labeled sections with comments. Return COMPLETE file.",
                test_cmd="python3 {file}",
                description="count assertions + organize + final",
            ),
        ],
    }


# ------------------------------------------------------------------
# Task 10 (medium): Multi-File Refactor
# ------------------------------------------------------------------

def _task_multi_file_refactor() -> dict:
    """Split a monolith into well-structured modules."""
    return {
        "name": "multi_file_refactor",
        "description": "Refactor monolithic code into clean modules — architecture challenge",
        "system": textwrap.dedent("""\
            You are a Python developer. Return ONLY a single python code block.
            No explanations. Include the complete file. Fix ALL issues when given errors.
        """),
        "steps": [
            TaskStep(
                prompt="Here's a monolithic inventory management system. Analyze its structure and list what should be extracted:\n\n```python\nimport json\nfrom datetime import datetime\n\nclass Product:\n    def __init__(self, sku, name, price, quantity=0, category='general'):\n        self.sku = sku\n        self.name = name\n        self.price = price\n        self.quantity = quantity\n        self.category = category\n        self.created_at = datetime.now()\n    def to_dict(self):\n        return {'sku': self.sku, 'name': self.name, 'price': self.price,\n                'quantity': self.quantity, 'category': self.category}\n    @classmethod\n    def from_dict(cls, d):\n        return cls(d['sku'], d['name'], d['price'], d.get('quantity',0), d.get('category','general'))\n\nclass Inventory:\n    def __init__(self):\n        self.products = {}\n        self.transactions = []\n    def add_product(self, product):\n        if product.sku in self.products:\n            raise ValueError(f'SKU {product.sku} already exists')\n        self.products[product.sku] = product\n    def restock(self, sku, amount):\n        if sku not in self.products:\n            raise KeyError(f'Product {sku} not found')\n        if amount <= 0:\n            raise ValueError('Amount must be positive')\n        self.products[sku].quantity += amount\n        self.transactions.append({'type': 'restock', 'sku': sku, 'amount': amount, 'time': datetime.now().isoformat()})\n    def sell(self, sku, amount):\n        if sku not in self.products:\n            raise KeyError(f'Product {sku} not found')\n        if self.products[sku].quantity < amount:\n            raise ValueError(f'Insufficient stock: have {self.products[sku].quantity}, need {amount}')\n        self.products[sku].quantity -= amount\n        self.transactions.append({'type': 'sell', 'sku': sku, 'amount': amount, 'time': datetime.now().isoformat()})\n        return self.products[sku].price * amount\n    def get_value(self):\n        return sum(p.price * p.quantity for p in self.products.values())\n    def low_stock(self, threshold=5):\n        return [p for p in self.products.values() if p.quantity <= threshold]\n    def category_report(self):\n        report = {}\n        for p in self.products.values():\n            cat = p.category\n            if cat not in report:\n                report[cat] = {'count': 0, 'total_value': 0, 'products': []}\n            report[cat]['count'] += 1\n            report[cat]['total_value'] += p.price * p.quantity\n            report[cat]['products'].append(p.name)\n        return report\n    def save(self, filepath):\n        data = {'products': {sku: p.to_dict() for sku, p in self.products.items()}, 'transactions': self.transactions}\n        with open(filepath, 'w') as f:\n            json.dump(data, f)\n    def load(self, filepath):\n        with open(filepath) as f:\n            data = json.load(f)\n        self.products = {sku: Product.from_dict(d) for sku, d in data['products'].items()}\n        self.transactions = data['transactions']\n\n# Tests\ninv = Inventory()\ninv.add_product(Product('A1', 'Widget', 9.99, 100))\ninv.add_product(Product('B2', 'Gadget', 24.99, 50, 'electronics'))\ninv.sell('A1', 5)\nassert inv.products['A1'].quantity == 95\nassert inv.get_value() == 95 * 9.99 + 50 * 24.99\nprint('monolith tests pass')\n```\n\nFirst step: extract the Product class into a clean data model. Add __eq__, __repr__, validation (price >= 0, quantity >= 0, sku non-empty). Keep Inventory and tests. Return COMPLETE file.",
                test_cmd="python3 {file}",
                description="analyze monolith + extract data model",
            ),
            TaskStep(
                prompt="Extract transaction tracking into a TransactionLog class. Methods: record(type, sku, amount, price=None), get_history(sku=None) -> list, sales_total() -> float, undo_last() -> dict. Inventory should use TransactionLog internally. Return COMPLETE file.",
                test_cmd="python3 -c \"exec(open('{file}').read()); inv=Inventory(); inv.add_product(Product('A1','W',10,50)); inv.sell('A1',3); assert len(inv.transaction_log.get_history())==1; assert inv.transaction_log.sales_total()==30; print('txn ok')\"",
                description="extract TransactionLog",
            ),
            TaskStep(
                prompt="Extract reporting into a ReportGenerator class that takes an Inventory. Methods: category_report(), low_stock_report(threshold), valuation_report(), transaction_summary(). Return COMPLETE file.",
                test_cmd="python3 -c \"exec(open('{file}').read()); inv=Inventory(); inv.add_product(Product('A1','W',10,50,'tools')); rg=ReportGenerator(inv); r=rg.category_report(); assert 'tools' in r; assert r['tools']['count']==1; print('report ok')\"",
                description="extract ReportGenerator",
            ),
            TaskStep(
                prompt="Extract I/O into a StorageBackend with save/load. Make it pluggable: JSONStorage and CSVStorage both implement save(inventory, path) and load(path) -> (products, transactions). Return COMPLETE file.",
                test_cmd="python3 -c \"import tempfile, os; exec(open('{file}').read()); inv=Inventory(); inv.add_product(Product('X1','Test',5.0,10)); s=JSONStorage(); f=os.path.join(tempfile.mkdtemp(),'inv.json'); s.save(inv,f); inv2=Inventory(); prods,txns=s.load(f); assert 'X1' in prods; print('storage ok')\"",
                description="extract StorageBackend (JSON + CSV)",
            ),
            TaskStep(
                prompt="Error: CSVStorage.load() crashes because CSV doesn't preserve types — price comes back as string '5.0' instead of float. Also transactions in CSV lose their nested structure. Fix type conversion in CSV loading. Return COMPLETE file.",
                test_cmd="python3 -c \"import tempfile, os; exec(open('{file}').read()); inv=Inventory(); inv.add_product(Product('X1','Test',5.0,10)); s=CSVStorage(); f=os.path.join(tempfile.mkdtemp(),'inv.csv'); s.save(inv,f); prods,txns=s.load(f); p=prods['X1']; assert isinstance(p.price, float), f'price is {{type(p.price)}}'; assert p.price==5.0; print('csv types ok')\"",
                description="fix CSV type conversion",
                inject_error="TypeError: '>' not supported between instances of 'str' and 'int' — CSVStorage.load() returns string quantities that break comparison in low_stock()",
            ),
            TaskStep(
                prompt="Wire all modules together: Inventory takes optional StorageBackend and uses TransactionLog. ReportGenerator works with the new Inventory. Ensure all original functionality still works. Return COMPLETE file.",
                test_cmd="python3 -c \"exec(open('{file}').read()); inv=Inventory(); inv.add_product(Product('A1','Widget',9.99,100)); inv.add_product(Product('B2','Gadget',24.99,50,'electronics')); inv.sell('A1',5); assert inv.products['A1'].quantity==95; rg=ReportGenerator(inv); r=rg.category_report(); assert len(r)>=1; print('wired ok')\"",
                description="wire modules together",
            ),
            TaskStep(
                prompt="Error: circular import — ReportGenerator imports Inventory which imports TransactionLog which imports Product, but ReportGenerator also uses Product directly. Fix by ensuring clean dependency direction: Product <- TransactionLog <- Inventory <- ReportGenerator. No circular references. Return COMPLETE file.",
                test_cmd="python3 -c \"exec(open('{file}').read()); inv=Inventory(); inv.add_product(Product('Z9','Gizmo',1.50,200)); inv.restock('Z9',100); assert inv.products['Z9'].quantity==300; rg=ReportGenerator(inv); v=rg.valuation_report(); print('no circular import')\"",
                description="fix circular imports",
                inject_error="ImportError: cannot import name 'Product' from partially initialized module — circular dependency between modules",
            ),
            TaskStep(
                prompt="Add tests for each extracted component: Product validation, TransactionLog operations, ReportGenerator correctness, JSONStorage round-trip, CSVStorage round-trip. Each component must be testable independently. Return COMPLETE file.",
                test_cmd="python3 {file}",
                description="per-module tests",
            ),
            TaskStep(
                prompt="Final: add an integration test that exercises the full workflow — create inventory, add products, restock, sell, generate all reports, save/load with both backends, verify data integrity after round-trip. Return COMPLETE file.",
                test_cmd="python3 {file}",
                description="integration test + final verification",
            ),
        ],
    }


# ------------------------------------------------------------------
# Task registry
# ------------------------------------------------------------------

TASKS: list[dict] = [
    _task_linked_list(),
    _task_state_machine(),
    _task_expression_parser(),
    _task_debug_failing_test(),
    _task_write_documentation(),
    _task_cli_argument_parser(),
    _task_fix_security_vuln(),
    _task_optimize_performance(),
    _task_add_test_coverage(),
    _task_multi_file_refactor(),
]


def get_task_by_name(name: str) -> dict | None:
    """Look up a task by its name field. Returns None if not found."""
    for task in TASKS:
        if task["name"] == name:
            return task
    return None
